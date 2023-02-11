# Copyright (c) 2019, Dokos SAS and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe import _
from frappe.utils import fmt_money, get_url


def get_context(context):
	context.no_cache = 1
	context.show_sidebar = False

	if frappe.form_dict.link:
		reference_document = frappe.get_doc("Payment Request", dict(payment_key=frappe.form_dict.link))
		context.payment_gateways = get_payment_gateways(reference_document)
	elif all(k in frappe.form_dict for k in ("reference_doctype","reference_name")):
		reference_document = frappe.get_doc(frappe.form_dict.reference_doctype, frappe.form_dict.reference_name)
		context.payment_gateways = get_payment_gateways(reference_document)

	if not reference_document or not context.payment_gateways:
		return

	if hasattr(reference_document, "get_payment_status"):
		reference_document.run_method("get_payment_status")

	context.reference_doctype = reference_document.doctype
	context.reference_name = reference_document.name
	context.subject = reference_document.get("subject") or reference_document.get("description")
	context.formattedAmount = fmt_money(
		reference_document.get("grand_total") or reference_document.get("amount"), currency=reference_document.get("currency")
	)


def get_payment_gateways(reference_document):
	payment_gateways = []
	for gateway in reference_document.get("payment_gateways"):
		result = check_and_add_gateway(gateway.payment_gateway, currency=reference_document.get("currency"))
		if result:
			payment_gateways.append(result)

	if not payment_gateways and reference_document.get("payment_gateway"):
		result = check_and_add_gateway(reference_document.get("payment_gateway"), currency=reference_document.get("currency"))
		if result:
			payment_gateways.append(result)

	return payment_gateways


def check_and_add_gateway(gateway, currency):
	if frappe.db.exists(
		"Payment Gateway Account", dict(payment_gateway=gateway, currency=currency)
	):
		return frappe.db.get_value("Payment Gateway", gateway, ["name", "title", "icon"], as_dict=True)


@frappe.whitelist(allow_guest=True)
def get_payment_url(reference_doctype, reference_name, gateway):
	reference_document = frappe.get_doc(reference_doctype, reference_name)
	if frappe.get_meta(reference_doctype).has_field("payment_gateway"):
		reference_document.db_set("payment_gateway", gateway)

	if hasattr(reference_document, "get_payment_url"):
		return reference_document.get_payment_url(gateway)
	else:
		return get_url("/payment-failed")
