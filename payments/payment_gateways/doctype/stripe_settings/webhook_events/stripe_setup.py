# Copyright (c) 2023, Dokos SAS and contributors
# For license information, please see license.txt

from functools import cached_property
import json

import frappe
from frappe import _

STATUS_MAP = {
	"setup_intent.succeeded": "Payment Method Registered",
	"payment_method.attached": "",
	"customer.updated": "",
}

class StripeSetupWebhooksController:
	def __init__(self, **kwargs):
		self.integration_request = frappe.get_doc(kwargs.get("doctype"), kwargs.get("docname"))
		self.integration_request.db_set("error", None)
		self.data = json.loads(self.integration_request.get("data"))
		self.metadata = {}
		self.update_integration_request_from_metadata()

		self.integration_request.load_from_db()
		self.handle_webhook()

	def update_integration_request_from_metadata(self):
		"""Replace the integration request's ref doc (Payment Request) with the one from the metadata if it exists."""
		self.metadata = self.data.get("data", {}).get("object", {}).get("metadata")
		for k in ("reference_doctype", "reference_docname", "reference_name"):
			if k in self.metadata:
				key = "reference_docname" if k == "reference_name" else k
				self.integration_request.db_set(key, self.metadata[k])

	def validate_data(self):
		if self.data.get("type") not in STATUS_MAP:
			return self.failure(self.data.get("type"), status="Not Handled")
		elif not (self.integration_request.reference_doctype and self.integration_request.reference_docname):
			return self.failure(_("This event contains no metadata"))
		elif not frappe.db.exists(self.integration_request.reference_doctype, self.integration_request.reference_docname):
			return self.failure(_("The reference document does not exist"))
		return True

	def redact_client_secret(self):
		self.data = json.loads(self.integration_request.get("data"))
		if self.data.get("type") in ("setup_intent.created", "setup_intent.succeeded"):
			if "data" in self.data and "object" in self.data["data"] and "client_secret" in self.data["data"]["object"]:
				self.data["data"]["object"]["client_secret"] = "*** Redacted per Stripe's guidelines ***"
				redacted = json.dumps(self.data, indent=2)
				self.integration_request.db_set("data", redacted)

	def get_reference_document(self):
		return frappe.get_cached_doc(self.integration_request.reference_doctype, self.integration_request.reference_docname)

	def get_customer_docname(self) -> str:
		ref_doc = self.get_reference_document()
		if hasattr(ref_doc, "customer"):
			return ref_doc.customer
		elif hasattr(ref_doc, "party_name") and ref_doc.get("party_type", None) == "Customer":
			return ref_doc.party_name

	@cached_property
	def stripe_settings(self):
		from payments.utils.utils import get_gateway_controller
		gateway_controller = get_gateway_controller(self.integration_request.reference_doctype, self.integration_request.reference_docname)
		stripe_settings = frappe.get_cached_doc("Stripe Settings", gateway_controller)
		return stripe_settings

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

	def failure(self, message="", status="Failed") -> None:
		self.integration_request.handle_failure(
			response={"message": message},
			status=status
		)

	def success(self, message="") -> None:
		self.integration_request.handle_success(
			response={"message": message}
		)
