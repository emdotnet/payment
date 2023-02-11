import frappe

from payments.payment_gateways.doctype.stripe_settings.stripe_settings import create_delete_webhooks

def execute():
	for stripe_settings in frappe.get_all("Stripe Settings"):
		create_delete_webhooks(stripe_settings.name, "delete")
		create_delete_webhooks(stripe_settings.name, "create")
