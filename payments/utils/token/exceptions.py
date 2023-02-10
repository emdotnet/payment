from typing import Collection
from frappe import ValidationError


class _KeysException(ValidationError):
	TITLE: str

	def __init__(self, keys: Collection[str], why = "") -> None:
		super().__init__(self.TITLE + ": " + ", ".join(sorted(keys)) + (f", why={why}" if why else ""))
		self.keys = keys
		self.why = why

	def __init_subclass__(cls, title: str) -> None:
		cls.TITLE = title
		return super().__init_subclass__()

class MissingKeys(_KeysException, title="Missing keys"):
	pass

class InvalidKeys(_KeysException, title="Invalid keys"):
	pass

class ExtraKeys(_KeysException, title="Extra keys"):
	pass

class MissingValues(_KeysException, title="Missing values"):
	pass
