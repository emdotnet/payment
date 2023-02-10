# Copyright (c) 2022, Dokos SAS and Contributors
# License: GNU General Public License v3. See license.txt

from typing import NoReturn
import stripe

import frappe
from frappe import _
from payments.utils.utils import get_gateway_controller
from frappe.utils import flt, check_format

from payments.payment_gateways.doctype.stripe_settings.stripe_data_handler import StripeDataHandler

from payments.payment_gateways.doctype.stripe_settings.api import (
	StripeCustomer,
	StripeInvoice,
	StripePaymentIntent,
	StripePaymentMethod,
)

def get_context(context):
	context.no_cache = 1

	try:
		# Instantiate the class that handles validation and decoding
		token_handler = StripeDataHandler.FromData(data=frappe.form_dict)

		# Decode and validate the data
		data = frappe._dict(token_handler.decode())

		# Retrieve the mode (payment or setup)
		mode = token_handler.get_mode()
		data.mode = mode
	except StripeDataHandler.InvalidTokenError:
		# During decoding, an InvalidTokenError is raised if the data is invalid, and an error is automatically logged.
		return redirect_to_invalid_link()
	except Exception as exc:
		# Log error in case of unexpected error, or if the settings are incorrect.
		title = "Stripe Checkout: " + repr(exc)
		frappe.log_error(title[:140], frappe.get_traceback())
		return redirect_to_invalid_link()

	# Move data to context (legacy)
	for key, value in data.items():
		context[key] = value

	# Set-up API key for Stripe
	stripe_settings = token_handler.get_controller()
	stripe.api_key = stripe_settings.get_password("secret_key")

	# Retrieve the customer's Stripe ID if it exists
	reference_document = frappe.get_doc(data.reference_doctype, data.reference_docname)
	if hasattr(reference_document, "customer"):
		# NOTE: Retrieve the customer docname using a @property method (virtual field)
		customer_docname: str = reference_document.customer
	else:
		customer_docname: str | None = reference_document.get("customer")
	stripe_customer_id = stripe_settings.get_stripe_customer_id(customer_docname) if customer_docname else None

	metadata = {
		"reference_doctype": data.reference_doctype,
		"reference_name": data.reference_docname
	}
	redirect_urls = {
		"success": stripe_settings.redirect_url or "/payment-success",
		# "failure": stripe_settings.failure_redirect_url or "/payment-failed",
		"cancel": stripe_settings.failure_redirect_url or "/payment-cancel",
	}

	# Setup mode requires a customer
	customer_api = StripeCustomer(stripe_settings)
	if mode in ("setup", "payment+setup"):
		if not stripe_customer_id:
			if not customer_docname:
				msg = _("Reference document must have a value for the `{0}` field in order to setup Stripe Checkout for future payments.").format("customer")
				frappe.log_error(msg[:140], msg, **metadata)
				return redirect_to_settings_incorrect()

			# Always create a customer if needed
			stripe_customer_id: str | None = customer_api.create(customer_docname)
			if not stripe_customer_id:
				msg = _("Failed to create Stripe customer.")
				frappe.log_error(msg[:140], msg, **metadata)
				return redirect_to_settings_incorrect()

		# Create/update Integration References
		customer_api.register(stripe_customer_id, customer_docname)

		# If an email is already set, the user won't be able to change it on the Stripe Checkout page.
		# Set to "" to allow the user to specify another one (that only Stripe will know).
		customer_api.update(stripe_customer_id, email=data.payer_email if check_format(data.payer_email) else "")
	elif not stripe_customer_id:
		stripe_customer_id = stripe_settings.get_stripe_customer_id(customer_docname)

	match mode:
		case "payment" | "payment+setup":
			# Immediate payment
			checkout_session = stripe_settings.create_payment_checkout_session(
				customer=stripe_customer_id,
				customer_email=data.payer_email,
				item=dict(amount=data.amount, currency=data.currency, description=data.description),
				metadata=metadata,
				redirect_urls=redirect_urls,
				also_setup_future_usage=bool(mode == "payment+setup"),
			)
		case "setup":
			checkout_session = stripe_settings.create_setup_checkout_session(
				customer=stripe_customer_id,
				metadata=metadata,
				redirect_urls=redirect_urls,
			)
		case _:
			raise ValueError("Invalid checkout mode: " + mode)

	frappe.local.flags.redirect_location = checkout_session.url
	raise frappe.Redirect


def redirect_to_invalid_link() -> NoReturn:
	frappe.redirect_to_message(_("Invalid link"), _("This link is not valid.<br>Please contact us."))
	frappe.local.flags.redirect_location = frappe.local.response.location
	raise frappe.Redirect

def redirect_to_settings_incorrect() -> NoReturn:
	"""Show a message to the customer if the admin settings are incorrect.
	This is a fallback in case the admin has not set up the Stripe settings correctly.
	"""
	frappe.redirect_to_message(
		title=_("Payment Gateway Error"),
		html=_("The payment gateway is not configured correctly. Please contact us."),
		http_status_code=500,
		indicator_color="red",
	)
	frappe.local.flags.redirect_location = frappe.local.response.location
	raise frappe.Redirect

def get_api_key(gateway_controller):
	if isinstance(gateway_controller, str):
		return frappe.get_doc("Stripe Settings", gateway_controller).publishable_key

	return gateway_controller.publishable_key


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
