// Copyright (c) 2017, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Stripe Settings', {
	refresh: function(frm) {
		frm.add_custom_button(__('Create Stripe Webhooks'), () => {
			frappe.confirm(
				__("Configure webhooks on your Stripe Dashboard"),
				() => {
					frappe.call({
						method:"payments.payment_gateways.doctype.stripe_settings.stripe_settings.create_delete_webhooks",
						args: {
							settings: frm.doc.name,
							action: "create"
						}
					}).done((r) => {
						if (r&&r.message) {
							frappe.show_alert({
								"message": __("Webhooks creation in progress"),
								"indicator": "green"
							})
							frm.reload_doc()
						} else {
							frappe.show_alert({
								"message": __("Webhooks creation failed. Please check the error logs"),
								"indicator": "red"
							})
						}
					});
				}
			);
		}, __("Webhooks"));


		frm.add_custom_button(__('Delete Stripe Webhooks'), () => {
			frappe.confirm(
				__("Delete webhooks configured on your Stripe Dashboard"),
				() => {
					frappe.call({
						method:"payments.payment_gateways.doctype.stripe_settings.stripe_settings.create_delete_webhooks",
						args: {
							settings: frm.doc.name,
							action: "delete"
						}
					}).done((r) => {
						if (r&&r.message) {
							frappe.show_alert({
								"message": __("Webhooks deletion in progress"),
								"indicator": "green"
							})
							frm.reload_doc()
						} else {
							frappe.show_alert({
								"message": __("Webhooks deletion failed. Please check the error logs"),
								"indicator": "red"
							})
						}
					});
				}
			);
		}, __("Webhooks"));
	}
});
