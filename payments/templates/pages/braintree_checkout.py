# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import json

import frappe
from frappe import _
from payments.payment_gateways.doctype.braintree_settings.braintree_settings  import get_gateway_controller
from frappe.utils import fmt_money

EXPECTED_KEYS = (
	"amount",
	"title",
	"description",
	"reference_doctype",
	"reference_docname",
	"payer_name",
	"payer_email",
	"order_id",
	"currency",
)


def get_context(context):
	context.no_cache = 1

	# all these keys exist in form_dict
	if not set(EXPECTED_KEYS) - set(list(frappe.form_dict)):
		for key in EXPECTED_KEYS:
			context[key] = frappe.form_dict[key]

		gateway_controller = get_gateway_controller(context.reference_doctype, context.reference_docname)
		settings = frappe.get_doc("Braintree Settings", gateway_controller)

		context.formatted_amount = fmt_money(amount=context.amount, currency=context.currency)
		context.locale = frappe.local.lang
		context.header_img = frappe.db.get_value("Braintree Settings", gateway_controller, "header_img")
		context.client_token = settings.generate_token(context)

	else:
		frappe.redirect_to_message(_("Invalid link"), _("This link is not valid.<br>Please contact us."))
		frappe.local.flags.redirect_location = frappe.local.response.location
		raise frappe.Redirect


@frappe.whitelist(allow_guest=True)
def make_payment(payload_nonce, data):
	data = frappe.parse_json(data)
	data.update({"payload_nonce": payload_nonce})

	gateway_controller = get_gateway_controller(data["reference_doctype"], data["reference_docname"])
	return frappe.get_doc("Braintree Settings", gateway_controller).create_payment_request(data)
