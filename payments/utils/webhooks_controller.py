import frappe

def handle_webhooks(handlers, **kwargs):
	integration_request = frappe.get_doc(kwargs.get("doctype"), kwargs.get("docname"))

	if handlers.get(integration_request.get("service_document")):
		handlers.get(integration_request.get("service_document"))(**kwargs)
	else:
		integration_request.db_set("error", _("This type of event is not handled"))
		integration_request.update_status({}, "Not Handled")