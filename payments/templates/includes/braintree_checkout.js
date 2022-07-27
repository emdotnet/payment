const submitButton = document.querySelector('#submit-button');
const data = {{ frappe.form_dict | json }};

const threeDSecureParameters = {
	amount: "{{ amount }}",
	email: "{{ payer_email }}"
}

braintree.dropin.create({
	authorization: "{{ client_token }}",
	selector: '#dropin-container',
	threeDSecure: true,
	paypal: {
		flow: 'vault'
	},
	locale: "{{ locale }}"
}).then(function(instance) {
	submitButton.addEventListener('click', function(e) {
		e.preventDefault();
		instance.requestPaymentMethod({
			threeDSecure: threeDSecureParameters
		}).then(function (payload) {
			if (payload.liabilityShifted || payload.type=="PayPalAccount") {
				submitPayment(payload);
			} else if (payload.liabilityShiftPossible) {
				submitPayment(payload);
			} else {
				$('#warning-msg').html(__("The bank could not authenticate this card. Please try again or contact your bank."));
				$('.warning').show();
				instance.clearSelectedPaymentMethod();
			}
		}).catch(function (error) {
			processError(error)
		});
	});

	instance.on('paymentMethodRequestable', function (event) {
		submitButton.removeAttribute('disabled');
	});

	instance.on('noPaymentMethodRequestable', function () {
		submitButton.setAttribute('disabled', 'disabled');
	});
}).catch(function (error) {
	processError(error)
});

const submitPayment = payload => {
	frappe.call({
		method: "frappe.templates.pages.integrations.braintree_checkout.make_payment",
		freeze: true,
		headers: { "X-Requested-With": "XMLHttpRequest" },
		args: {
			"payload_nonce": payload.nonce,
			"data": data,
		}
	})
	.then(r => {
		if (r.message && r.message.status == "Completed") {
			window.location.href = r.message.redirect_to
		} else if (r.message && r.message.status == "Error") {
			window.location.href = r.message.redirect_to
		}
	})
}

const processError = error => {
	submitButton.style.display = "none"
	$('#error-msg').html(error.message);
	$('.error').show()
}
