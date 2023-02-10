import frappe

from payments.payment_gateways.doctype.stripe_settings.api.errors import handle_stripe_errors
from payments.payment_gateways.doctype.stripe_settings.idempotency import IdempotencyKey, handle_idempotency


class StripeCustomer:
	def __init__(self, gateway):
		self.gateway = gateway

	@handle_stripe_errors
	def get_or_create(self, customer_docname, stripe_id=None):
		if not stripe_id:
			stripe_id = frappe.db.get_value(
				"Integration References",
				dict(customer=customer_docname, stripe_settings=self.gateway.name),
				"stripe_customer_id",
			)

		if stripe_id:
			customer = self.get(stripe_id)
			if not customer.get("deleted"):
				return customer

		return self.create(customer_docname)

	def get(self, stripe_id):
		return self.gateway.stripe.Customer.retrieve(stripe_id)

	@handle_idempotency
	@handle_stripe_errors
	def create(self, customer_docname, **kwargs):
		from frappe.contacts.doctype.contact.contact import get_default_contact

		metadata = {"customer": customer_docname}
		customer_name = frappe.db.get_value("Customer", customer_docname, "customer_name")
		contact = get_default_contact("Customer", customer_docname)
		contact_email = frappe.db.get_value("Contact", contact, "email_id")

		if customer_name:
			stripe_customer = self.gateway.stripe.Customer.create(
				name=customer_name,
				email=contact_email,
				metadata=metadata,
				idempotency_key=IdempotencyKey("customer", "create", customer_docname).get(),
				**kwargs
			)

			return stripe_customer.id

	@handle_stripe_errors
	def update(self, stripe_id, **kwargs):
		return self.gateway.stripe.Customer.modify(stripe_id, **kwargs)

	@handle_stripe_errors
	def delete(self, stripe_id):
		return self.gateway.stripe.Customer.delete(stripe_id)

	def register(self, stripe_id, customer_docname):
		existing = frappe.db.exists(
			"Integration References",
			dict(customer=customer_docname),
		)
		data = {
			"stripe_settings": self.gateway.name,
			"stripe_customer_id": stripe_id,
		}

		if existing:
			doc = frappe.get_doc("Integration References", existing)
			doc.update(data)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(
				{
					"doctype": "Integration References",
					"customer": customer_docname,
					**data
				}
			).insert(ignore_permissions=True)
			frappe.db.commit()

	@handle_stripe_errors
	def update_default_payment_method(self, stripe_id, payment_method_id):
		return self.gateway.stripe.Customer.modify(
			stripe_id,
			invoice_settings=dict(default_payment_method=payment_method_id),
		)
