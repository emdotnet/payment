# Copyright (c) 2019, Dokos SAS and contributors
# For license information, please see license.txt


from urllib.parse import urlencode

import frappe
import stripe
from frappe import _
from payments.utils.utils import PaymentGatewayController
from frappe.utils import call_hook_method, flt, get_url, check_format
from payments.utils import create_payment_gateway

from payments.payment_gateways.doctype.stripe_settings.api import (
	StripeCustomer,
	StripeInvoiceItem,
	StripePaymentIntent,
	StripePrice,
	StripeWebhookEndpoint,
)
from payments.payment_gateways.doctype.stripe_settings.webhook_events import StripeWebhooksController, StripeSetupWebhooksController

WEBHOOK_ENDPOINT = "/api/method/payments.payment_gateways.doctype.stripe_settings.webhooks?account="

class StripeSettings(PaymentGatewayController):
	currency_wise_minimum_charge_amount = {
		"JPY": 50,
		"MXN": 10,
		"DKK": 2.50,
		"HKD": 4.00,
		"NOK": 3.00,
		"SEK": 3.00,
		"USD": 0.50,
		"AUD": 0.50,
		"BRL": 0.50,
		"CAD": 0.50,
		"CHF": 0.50,
		"EUR": 0.50,
		"GBP": 0.30,
		"NZD": 0.50,
		"SGD": 0.50,
	}

	enabled_events = [
		"payment_intent.created",
		"payment_intent.canceled",
		"payment_intent.payment_failed",
		"payment_intent.processing",
		"payment_intent.succeeded",
	]

	def __init__(self, *args, **kwargs):
		super(StripeSettings, self).__init__(*args, **kwargs)
		if not self.is_new():
			self.configure_stripe()

	def before_insert(self):
		self.gateway_name = frappe.scrub(self.gateway_name)

	def validate(self):
		if self.name:
			self.webhook_url = f"{frappe.utils.get_url(WEBHOOK_ENDPOINT)}{self.name}"

	def configure_stripe(self):
		self.stripe = stripe
		self.stripe.api_key = self.get_password(fieldname="secret_key", raise_exception=False)
		self.stripe.default_http_client = stripe.http_client.RequestsClient()

	def get_supported_currencies(self):
		account = self.stripe.Account.retrieve()
		supported_payment_currencies = self.stripe.CountrySpec.retrieve(account["country"])[
			"supported_payment_currencies"
		]

		return [currency.upper() for currency in supported_payment_currencies]

	def on_update(self):
		create_payment_gateway(
			"Stripe-" + self.gateway_name, settings="Stripe Settings", controller=self.gateway_name
		)
		call_hook_method("payment_gateway_enabled", gateway="Stripe-" + self.gateway_name)
		if not self.flags.ignore_mandatory:
			self.validate_stripe_credentials()

	def validate_stripe_credentials(self):
		try:
			self.configure_stripe()
			balance = self.stripe.Balance.retrieve()
			return balance
		except Exception as e:
			frappe.throw(_("Stripe connection could not be initialized.<br>Error: {0}").format(str(e)))

	def validate_transaction_currency(self, currency):
		if currency not in self.get_supported_currencies():
			frappe.throw(
				_(
					"Please select another payment method. Stripe does not support transactions in currency '{0}'"
				).format(currency)
			)

	def validate_minimum_transaction_amount(self, currency, amount):
		if currency in self.currency_wise_minimum_charge_amount:
			if flt(amount) < self.currency_wise_minimum_charge_amount.get(currency, 0.0):
				frappe.throw(
					_("For currency {0}, the minimum transaction amount should be {1}").format(
						currency, self.currency_wise_minimum_charge_amount.get(currency, 0.0)
					)
				)

	def get_stripe_plan(self, plan, currency):
		try:
			stripe_plan = StripePrice(self).retrieve(plan)
			if not stripe_plan.active:
				frappe.throw(_("Payment plan {0} is no longer active.").format(plan))
			if not currency == stripe_plan.currency.upper():
				frappe.throw(
					_("Payment plan {0} is in currency {1}, not {2}.").format(
						plan, stripe_plan.currency.upper(), currency
					)
				)
			return stripe_plan
		except stripe.error.InvalidRequestError:
			frappe.throw(_("Invalid Stripe plan or currency: {0} - {1}").format(plan, currency))

	def get_stripe_invoice_item(self, item, currency):
		try:
			invoice_item = StripeInvoiceItem(self).retrieve(item)
			if not currency == invoice_item.currency.upper():
				frappe.throw(
					_("Payment plan {0} is in currency {1}, not {2}.").format(
						item, invoice_item.currency.upper(), currency
					)
				)
			return invoice_item
		except stripe.error.InvalidRequestError:
			frappe.throw(_("Invalid currency for invoice item: {0} - {1}").format(item, currency))

	def get_payment_url(self, **kwargs):
		return get_url(
			"./stripe_checkout?{0}".format(urlencode(kwargs))
		)

	def cancel_subscription(self, **kwargs):
		from payments.payment_gateways.doctype.stripe_settings.api import StripeSubscription

		return StripeSubscription(self).cancel(
			kwargs.get("subscription"),
			invoice_now=kwargs.get("invoice_now", False),
			prorate=kwargs.get("prorate", False),
		)

	def get_stripe_customer_id(self, customer):
		return frappe.db.get_value(
			"Integration References",
			dict(customer=customer, stripe_settings=self.name),
			"stripe_customer_id",
		)

	def immediate_payment_processing(self, reference, customer, amount, currency, description, metadata):
		try:
			stripe_customer_id = self.get_stripe_customer_id(customer)
			payment_intent_id = self.create_payment_intent(reference, stripe_customer_id, amount, currency, description, metadata)
			return payment_intent_id
		except Exception:
			frappe.log_error(
				_("Stripe direct processing failed for {0}".format(reference)),
				message=frappe.get_traceback(),
				reference_doctype=isinstance(metadata, dict) and metadata.get("reference_doctype"),
				reference_name=isinstance(metadata, dict) and metadata.get("reference_name"),
			)

	def create_payment_intent(self, reference, customer, amount, currency, description, metadata):
		payment_method = StripeCustomer(self).get(customer).get("invoice_settings", {}).get("default_payment_method")
		statement_descriptor = str(reference)[:22]

		payment_intent = (
			StripePaymentIntent(self, reference).create(
				amount=round(flt(amount) * 100.0),
				description=description,
				currency=currency,
				customer=customer,
				confirm=True,
				off_session=True,
				metadata=metadata,
				payment_method=payment_method,
				statement_descriptor=statement_descriptor
			)
			or {}
		)

		self.trigger_on_payment_authorized(metadata, payment_intent.get("id"))

		return payment_intent.get("id")

	def make_line_item(self, amount, currency, description):
		return {
			"price_data": {
				"currency": currency,
				"product_data": {
					"name": description,
				},
				"unit_amount": round(flt(amount) * 100.0),
			},
			"quantity": 1,
		}

	def create_payment_checkout_session(self, *, customer, customer_email, item, redirect_urls, metadata, also_setup_future_usage=False):
		payment_intent_data = { "metadata": metadata }
		more_options = {}

		if also_setup_future_usage:
			payment_intent_data["setup_future_usage"] = "off_session"
			# more_options["customer_creation"] = "required"
			# more_options["consent_collection"] = { "terms_of_service": "required" }
			custom_text = _("This payment method will be used for subsequent recurring payments.")
			more_options["custom_text"] = {"submit": {"message": custom_text}}
			if not customer:
				raise ValueError("The `customer` parameter is required with also_setup_future_usage=True")
		else:
			if check_format(customer_email):
				more_options["customer_email"] = customer_email

		checkout_session = stripe.checkout.Session.create(
			mode="payment",
			customer=customer,
			metadata=metadata,
			line_items=[self.make_line_item(**item)],
			payment_intent_data=payment_intent_data,
			success_url=get_url(redirect_urls["success"]),
			cancel_url=get_url(redirect_urls["cancel"]),
			**more_options,
		)

		# NOTE: A PaymentIntent is no longer created during Checkout Session creation in payment mode.
		# https://stripe.com/docs/upgrades#2022-08-01
		self.trigger_on_payment_authorized(metadata, payment_intent=None)
		return checkout_session

	def create_setup_checkout_session(self, *, customer, redirect_urls, metadata, payment_method_types=["card", "sepa_debit"]):
		checkout_session = stripe.checkout.Session.create(
			mode="setup",
			customer=customer,
			metadata=metadata,
			setup_intent_data={"metadata": metadata},
			payment_method_types=payment_method_types,
			success_url=get_url(redirect_urls["success"]),
			cancel_url=get_url(redirect_urls["cancel"]),
		)
		return checkout_session

	def trigger_on_payment_authorized(self, metadata, payment_intent=None):
		if metadata.get("reference_doctype") and (metadata.get("reference_name") or metadata.get("reference_docname")):
			reference_document = frappe.get_doc(metadata.get("reference_doctype"), (metadata.get("reference_name") or metadata.get("reference_docname")))
			reference_document.run_method("on_payment_authorized", "Pending", payment_intent)

	def get_transaction_fees(self, payment_intent):
		stripe_payment_intent_object = self.stripe.PaymentIntent.retrieve(payment_intent, expand=['latest_charge.balance_transaction'])
		return frappe._dict(
			base_amount = flt(stripe_payment_intent_object.latest_charge.amount) / 100.0,
			fee_amount = flt(stripe_payment_intent_object.latest_charge.balance_transaction.fee) / 100.0,
			exchange_rate = flt(stripe_payment_intent_object.latest_charge.balance_transaction.exchange_rate)
		)

	def get_customer_id(self, payment_intent):
		stripe_payment_intent_object = self.stripe.PaymentIntent.retrieve(payment_intent)
		if stripe_payment_intent_object:
			return stripe_payment_intent_object.customer
		else:
			return None


