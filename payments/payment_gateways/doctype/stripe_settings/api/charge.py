import frappe

from payment.payment_gateways.doctype.stripe_settings.api.errors import handle_stripe_errors


class StripeCharge:
	def __init__(self, gateway):
		self.gateway = gateway

	@handle_stripe_errors
	def retrieve(self, id):
		return self.gateway.stripe.Charge.retrieve(id, expand=["balance_transaction"])
