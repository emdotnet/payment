from payments.payment_gateways.doctype.stripe_settings.api.errors import handle_stripe_errors
from payments.payment_gateways.doctype.stripe_settings.idempotency import IdempotencyKey, handle_idempotency


class StripePaymentIntent:
	def __init__(self, gateway, reference=None):
		self.gateway = gateway
		self.reference = reference

	@handle_idempotency
	def create(self, amount, currency, **kwargs):
		return self.gateway.stripe.PaymentIntent.create(
			amount=amount,
			currency=currency,
			idempotency_key=IdempotencyKey("payment_intent", "create", self.reference).get(),
			**kwargs
		)

	@handle_stripe_errors
	def update(self, id, **kwargs):
		return self.gateway.stripe.PaymentIntent.modify(id, **kwargs)

	@handle_stripe_errors
	def confirm(self, id, **kwargs):
		return self.gateway.stripe.PaymentIntent.confirm(id, **kwargs)

	@handle_stripe_errors
	def capture(self, id, **kwargs):
		return self.gateway.stripe.PaymentIntent.attach(id, **kwargs)

	@handle_stripe_errors
	def cancel(self, id, **kwargs):
		return self.gateway.stripe.PaymentIntent.detach(id, **kwargs)
