import json

import frappe
from frappe.core.doctype.file import remove_file_by_url
from frappe.rate_limiter import rate_limit
from frappe.utils import flt
from frappe.website.doctype.web_form.web_form import WebForm

from payments.utils import get_payment_gateway_controller


class PaymentWebForm(WebForm):
	def validate(self):
		super().validate()

		if getattr(self, "accept_payment", False):
			self.validate_payment_amount()
			self.validate_gateway_doc_field()

	def validate_gateway_doc_field(self):
		meta = frappe.get_meta(self.doc_type)
		if not meta.has_field("payment_gateway"):
			frappe.throw(frappe._(
				"The selected document type ({0}) must contain a `{1}` field. This field is used to store the payment gateway used for the payment made when the form is submitted."
			).format(frappe._(self.doc_type), "payment_gateway"))

	def should_pay_for_doc(self, doc):
		if getattr(self, "accept_payment", False):
			meta = frappe.get_meta(doc.doctype)
			if meta.has_field("paid"):
				if doc.paid:
					return False  # document already paid
			return True
		return False  # web form does not accept payments

	def webform_validate_doc(self, doc):
		super().webform_validate_doc(doc)

		if self.should_pay_for_doc(doc):
			meta = frappe.get_meta(doc.doctype)
			if meta.has_field("payment_gateway"):
				doc.payment_gateway = self.payment_gateway
			doc.run_method("validate_payment")

	def webform_accept_doc(self, doc):
		original_result = super().webform_accept_doc(doc)

		if self.should_pay_for_doc(doc):
			redirect_url = self.get_payment_gateway_url(doc)
			return { "redirect": redirect_url }

		return original_result

	def validate_payment_amount(self):
		if self.amount_based_on_field and not self.amount_field:
			frappe.throw(frappe._("Please select a Amount Field."))
		elif not self.amount_based_on_field and not flt(self.amount) > 0:
			frappe.throw(frappe._("Amount must be greater than 0."))

	def get_payment_gateway_url(self, doc):
		if getattr(self, "accept_payment", False):
			controller = get_payment_gateway_controller(self.payment_gateway)

			title = f"Payment for {doc.doctype} {doc.name}"
			amount = self.amount
			if self.amount_based_on_field:
				amount = doc.get(self.amount_field)

			from decimal import Decimal

			if amount is None or Decimal(amount) <= 0:
				return frappe.utils.get_url(self.success_url or self.route)

			payment_details = {
				"amount": amount,
				"title": title,
				"description": title,
				"reference_doctype": doc.doctype,
				"reference_docname": doc.name,
				"payer_email": doc.get("email") or frappe.session.user,
				"payer_name": doc.get("full_name") or frappe.utils.get_fullname(frappe.session.user),
				"order_id": doc.name,
				"currency": self.currency,
				"redirect_to": frappe.utils.get_url(self.success_url or self.route),
			}

			# Redirect the user to this url
			return controller.get_payment_url(**payment_details)


@frappe.whitelist(allow_guest=True)
@rate_limit(key="web_form", limit=5, seconds=60, methods=["POST"])
def accept(web_form, data, docname=None, for_payment=False):
	from frappe.website.doctype.web_form.web_form import accept
	raise DeprecationWarning("This API endpoint is deprecated.")
	return accept(web_form=web_form, data=data)
