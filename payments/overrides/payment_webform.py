import frappe
from frappe import _
from frappe.utils import flt
from frappe.website.doctype.web_form.web_form import WebForm

from payments.utils import get_payment_gateway_controller


class PaymentWebForm(WebForm):
	def validate(self):
		super().validate()

		if getattr(self, "accept_payment", False):
			self.validate_payment_amount()
			self.validate_currency()
			self.validate_ref_doctype_fields()
			self.clear_amount_if_fetching_from_field()
			self.clear_currency_if_fetching_from_field()

	def validate_ref_doctype_fields(self):
		meta = frappe.get_meta(self.doc_type)
		required_fields = ["payment_gateway"]
		for field in required_fields:
			if not meta.has_field(field):
				frappe.throw(_(
					"The selected document type ({0}) must contain a `{1}` field. This field is used to store data when the form is submitted. Required fields are: {2}"
				).format(_(self.doc_type), field, ", ".join(required_fields)))

	def validate_payment_amount(self):
		if not self.can_require_immediate_payment():
			return  # no need to validate amount if not accepting immediate payment
		if self.amount_based_on_field and not self.amount_field:
			frappe.throw(_("Please select a Amount Field."))
		elif not self.amount_based_on_field and not flt(self.amount) > 0:
			frappe.throw(_("Amount must be greater than 0."))

	def validate_currency(self):
		if not self.can_require_immediate_payment():
			return  # no need to validate currency if not accepting immediate payment
		if self.currency_based_on_field and not self.currency_field:
			frappe.throw(_("Please select a {0} Field.").format(_("Currency")))
		elif not self.currency_based_on_field and not self.currency:
			frappe.throw(_("The field {0} is mandatory").format(_("Currency")))

	def clear_amount_if_fetching_from_field(self):
		if self.amount_based_on_field:
			self.amount = None

	def clear_currency_if_fetching_from_field(self):
		if self.currency_based_on_field:
			self.currency = None

	PAYMENT_TYPES = {
		"Immediate payment": "immediate",
		"Automatic payments": "offline",
		"Initial payment followed by automatic payments": "immediate+offline",
	}

	def get_payment_type(self):
		accept_payment = bool(self.accept_payment)
		if not accept_payment:
			return None

		if not getattr(self, "payment_type", None):
			return "immediate"

		payment_type = self.PAYMENT_TYPES.get(self.payment_type, "immediate")
		return payment_type

	def has_payments_enabled(self, doc):
		if self.get_payment_type():
			# Legacy: could be removed in future (unused in Dokos/Dodock)
			if frappe.get_meta(doc.doctype).has_field("paid") and doc.paid:
				return False  # document already paid

			return True  # web form accepts payments
		return False  # web form does not accept payments

	def webform_validate_doc(self, doc):
		super().webform_validate_doc(doc)

		if self.has_payments_enabled(doc):
			meta = frappe.get_meta(doc.doctype)
			if meta.has_field("payment_gateway"):
				doc.payment_gateway = self.payment_gateway
			doc.run_method("validate_payment")

	def webform_accept_doc(self, doc):
		original_result = super().webform_accept_doc(doc)

		if self.has_payments_enabled(doc):
			redirect_url = self.get_payment_gateway_url(doc)
			return { "redirect": redirect_url }

		return original_result

	def get_currency(self, doc):
		if self.currency_based_on_field:
			return doc.get(self.currency_field)
		return self.currency

	def get_amount(self, doc):
		if self.amount_based_on_field:
			return doc.get(self.amount_field)
		return self.amount

	def can_require_immediate_payment(self):
		payment_type = self.get_payment_type()
		return payment_type in ("immediate", "immediate+offline")

	def get_payment_gateway_url(self, doc):
		payment_type = self.get_payment_type()
		if not payment_type:
			return None

		controller = get_payment_gateway_controller(self.payment_gateway)

		# Get title
		if payment_type == "offline":
			title = _("Setup automatic payments for {0} {1}").format(_(doc.doctype), doc.name)
		else:
			title = _("Payment for {0} {1}").format(_(doc.doctype), doc.name)

		# Get amount and check it is valid
		will_pay_immediately = self.can_require_immediate_payment()
		amount = None
		currency = None
		if will_pay_immediately:
			amount = self.get_amount(doc)
			currency = self.get_currency(doc)

			from decimal import Decimal
			if amount is None or Decimal(amount) <= 0:
				return frappe.utils.get_url(self.success_url or self.route)

		payment_details = {
			"_payment_type": payment_type,
			"amount": amount,
			"title": title,
			"description": title,
			"reference_doctype": doc.doctype,
			"reference_docname": doc.name,
			"payer_email": doc.get("email") or frappe.session.user,
			"payer_name": doc.get("full_name") or frappe.utils.get_fullname(frappe.session.user),
			"order_id": doc.name,
			"currency": currency,
			"redirect_to": frappe.utils.get_url(self.success_url or self.route),
		}

		# Redirect the user to this url
		return controller.get_payment_url(**payment_details)
