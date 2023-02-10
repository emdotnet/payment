from payments.utils.token.exceptions import MissingKeys, ExtraKeys, MissingValues

class _BaseDataValidator(dict):
	ALLOW_EXTRA_KEYS = "error"
	REQUIRED_KEYS: set[str] = {}
	OPTIONAL_KEYS: set[str] = {}

	def update_outgoing(self, data: dict) -> dict:
		if self.ALLOW_EXTRA_KEYS in (False, "warn", "error"):
			expected_keys = set(self.REQUIRED_KEYS | self.OPTIONAL_KEYS | {"_payment_type"})
			extra_keys = set(data.keys()) - expected_keys
			if extra_keys:
				if self.ALLOW_EXTRA_KEYS == "error" or self.ALLOW_EXTRA_KEYS is False:
					raise ExtraKeys(extra_keys)
				elif self.ALLOW_EXTRA_KEYS == "warn":
					import frappe
					msg = "\n\n".join((
						f"Extra keys in data: {extra_keys}. ",
						f"Data: {data}",
					))
					frappe.log_error("Payments: Warning: Extra keys in data", msg)

		self._check_keys(data)
		return data

	def update_incoming(self, data: dict) -> dict:
		self._check_keys(data)
		return data

	def _check_keys(self, data: dict):
		missing_keys = set()
		empty_keys = set()
		for k in self.REQUIRED_KEYS:
			if k not in data:
				missing_keys.add(k)
			elif not data[k]:
				empty_keys.add(k)

		if missing_keys:
			raise MissingKeys(missing_keys)

		if empty_keys:
			raise MissingValues(empty_keys)

class ValidatorForTests(_BaseDataValidator):
	REQUIRED_KEYS = {
		"mode",
		"key1",
		"key2",
	}
