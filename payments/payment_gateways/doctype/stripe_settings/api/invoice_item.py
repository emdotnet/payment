import frappe

from payments.payment_gateways.doctype.stripe_settings.api.errors import handle_stripe_errors
from payments.payment_gateways.doctype.stripe_settings.idempotency import IdempotencyKey, handle_idempotency


class StripeInvoiceItem:
	def __init__(self, gateway):
		self.gateway = gateway

	@handle_idempotency
	@handle_stripe_errors
	def create(self, customer, **kwargs):
		return self.gateway.stripe.InvoiceItem.create(
			customer=customer,
			idempotency_key=IdempotencyKey(
				"invoice_item", "create", frappe.scrub(kwargs["description"])
			).get(),
			**kwargs
		)

	@handle_stripe_errors
	def retrieve(self, id):
		return self.gateway.stripe.InvoiceItem.retrieve(id)
