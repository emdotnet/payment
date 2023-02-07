# Copyright (c) 2022, Dokos SAS and Contributors
# License: GNU General Public License v3. See license.txt

import stripe

import frappe
from frappe import _
from payments.utils.utils import get_gateway_controller
from frappe.utils import flt

from payments.payment_gateways.doctype.stripe_settings.api import (
	StripeCustomer,
	StripeInvoice,
	StripePaymentIntent,
	StripePaymentMethod,
)

expected_keys = (
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

	if not (set(expected_keys) - set(list(frappe.form_dict))):
		for key in expected_keys:
			context[key] = frappe.form_dict[key]

		gateway_controller = get_gateway_controller(
			context.reference_doctype, context.reference_docname
		)
		if not gateway_controller:
			redirect_to_invalid_link()

		reference_document = frappe.get_doc(context.reference_doctype, context.reference_docname)
	else:
		redirect_to_invalid_link()

	stripe_settings = frappe.get_cached_doc("Stripe Settings", gateway_controller)
	stripe.api_key = stripe_settings.get_password("secret_key")
	customer = reference_document.customer if hasattr(reference_document, 'customer') else reference_document.get("customer")
	stripe_customer_id = stripe_settings.get_stripe_customer_id(customer) if customer else None

	checkout_session = stripe_settings.create_checkout_session(
		customer=stripe_customer_id,
		customer_email=context.payer_email,
		metadata={
			"reference_doctype": context.reference_doctype,
			"reference_name": context.reference_docname
		},
		amount=context.amount,
		currency=context.currency,
		description=context.description,
		payment_success_redirect=stripe_settings.redirect_url or "/payment-success",
		payment_failure_redirect=stripe_settings.failure_redirect_url or "/payment-failed",
		mode="setup" if is_linked_to_subscription(context.reference_doctype) else "payment"
	)

	frappe.local.flags.redirect_location = checkout_session.url
	raise frappe.Redirect


def redirect_to_invalid_link():
	frappe.redirect_to_message(_("Invalid link"), _("This link is not valid.<br>Please contact us."))
	frappe.local.flags.redirect_location = frappe.local.response.location
	raise frappe.Redirect

def get_api_key(gateway_controller):
	if isinstance(gateway_controller, str):
		return frappe.get_doc("Stripe Settings", gateway_controller).publishable_key

	return gateway_controller.publishable_key

def is_linked_to_subscription(reference_doctype):
	meta = frappe.get_meta(reference_doctype)
	if reference_doctype == "Subscription" or [df for df in meta.fields if df.fieldname == "subscription"]:
		return True


@frappe.whitelist(allow_guest=True)
def make_payment_intent(
	payment_key,
	customer=None,
	reference_doctype=None,
	reference_docname=None,
	webform=None,
	grand_total=None,
	currency=None,
):
	if frappe.db.exists("Payment Request", {"payment_key": payment_key}):
		payment_request = frappe.get_doc("Payment Request", {"payment_key": payment_key})
		gateway_controller_name = get_gateway_controller("Payment Request", payment_request.name)
		gateway_controller = frappe.get_doc("Stripe Settings", gateway_controller_name)

	elif webform and reference_doctype and reference_docname:
		gateway_controller_name = get_gateway_controller("Web Form", webform)
		gateway_controller = frappe.get_doc("Stripe Settings", gateway_controller_name)
		payment_request = create_payment_request(
			reference_doctype=reference_doctype,
			reference_name=reference_docname,
			grand_total=grand_total,
			currency=currency,
			payment_gateway=frappe.db.get_value("Web Form", webform, "payment_gateway"),
		)

	payment_intent_object = dict(
		metadata={
			"reference_doctype": payment_request.reference_doctype,
			"reference_name": payment_request.reference_name,
			"payment_request": payment_request.name,
		}
	)

	if not webform:
		payment_intent_object.update(dict(setup_future_usage="off_session"))

	if customer:
		payment_intent_object.update(dict(customer=customer))

	payment_intent = StripePaymentIntent(gateway_controller, payment_request).create(
		amount=round(flt(payment_request.grand_total) * 100),
		currency=payment_request.currency,
		**payment_intent_object
	)

	return payment_intent


def create_payment_request(**kwargs):
	# TODO: Refactor implementation
	from erpnext.accounts.doctype.payment_request.payment_request import make_payment_request

	return frappe.get_doc(
		make_payment_request(
			**{
				"dt": kwargs.get("reference_doctype"),
				"dn": kwargs.get("reference_name"),
				"grand_total": kwargs.get("grand_total"),
				"submit_doc": True,
				"return_doc": True,
				"mute_email": 1,
				"currency": kwargs.get("currency"),
				"payment_gateway": kwargs.get("payment_gateway"),
			}
		)
	)


@frappe.whitelist(allow_guest=True)
def retry_invoice(**kwargs):
	payment_request, payment_gateway = _update_payment_method(**kwargs)

	invoice = StripeInvoice(payment_gateway).retrieve(
		kwargs.get("invoiceId"), expand=["payment_intent"]
	)
	return invoice


def _update_payment_method(**kwargs):
	if not kwargs.get("payment_key"):
		return

	payment_request = frappe.get_doc("Payment Request", {"payment_key": kwargs.get("payment_key")})
	gateway_controller_name = get_gateway_controller("Payment Request", payment_request.name)
	gateway_controller = frappe.get_doc("Stripe Settings", gateway_controller_name)

	StripePaymentMethod(gateway_controller).attach(
		kwargs.get("paymentMethodId"), kwargs.get("customerId")
	)
	StripeCustomer(gateway_controller).update(
		kwargs.get("customerId"),
		invoice_settings={
			"default_payment_method": kwargs.get("paymentMethodId"),
		},
	)

	return payment_request, gateway_controller


@frappe.whitelist(allow_guest=True)
def update_payment_method(**kwargs):
	_update_payment_method(**kwargs)
