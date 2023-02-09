import frappe

from typing import Literal, TYPE_CHECKING

from payments.utils.token.exceptions import InvalidKeys, MissingKeys, MissingValues
from payments.utils.token.handler import UnsafeTokenHandler

if TYPE_CHECKING:
	from payments.utils.token.handler import _BaseTokenHandler

def _is_linked_to_subscription(reference_doctype: str, reference_docname: str) -> bool:
	"""Check if the reference document is or is linked to a Subscription.
	- `True` if the doctype is `Subscription`.
	- `True` is the document has a non-empty `subscription` field.
	- `False` otherwise.
	"""

	if reference_doctype == "Subscription":
		return True

	meta = frappe.get_meta(reference_doctype)
	if meta.has_field("subscription") and frappe.db.exists(reference_doctype, reference_docname):
		value = frappe.db.get_value(reference_doctype, reference_docname, "subscription")
		if value:
			return True

	return False


def infer_stripe_mode_from_data(*, data: dict, token_handler: "_BaseTokenHandler | None" = None):
	"""Use this function to automatically determine the mode of a Stripe payment based on the data.

	Args:
		data (dict): The data to infer the mode from, most likely a dict of query params, including a "token" field. If there is a token, the `mode` must be in the decoded data. In other words, the `token` must be the only key in the data.
		token_handler (_BaseTokenHandler, optional): A class that can decode a token. Use `UnsafeTokenHandler` if you don't yet have a token handler, as further checking is always done by the final TokenHandler you will use. Defaults to None (only handles non-token data).

	Raises:
		ValueError

	Returns:
		"payment" | "payment+setup" | "setup"
	"""

	if not isinstance(data, dict):
		raise ValueError(f"Invalid data type: {type(data)}, expected dict")

	if token := data.get("token"):
		if token_handler:
			decoded_data = token_handler._decode_from_token(token, verify=False)
			data = decoded_data
			# return infer_mode_from_data(token_handler=token_handler, data=decoded_data)

	if mode := data.get("mode"):
		if mode in ("payment", "setup", "payment+setup"):
			return mode
		if mode == "test" and frappe.flags.in_test:
			return mode

	ref_doc = (data.get("reference_doctype"), data.get("reference_docname"))
	if all(ref_doc) and _is_linked_to_subscription(*ref_doc):
		return "payment+setup"

	# Legacy
	if data.get("amount"):
		return "payment"

	raise ValueError("No valid `mode` found in/for data: " + frappe.as_json(data))


def infer_stripe_gateway_controller_from_data(data: dict):
	DOC_KEYS = ("reference_doctype", "reference_docname")
	ref_doc: tuple[str]

	if isinstance(token := data.get("token"), str):
		# Problem: To get the secret (arbitrarily chosen to be the secret_key of the payment gateway controller),
		# we need to get the gateway controller, so we need to know the reference document,
		# so we need to decode the token. Thus, to decode the token we need to decode the token.
		# Solution: Decode the token without verification, then use the decoded data to get the reference document.
		unsafe_decoded = UnsafeTokenHandler()._decode_from_token(token, verify=False)
		ref_doc = tuple(unsafe_decoded.get(k) for k in DOC_KEYS)
	else:
		ref_doc = tuple(data.get(k) for k in DOC_KEYS)

	_validate_ref_doc_keys(DOC_KEYS, ref_doc)

	from payments.utils.utils import get_gateway_controller
	gateway_controller = get_gateway_controller(*ref_doc)
	if not gateway_controller:
		meta = frappe.get_meta(ref_doc[0])
		if not meta.has_field("payment_gateway"):
			raise ValueError(f"Reference document {': '.join(ref_doc)} has no `payment_gateway` field")

		doc = frappe.get_doc(ref_doc[0], ref_doc[1])  # Raises frappe.DoesNotExistError

		pg = doc.get("payment_gateway")
		if not pg:
			msg = frappe._("Please set a payment gateway for reference document {0} {1}").format(
				frappe._(ref_doc[0]), ref_doc[1]
			)
			raise ValueError(msg)

		raise ValueError(f"Unable to find payment controller for reference document {': '.join(ref_doc)} (doc.payment_gateway={repr(pg)})")

	return gateway_controller

def _validate_ref_doc_keys(DOC_KEYS, ref_doc):
	missing_keys = [k for k, v in zip(DOC_KEYS, ref_doc) if v is None]
	if missing_keys:
		raise MissingKeys(missing_keys)

	empty_keys = [k for k, v in zip(DOC_KEYS, ref_doc) if not v]
	if empty_keys:
		raise MissingValues(empty_keys)

	invalid_keys = [k for k, v in zip(DOC_KEYS, ref_doc) if not isinstance(v, str)]
	if invalid_keys:
		why = "expected strings, got " + ", ".join(f"{k}: {type(v).__name__}" for k, v in zip(DOC_KEYS, ref_doc))
		raise InvalidKeys(invalid_keys, why)
