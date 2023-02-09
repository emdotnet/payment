# Copyright (c) 2023, Dokos SAS and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from .base import BaseStripeWebhooksController

class StripeSetupWebhooksController(BaseStripeWebhooksController):
	STATUS_MAP = {
		"setup_intent.succeeded": "Payment Method Registered",
	}

	def handle_webhook(self):
		if not self.validate_data():
			return
		self.redact_client_secret()

		response = ""
		type = self.data.get("type")
		obj = self.data.get("data", {}).get("object", {})

		# Create or update the customer
		customer_docname = self.get_customer_docname()
		stripe_customer_id = (
			obj.get("customer", None)
			or obj.get("invoice_settings", {}).get("customer", None)
		)

		from payments.payment_gateways.doctype.stripe_settings.api import StripeCustomer
		customer_api = StripeCustomer(self.stripe_settings)

		if not stripe_customer_id:
			if customer_docname:
				# Create the customer
				stripe_customer_id = customer_api.create(customer_docname)
				assert stripe_customer_id, "Failed to create Stripe customer"
			else:
				return self.failure("Missing customer in reference document: " + repr(self.get_reference_document()))

		if customer_docname:
			# Update/Create the Integration References
			customer_api.register(stripe_customer_id, customer_docname)

		# Update the default payment method
		payment_method = (
			obj.get("payment_method", None)
			or obj.get("invoice_settings", {}).get("default_payment_method", None)
		)
		# payment_method_options = {"card": {"request_three_d_secure": "automatic"}}
		# payment_method_types = ["card", "sepa_debit"]  # choices shown on Stripe's setup page

		if payment_method:
			# Update the default payment method in Stripe's customer record
			customer_api.update_default_payment_method(stripe_customer_id, payment_method)
			response = f"Updated default payment method for customer '{stripe_customer_id}' to '{payment_method}'"

		try:
			if status := STATUS_MAP.get(type, None):
				reference_document = self.get_reference_document()
				response = reference_document.run_method("on_payment_authorized", status=status, reference_no=None) or response
			self.success(response)
		except Exception:
			self.failure(frappe.get_traceback())
