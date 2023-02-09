# Copyright (c) 2023, Dokos SAS and contributors
# For license information, please see license.txt

from functools import cached_property
import json

import frappe
from frappe import _

class BaseStripeWebhooksController:
	STATUS_MAP = {}

	@classmethod
	def get_handled_events(cls):
		return cls.STATUS_MAP.keys()

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
		if self.data.get("type") not in self.STATUS_MAP:
			return self.failure(self.data.get("type"), status="Not Handled")
		elif not (self.integration_request.reference_doctype and self.integration_request.reference_docname):
			return self.failure(_("This event contains no metadata"))
		elif not frappe.db.exists(self.integration_request.reference_doctype, self.integration_request.reference_docname):
			return self.failure(_("The reference document does not exist"))
		return True

	def redact_client_secret(self):
		try:
			self.data = json.loads(self.integration_request.get("data"))
			if "data" in self.data and "object" in self.data["data"] and "client_secret" in self.data["data"]["object"]:
				self.data["data"]["object"]["client_secret"] = "*** Redacted per Stripe's guidelines ***"
				redacted = json.dumps(self.data, indent=2)
				self.integration_request.db_set("data", redacted)
		except Exception:
			pass

	def get_reference_document(self):
		return frappe.get_doc(self.integration_request.reference_doctype, self.integration_request.reference_docname)

	def get_customer_docname(self) -> str:
		ref_doc = self.get_reference_document()
		if not ref_doc:
			return None
		elif hasattr(ref_doc, "customer"):
			return ref_doc.customer
		elif hasattr(ref_doc, "party_name") and ref_doc.get("party_type") == "Customer":
			return ref_doc.party_name

	@cached_property
	def stripe_settings(self):
		from payments.utils.utils import get_gateway_controller
		gateway_controller = get_gateway_controller(self.integration_request.reference_doctype, self.integration_request.reference_docname)
		stripe_settings = frappe.get_cached_doc("Stripe Settings", gateway_controller)
		return stripe_settings

	def failure(self, message="", status="Failed") -> None:
		self.integration_request.handle_failure(
			response={"message": message},
			status=status
		)

	def success(self, message="") -> None:
		self.integration_request.handle_success(
			response={"message": message}
		)

	def handle_webhook(self):
		raise NotImplementedError