def handle_webhooks(**kwargs):
	integration_request = frappe.get_doc(kwargs.get("doctype"), kwargs.get("docname"))

	if integration_request.service_document in ["charge", "payment_intent", "invoice", "checkout"]:
		StripeWebhooksController(**kwargs)
	elif integration_request.service_document in ["setup_intent", "payment_method", "customer"]:
		StripeSetupWebhooksController(**kwargs)
	else:
		integration_request.handle_failure({"message": _("This type of event is not handled")}, "Not Handled")


@frappe.whitelist()
def create_delete_webhooks(settings, action="create"):
	stripe_settings = frappe.get_doc("Stripe Settings", settings)
	url = f"{frappe.utils.get_url(WEBHOOK_ENDPOINT)}{stripe_settings.name}"

	if action == "create":
		return create_webhooks(stripe_settings, url)
	elif action == "delete":
		return delete_webhooks(stripe_settings, url)


def create_webhooks(stripe_settings, url):
	try:
		result = StripeWebhookEndpoint(stripe_settings).create(url, stripe_settings.enabled_events)
		if result:
			frappe.db.set_value(
				"Stripe Settings", stripe_settings.name, "webhook_secret_key", result.get("secret")
			)
		return result
	except Exception:
		frappe.log_error(_("Stripe webhook creation error"))


def delete_webhooks(stripe_settings, url):
	webhooks_list = StripeWebhookEndpoint(stripe_settings).get_all()

	for webhook in webhooks_list.get("data", []):
		if webhook.get("url") == url:
			try:
				StripeWebhookEndpoint(stripe_settings).delete(webhook.get("id"))
				frappe.db.set_value("Stripe Settings", stripe_settings.name, "webhook_secret_key", "")
			except Exception:
				frappe.log_error(_("Stripe webhook deletion error"))

	return webhooks_list

