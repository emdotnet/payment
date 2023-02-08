import frappe

from payments.utils.token import _BaseDataValidator, _BaseTokenHandler, ValidatorForTests

from typing import TYPE_CHECKING, NoReturn

from payments.utils.token.inference import infer_stripe_mode_from_data, infer_stripe_gateway_controller_from_data
from payments.utils.token.methods import TokenMethodCompressed
if TYPE_CHECKING:
	from payments.payment_gateways.doctype.stripe_settings.stripe_settings import StripeSettings


class StripePaymentDataValidator(_BaseDataValidator):
	ALLOW_EXTRA_KEYS = "warn"
	REQUIRED_KEYS = {
		"amount",
		"title",
		"description",
		"reference_doctype",
		"reference_docname",
		"payer_name",
		"payer_email",
		"order_id",
		"currency",
		"redirect_to",
	}

class StripeSetupDataValidator(_BaseDataValidator):
	ALLOW_EXTRA_KEYS = True
	REQUIRED_KEYS = {
		"reference_doctype",
		"reference_docname",
		"payer_email",
	}

class _StripeTokenHandlerFromController(_BaseTokenHandler):
	DEFAULT_TOKEN_ENCODER = TokenMethodCompressed
	VALIDATORS: dict[str, _BaseDataValidator] = {
		"payment": StripePaymentDataValidator,
		"setup": StripeSetupDataValidator,
		"test": ValidatorForTests,  # NOTE: Only allowed in tests
	}

	def get_validator(self, data: dict) -> "_BaseDataValidator":
		mode = self.get_mode_for_data(data)
		if mode != "test" or frappe.flags.in_test:
			if validator := self.VALIDATORS.get(mode):
				return validator(token_handler=self)
		raise ValueError(f"Invalid mode: {mode}")

	def __init__(self, gateway_controller: "str | StripeSettings") -> None:
		super().__init__()
		if isinstance(gateway_controller, str):
			self.stripe_settings: "StripeSettings" = frappe.get_cached_doc("Stripe Settings", gateway_controller)
		else:
			self.stripe_settings = gateway_controller

		self.secret = self.stripe_settings.get_password("secret_key")

	def get_controller(self):
		return self.stripe_settings

	def get_secret(self) -> str:
		return self.secret

	def get_mode_for_data(self, data: dict):
		return infer_stripe_mode_from_data(data=data, token_handler=self)

	def log_invalid_url(self, **kwargs):
		super().log_invalid_url(**kwargs, title="Someone accessed an invalid Stripe checkout URL")

	def generate_query_params(self, data: dict):
		return self.encode(data=data)

class _StripeTokenHandlerFromData(_StripeTokenHandlerFromController):
	def __init__(self, default_data: dict, gateway_controller: "str | StripeSettings") -> None:
		super().__init__(gateway_controller=gateway_controller)
		self.default_data = default_data

	def get_mode(self):
		return self.get_mode_for_data(self.default_data)

	def decode(self, data: dict | None = None):
		return super().decode(data or self.default_data)

class StripeDataHandler:
	def __init__(self) -> NoReturn:
		raise NotImplementedError("StripeDataHandler can not be instantiated directly. Use StripeDataHandler.FromData or .FromController instead. This is because a data source/controller is needed to fetch the secret.")

	@classmethod
	def FromData(cls, data: dict):
		gateway_controller = infer_stripe_gateway_controller_from_data(data=data)
		return _StripeTokenHandlerFromData(default_data=data, gateway_controller=gateway_controller)

	@classmethod
	def FromController(cls, gateway_controller: "str | StripeSettings"):
		return _StripeTokenHandlerFromController(gateway_controller=gateway_controller)

	@classmethod
	def generate_query_params(cls, stripe_settings: "StripeSettings", data: dict):
		return cls.FromController(stripe_settings).generate_query_params(data=data)
