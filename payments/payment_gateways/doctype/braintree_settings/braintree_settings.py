# Copyright (c) 2021, Frappe Technologies and contributors
# License: MIT. See LICENSE


from urllib.parse import urlencode

import braintree
import frappe
from frappe import _
from frappe.integrations.utils import (
	create_request_log,
)

from payments.utils.utils import (
	PaymentGatewayController,
)
from payments.utils import create_payment_gateway
from frappe.utils import call_hook_method, get_url


class BraintreeSettings(PaymentGatewayController):
	supported_currencies = [
		"AED",
		"AMD",
		"AOA",
		"ARS",
		"AUD",
		"AWG",
		"AZN",
		"BAM",
		"BBD",
		"BDT",
		"BGN",
		"BIF",
		"BMD",
		"BND",
		"BOB",
		"BRL",
		"BSD",
		"BWP",
		"BYN",
		"BZD",
		"CAD",
		"CHF",
		"CLP",
		"CNY",
		"COP",
		"CRC",
		"CVE",
		"CZK",
		"DJF",
		"DKK",
		"DOP",
		"DZD",
		"EGP",
		"ETB",
		"EUR",
		"FJD",
		"FKP",
		"GBP",
		"GEL",
		"GHS",
		"GIP",
		"GMD",
		"GNF",
		"GTQ",
		"GYD",
		"HKD",
		"HNL",
		"HRK",
		"HTG",
		"HUF",
		"IDR",
		"ILS",
		"INR",
		"ISK",
		"JMD",
		"JPY",
		"KES",
		"KGS",
		"KHR",
		"KMF",
		"KRW",
		"KYD",
		"KZT",
		"LAK",
		"LBP",
		"LKR",
		"LRD",
		"LSL",
		"LTL",
		"MAD",
		"MDL",
		"MKD",
		"MNT",
		"MOP",
		"MUR",
		"MVR",
		"MWK",
		"MXN",
		"MYR",
		"MZN",
		"NAD",
		"NGN",
		"NIO",
		"NOK",
		"NPR",
		"NZD",
		"PAB",
		"PEN",
		"PGK",
		"PHP",
		"PKR",
		"PLN",
		"PYG",
		"QAR",
		"RON",
		"RSD",
		"RUB",
		"RWF",
		"SAR",
		"SBD",
		"SCR",
		"SEK",
		"SGD",
		"SHP",
		"SLL",
		"SOS",
		"SRD",
		"STD",
		"SVC",
		"SYP",
		"SZL",
		"THB",
		"TJS",
		"TOP",
		"TRY",
		"TTD",
		"TWD",
		"TZS",
		"UAH",
		"UGX",
		"USD",
		"UYU",
		"UZS",
		"VEF",
		"VND",
		"VUV",
		"WST",
		"XAF",
		"XCD",
		"XOF",
		"XPF",
		"YER",
		"ZAR",
		"ZMK",
		"ZWD",
	]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if not self.is_new():
			self.configure_braintree()

	def validate(self):
		if not self.flags.ignore_mandatory:
			self.configure_braintree()

	def on_update(self):
		create_payment_gateway(
			"Braintree-" + self.gateway_name,
			settings="Braintree Settings",
			controller=self.gateway_name,
		)
		call_hook_method("payment_gateway_enabled", gateway="Braintree-" + self.gateway_name)

	def configure_braintree(self):
		self.gateway = braintree.BraintreeGateway(
			braintree.Configuration(
				environment=braintree.Environment.Sandbox
				if self.use_sandbox
				else braintree.Environment.Production,
				merchant_id=self.merchant_id,
				public_key=self.public_key,
				private_key=self.get_password(fieldname="private_key", raise_exception=False),
			)
		)

	def generate_token(self, data=None):
		if data:
			self.data = frappe._dict(data)

		try:
			self.get_merchant_account()
			return self.gateway.client_token.generate({"merchant_account_id": self.merchant_account.id})
		except Exception as e:
			frappe.log_error(e, _("Client token generation issue"))

	def validate_transaction_currency(self, currency):
		if currency not in self.supported_currencies:
			frappe.throw(
				_(
					"Please select another payment method. Braintree does not support transactions in currency '{0}'"
				).format(currency)
			)

	def get_payment_url(self, **kwargs):
		return get_url(f"./braintree_checkout?{urlencode(kwargs)}")

	def create_payment_request(self, data):
		self.data = frappe._dict(data)

		try:
			self.integration_request = create_request_log(self.data, service_name="Braintree")
			return self.create_charge_on_braintree()

		except Exception:
			frappe.log_error(frappe.get_traceback())
			return {
				"redirect_to": frappe.redirect_to_message(
					_("Server Error"),
					_(
						"There seems to be an issue with the server's braintree configuration. Don't worry, in case of failure, the amount will get refunded to your account."
					),
				),
				"status": 401,
			}

	def get_merchant_account(self):
		result = self.gateway.merchant_account.all()
		matching_merchants = [
			x for x in result.merchant_accounts if x.currency_iso_code == self.data.currency
		]
		default_merchant = [y for y in matching_merchants if y.default] if matching_merchants else []

		if default_merchant:
			self.merchant_account = default_merchant[0]
		elif matching_merchants:
			self.merchant_account = matching_merchants[0]

		if not hasattr(self, "merchant_account"):
			frappe.log_error(_(f"Merchant account for currency {self.data.currency} missing"))

	def create_charge_on_braintree(self):
		self.get_merchant_account()

		if not hasattr(self, "merchant_account"):
			return {"redirect_to": "payment-failed", "status": "Error"}

		redirect_to = self.data.get("redirect_to") or None
		redirect_message = self.data.get("redirect_message") or None

		result = self.gateway.transaction.sale(
			{
				"amount": self.data.amount,
				"payment_method_nonce": self.data.payload_nonce,
				"options": {"submit_for_settlement": True},
				"merchant_account_id": self.merchant_account.id,
			}
		)

		if result.is_success:
			self.integration_request.db_set("status", "Completed", update_modified=False)
			self.flags.status_changed_to = "Completed"
			self.integration_request.db_set(
				"output", result.transaction.status, update_modified=False
			)

		elif result.transaction:
			self.integration_request.db_set("status", "Failed", update_modified=False)
			error_log = frappe.log_error(
				"code: "
				+ str(result.transaction.processor_response_code)
				+ " | text: "
				+ str(result.transaction.processor_response_text),
				"Braintree Payment Error",
			)
			self.integration_request.db_set("error", error_log.error, update_modified=False)
		else:
			self.integration_request.db_set("status", "Failed", update_modified=False)
			for error in result.errors.deep_errors:
				error_log = frappe.log_error(
					"code: " + str(error.code) + " | message: " + str(error.message),
					"Braintree Payment Error",
				)
				self.integration_request.db_set("error", error_log.error, update_modified=False)

		if self.flags.status_changed_to == "Completed":
			status = "Completed"
			if self.data.reference_doctype and self.data.reference_docname:
				custom_redirect_to = None
				try:
					custom_redirect_to = frappe.get_doc(
						self.data.reference_doctype, self.data.reference_docname
					).run_method("on_payment_authorized", self.flags.status_changed_to)
					braintree_success_page = frappe.get_hooks("braintree_success_page")
					if braintree_success_page:
						custom_redirect_to = frappe.get_attr(braintree_success_page[-1])(self.data)
				except Exception:
					frappe.log_error(frappe.get_traceback())

				if custom_redirect_to and custom_redirect_to != "no-redirection":
					redirect_to = custom_redirect_to

			redirect_url = "payment-success"
		else:
			status = "Error"
			redirect_url = "payment-failed"

		if redirect_to and redirect_to != "no-redirection":
			redirect_url += "?" + urlencode({"redirect_to": redirect_to})
		if redirect_message:
			redirect_url += "&" + urlencode({"redirect_message": redirect_message})

		return {"redirect_to": redirect_url, "status": status}

def get_gateway_controller(doc):
	payment_request = frappe.get_doc("Payment Request", doc)
	gateway_controller = frappe.db.get_value(
		"Payment Gateway", payment_request.payment_gateway, "gateway_controller"
	)
	return gateway_controller