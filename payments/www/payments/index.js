frappe.ready(() => {
	document.getElementById("payment-method-selection-page").addEventListener('click', (e) => {
		const isButton = e.target.nodeName === 'BUTTON'; 

		if (!isButton || !e.target.getAttribute("data-payment-gateway")) {
			return;
		}
		
		e.target.disabled = true;
		e.target.innerHTML = __("Redirecting...")

		frappe.call({
			method: "payments.www.payments.index.get_payment_url",
			args: {
				reference_doctype: e.target.getAttribute("data-reference_doctype"),
				reference_name: e.target.getAttribute("data-reference_name"),
				gateway: e.target.getAttribute("data-payment-gateway")
			}
		}).then(r => {
			if (r.message) {
				window.location.href = r.message;
			} else {
				frappe.msgprint(__("An error occured. <br>Please contact us."))
			}
		})
	})
})