import click
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


class PaymentGatewayController(Document):
	def finalize_request(self, reference_no=None):
		redirect_to = self.data.get("redirect_to")
		redirect_message = self.data.get("redirect_message")

		if (
			self.flags.status_changed_to in ["Completed", "Autorized", "Pending"]
			and self.reference_document
		):
			custom_redirect_to = None
			try:
				custom_redirect_to = self.reference_document.run_method(
					"on_payment_authorized", self.flags.status_changed_to, reference_no
				)
			except Exception:
				frappe.log_error(frappe.get_traceback(), _("Payment custom redirect error"))

			if custom_redirect_to and custom_redirect_to != "no-redirection":
				redirect_to = custom_redirect_to

			redirect_url = self.redirect_url if self.get("redirect_url") else "/payment-success"

		else:
			redirect_url = "/payment-failed"

		if redirect_to and redirect_to != "no-redirection":
			redirect_url += "?" + urlencode({"redirect_to": redirect_to})
		if redirect_message:
			redirect_url += "&" + urlencode({"redirect_message": redirect_message})

		return {"redirect_to": redirect_url, "status": self.integration_request.status}

	def change_integration_request_status(self, status, error_type, error):
		if hasattr(self, "integration_request"):
			self.flags.status_changed_to = status
			self.integration_request.db_set("status", status, update_modified=True)
			self.integration_request.db_set(error_type, error, update_modified=True)

		if hasattr(self, "update_reference_document_status"):
			self.update_reference_document_status(status)


def get_payment_gateway_controller(payment_gateway):
	"""Return payment gateway controller"""
	gateway = frappe.get_doc("Payment Gateway", payment_gateway)
	if gateway.gateway_controller is None:
		try:
			return frappe.get_doc(f"{payment_gateway} Settings")
		except Exception:
			frappe.throw(_("{0} Settings not found").format(payment_gateway))
	else:
		try:
			return frappe.get_doc(gateway.gateway_settings, gateway.gateway_controller)
		except Exception:
			frappe.throw(_("{0} Settings not found").format(payment_gateway))


def get_gateway_controller(doctype, docname):
	payment_gateway = frappe.db.get_value(doctype, docname, "payment_gateway")
	gateway_controller = frappe.db.get_value(
		"Payment Gateway", payment_gateway, "gateway_controller"
	)
	return gateway_controller


@frappe.whitelist(allow_guest=True, xss_safe=True)
def get_checkout_url(**kwargs):
	try:
		if kwargs.get("payment_gateway"):
			doc = frappe.get_doc("{} Settings".format(kwargs.get("payment_gateway")))
			return doc.get_payment_url(**kwargs)
		else:
			raise Exception
	except Exception:
		frappe.respond_as_web_page(
			_("Something went wrong"),
			_(
				"Looks like something is wrong with this site's payment gateway configuration. No payment has been made."
			),
			indicator_color="red",
			http_status_code=frappe.ValidationError.http_status_code,
		)


def create_payment_gateway(gateway, settings=None, controller=None):
	# NOTE: we don't translate Payment Gateway name because it is an internal doctype
	if not frappe.db.exists("Payment Gateway", gateway):
		payment_gateway = frappe.get_doc(
			{
				"doctype": "Payment Gateway",
				"gateway": gateway,
				"gateway_settings": settings,
				"gateway_controller": controller,
			}
		)
		payment_gateway.insert(ignore_permissions=True)

def after_migrate():
	make_custom_fields()

def make_custom_fields():
	click.secho("* Updating Payment Custom Fields in Web Form")
	create_custom_fields(get_custom_fields())
	frappe.clear_cache(doctype="Web Form")

def get_custom_fields():
	return {
		'Web Form': [
			{
				"fieldname": "payments_tab",
				"fieldtype": "Tab Break",
				"label": "Payments",
				"insert_after": "custom_css"
			},
			{
				"default": "0",
				"fieldname": "accept_payment",
				"fieldtype": "Check",
				"label": "Accept Payment",
				"insert_after": "payments_tab"
			},
			{
				"depends_on": "accept_payment",
				"fieldname": "payment_gateway",
				"fieldtype": "Link",
				"label": "Payment Gateway",
				"options": "Payment Gateway",
				"insert_after": "accept_payment"
			},
			{
				"default": "Pay now",
				"depends_on": "accept_payment",
				"fieldname": "payment_button_label",
				"fieldtype": "Data",
				"label": "Button Label",
				"insert_after": "payment_gateway",
				"translatable": "1",
			},
			{
				"depends_on": "accept_payment",
				"fieldname": "payment_button_help",
				"fieldtype": "Text",
				"label": "Button Help",
				"insert_after": "payment_button_label"
			},
			{
				"fieldname": "payments_cb",
				"fieldtype": "Column Break",
				"insert_after": "payment_button_help"
			},
			{
				"default": "0",
				"depends_on": "accept_payment",
				"fieldname": "amount_based_on_field",
				"fieldtype": "Check",
				"label": "Amount Based On Field",
				"insert_after": "payments_cb"
			},
			{
				"depends_on": "eval:doc.accept_payment && doc.amount_based_on_field",
				"fieldname": "amount_field",
				"fieldtype": "Select",
				"label": "Amount Field",
				"insert_after": "amount_based_on_field",
				"translatable": "0",
			},
			{
				"depends_on": "eval:doc.accept_payment && !doc.amount_based_on_field",
				"fieldname": "amount",
				"fieldtype": "Currency",
				"label": "Amount",
				"insert_after": "amount_field",
				"translatable": "0",
			},
			{
				"default": "0",
				"depends_on": "accept_payment",
				"fieldname": "currency_based_on_field",
				"fieldtype": "Check",
				"label": "Currency Based On Field",
				"insert_after": "amount"
			},
			{
				"depends_on": "eval:doc.accept_payment && doc.currency_based_on_field",
				"fieldname": "currency_field",
				"fieldtype": "Select",
				"label": "Currency Field",
				"insert_after": "currency_based_on_field",
				"translatable": "0",
			},
			{
				"depends_on": "eval:doc.accept_payment && !doc.currency_based_on_field",
				"fieldname": "currency",
				"fieldtype": "Link",
				"label": "Currency",
				"options": "Currency",
				"insert_after": "currency_field",
				"translatable": "0",
			},
		],
	}


def delete_custom_fields():
	if frappe.get_meta("Web Form").has_field("payments_tab"):
		click.secho("* Uninstalling Payment Custom Fields from Web Form")

		fieldnames = (
			"payments_tab",
			"accept_payment",
			"payment_gateway",
			"payment_button_label",
			"payment_button_help",
			"payments_cb",
			"amount_field",
			"amount_based_on_field",
			"amount",
			"currency",
		)

		for fieldname in fieldnames:
			frappe.db.delete("Custom Field", {"name": "Web Form-" + fieldname})

		frappe.clear_cache(doctype="Web Form")

def before_install():
	# TODO: remove this
	# This is done for erpnext CI patch test
	#
	# Since we follow a flow like install v14 -> restore v10 site
	# -> migrate to v12, v13 and then v14 again
	#
	# This app fails installing when the site is restored to v10 as
	# a lot of apis don;t exist in v10 and this is a (at the moment) required app for erpnext.
	if not frappe.get_meta("Module Def").has_field("custom"):
		return False
