# Copyright (c) 2023, Dokos SAS and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _

STATUS_MAP = {
	"payment_intent.created": "Pending",
	"payment_intent.canceled": "Failed",
	"payment_intent.payment_failed": "Failed",
	"payment_intent.processing": "Pending",
	"payment_intent.succeeded": "Paid",
}

class StripeWebhooksController:
	def __init__(self, **kwargs):
		self.integration_request = frappe.get_doc(kwargs.get("doctype"), kwargs.get("docname"))
		self.integration_request.db_set("error", None)
		self.data = json.loads(self.integration_request.get("data"))
		self.payment_intent = self.data.get("data", {}).get("object", {}).get("id")
		self.metadata = {}
		self.get_reference_documents()

		self.integration_request.load_from_db()
		self.handle_webhook()

	def get_reference_documents(self):
		self.metadata = self.data.get("data", {}).get("object", {}).get("metadata")
		for k in ("reference_doctype", "reference_docname", "reference_name"):
			if k in self.metadata:
				key = "reference_docname" if k == "reference_name" else k
				self.integration_request.db_set(key, self.metadata[k])

	def handle_webhook(self):
		action = self.data.get("type")
		if action not in STATUS_MAP:
			return self.integration_request.handle_failure(
				response={"message": _("This type of event is not handled")},
				status="Not Handled"
			)

		elif not (self.integration_request.reference_doctype and self.integration_request.reference_docname):
			return self.integration_request.handle_failure(
				response={"message": _("This event contains not metadata")},
				status="Error"
			)

		elif not frappe.db.exists(self.integration_request.reference_doctype, self.integration_request.reference_docname):
			return self.integration_request.handle_failure(
				response={"message": _("The reference document does not exist")},
				status="Error"
			)

		try:
			reference_document = frappe.get_doc(self.integration_request.reference_doctype, self.integration_request.reference_docname)
			response = reference_document.run_method("on_payment_authorized", status=STATUS_MAP[action], reference_no=self.payment_intent)
			self.integration_request.handle_success(
				response={"message": response}
			)

		except Exception:
			self.integration_request.handle_failure(
				response={"message": frappe.get_traceback()},
				status="Error"
			)