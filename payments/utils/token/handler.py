from typing import Literal, TYPE_CHECKING

import frappe

from payments.utils.token.methods import TokenMethodJWT, TokenMethodCompressed, InvalidTokenError
from payments.utils.token.exceptions import *

if TYPE_CHECKING:
	from typing import Type
	from payments.utils.token.validator import _BaseDataValidator
	from payments.utils.token.methods import _BaseTokenMethod

class _BaseTokenHandler:
	DEFAULT_TOKEN_ENCODER = TokenMethodJWT

	# Methods to be implemented by subclasses
	def get_secret(self) -> str:
		raise NotImplementedError

	def get_validator(self, data: dict) -> "_BaseDataValidator":
		if frappe.flags.in_test and data and data.get("mode", None) == "test":
			from payments.utils.token.validator import ValidatorForTests
			return ValidatorForTests()
		raise NotImplementedError

	def _get_token_decoder(self, tok: str) -> "Type[_BaseTokenMethod]":
		if tok.startswith("c."):
			return TokenMethodCompressed
		return TokenMethodJWT

	def _get_token_encoder(self, data: dict) -> "Type[_BaseTokenMethod]":
		return self.DEFAULT_TOKEN_ENCODER

	def _encode_to_token(self, data: dict) -> str:
		encoder_cls = self._get_token_encoder(data)
		encoder = encoder_cls(self.get_secret())
		return encoder.encode(data)

	def _decode_from_token(self, tok: str, verify=True) -> dict:
		if tok == "":
			raise ValueError("Empty token")
		elif not isinstance(tok, str):
			raise ValueError(f"Invalid token type: {type(tok)}")

		decoder_cls = self._get_token_decoder(tok)
		decoder = decoder_cls(self.get_secret())
		return decoder.decode(tok, verify=verify)

	def decode(self, data: dict) -> dict:
		"""Decodes a dict of query params into a dict with valid business data
		A validation step is performed to ensure the data contains the right keys.

		Args:
				data: The query params to decode, probably including a token

		Returns:
				dict: The decoded data
		"""
		try:
			inp = data
			if token := inp.get("token", None):
				inp = self._decode_from_token(token)

			inp = self.get_validator(inp).update_incoming(inp) or inp
			return inp
		except frappe.ValidationError as exc:
			self.log_invalid_url(data=data, exc=exc)
			raise InvalidTokenError(data) from exc

	def encode(self, data: dict) -> dict:
		"""Transform a dict with business data into a dict of query params.

		Args:
				data (dict): The relevant data to encode

		Returns:
				dict: A dict of query params to be stored in a URL
		"""

		out = self.get_validator(data).update_outgoing(data) or data
		token = self._encode_to_token(out)
		if token:
			out = { "token": token }  # The `token` must be the only key in the dict
		return out

	def log_invalid_url(self, data: dict, exc: Exception = None, title="Invalid URL"):
		try:
			url = frappe.request.url
		except Exception:
			url = "No URL"
		_log_invalid_url(url=url, token_handler=self, data=data, exc=exc, title=title)

def _get_token_debug_info(token_handler: _BaseTokenHandler, data: dict):
	if not data:
		return {"error": "No data"}
	if not isinstance(data, dict):
		return {"error": f"Invalid data type: {type(data)}"}

	if token := data.get("token", None):
		if not isinstance(token, str):
			return {"error": f"Invalid token type: {type(token)}"}
		decoded = None
		try:
			decoded = token_handler._decode_from_token(token, verify=False)
			decoded = token_handler._decode_from_token(token, verify=True)
			return {"ok": True, "token": token, "decoded": decoded}
		except Exception as e:
			return {"error": f"Error while decoding token: {token}", "exception": repr(e), "decoded": decoded}
	else:
		return {"error": "No token"}
	raise NotImplementedError

def _log_invalid_url(url: str, token_handler: _BaseTokenHandler, data: dict, exc: Exception, title=""):
	title = title or frappe._("Invalid token URL")
	msg = "\n\n".join((
		title,
		url,
		"Error: " + repr(exc),
		"Source data: " + frappe.as_json(data),
		"Token handler: " + repr(token_handler),
		"Token debug info: " + frappe.as_json(_get_token_debug_info(token_handler, data)),
		"Stacktrace: " + frappe.get_traceback(),
	))
	frappe.log_error(title[:140], msg)

class UnsafeTokenHandler(_BaseTokenHandler):
	def get_secret(self) -> str:
		return "NO SECRET - UNSAFE TOKEN HANDLER"

	def _decode_from_token(self, tok: str, verify: Literal[False]) -> dict:
		return super()._decode_from_token(tok, verify=False)

	def _encode_to_token(self, data: dict) -> str:
		raise NotImplementedError("UnsafeTokenHandler does not support encoding")

	def encode(self, data: dict):
		raise NotImplementedError("UnsafeTokenHandler does not support encoding")
