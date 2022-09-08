# Payments

Payments application for Dodock and Dokos

## Installation
1. Install [Dokos CLI & Dodock](https://doc.dokos.io/fr/getting-started).

2. Once setup is complete, add the payments app to your bench by running
    ```
    $ bench get-app payments --branch <version branch>
    ```

> Example: If you want to use this application with Dodock/Dokos v3, you should use branch `v3.x.x`  
> `$ bench get-app payments --branch v3.x.x`

3. Install the payments app on the required site by running
    ```
    $ bench --site <sitename> install-app payments
    ```

> Note: The application will be automatically installed if you install Dokos on your site.

## Content

This application contains integrations with the following payment gateways:

- [Braintree](https://www.braintreepayments.com/)
- [Paypal](https://www.paypal.com/)
- [Paytm](https://paytm.com/)
- [Razorpay](https://razorpay.com/)
- [Stripe](https://stripe.com/)

## License

MIT ([license.txt](license.txt))
