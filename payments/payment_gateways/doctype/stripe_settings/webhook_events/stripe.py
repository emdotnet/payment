# Copyright (c) 2023, Dokos SAS and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from .base import BaseStripeWebhooksController

class StripeWebhooksController(BaseStripeWebhooksController):
	STATUS_MAP = {
		"payment_intent.created": "Pending",
		"payment_intent.canceled": "Failed",
		"payment_intent.payment_failed": "Failed",
		"payment_intent.processing": "Pending",
		"payment_intent.succeeded": "Paid",
	}

	def handle_webhook(self):
		self.payment_intent = self.data.get("data", {}).get("object", {}).get("id")

		if not self.validate_data():
			return
		self.redact_client_secret()

		try:
			action = self.data.get("type")
			obj = self.data.get("data", {}).get("object", {})
			if obj.get("setup_future_usage") == "off_session":
				stripe_customer_id = obj.get("customer")
				if stripe_customer_id:
					if payment_method := obj.get("payment_method"):
						# Update the default payment method in Stripe's customer record
						from payments.payment_gateways.doctype.stripe_settings.api import StripeCustomer
						customer_api = StripeCustomer(self.stripe_settings)
						customer_api.update_default_payment_method(stripe_customer_id, payment_method)
						response = f"Updated default payment method for customer '{stripe_customer_id}' to '{payment_method}'"

			reference_document = self.get_reference_document()
			response = reference_document.run_method("on_payment_authorized", status=self.STATUS_MAP[action], reference_no=self.payment_intent)
			self.success(response)
		except Exception:
			self.failure(frappe.get_traceback())

STATUS_MAP = StripeWebhooksController.STATUS_MAP