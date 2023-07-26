import unittest

from typing import Type

from .handler import _BaseTokenHandler
from .methods import TokenMethodJWT, TokenMethodCompressed, _BaseTokenMethod
from .validator import ValidatorForTests

class MockTokenHandler(_BaseTokenHandler):
	def __init__(self, encoder: Type[_BaseTokenMethod] = None, decoder: Type[_BaseTokenMethod] = None) -> None:
		super().__init__()

		self._encoder = encoder
		self._decoder = decoder

	def _encode_to_token(self, data: dict) -> str:
		if self._encoder:
			return self._encoder(self.get_secret()).encode(data)
		return super()._encode_to_token(data)

	def _decode_from_token(self, tok: str, verify=True) -> dict:
		if self._decoder:
			return self._decoder(self.get_secret()).decode(tok, verify=verify)
		return super()._decode_from_token(tok, verify)

	def get_secret(self) -> str:
		return "my-test-secret"

	def get_validator(self, data: dict):
		return ValidatorForTests()

	def log_invalid_url(self, data: dict, exc: Exception = None, title="Invalid URL"):
		print(title, exc, data)

class TestToken(unittest.TestCase):
	def test_jwt(self):
		raw_data = {
			"mode": "test",
			"key1": "value1",
			"key2": "value2",
		}

		th = MockTokenHandler(encoder=TokenMethodJWT, decoder=TokenMethodJWT)
		self.assertEqual(th.get_secret(), "my-test-secret")

		token = th._encode_to_token(raw_data)
		# cannot assert full string, as it only works with deterministic json key order
		# self.assertEqual(
		# 	token,
		# 	"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtb2RlIjoidGVzdCIsImtleTEiOiJ2YWx1ZTEiLCJrZXkyIjoidmFsdWUyIn0.os8OQd6PP9yhN3yU-ufI8gVqIk_cbFZsySPQbwWt5Ms"
		# )

		decoded = th._decode_from_token(token)
		self.assertDictEqual(decoded, raw_data)

	def test_jwt_decode(self):
		th = MockTokenHandler(encoder=TokenMethodJWT, decoder=TokenMethodJWT)
		query_params = {
			"token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtb2RlIjoidGVzdCIsImtleTEiOiJ2YWx1ZTEiLCJrZXkyIjoidmFsdWUyIn0.os8OQd6PP9yhN3yU-ufI8gVqIk_cbFZsySPQbwWt5Ms",
		}

		self.assertDictEqual(th.decode(query_params), {
			"mode": "test",
			"key1": "value1",
			"key2": "value2",
		})

	def test_compressed_token(self):
		raw_data = {
			"mode": "test",
			"key1": "value1",
			"key2": "value2",
		}

		th = MockTokenHandler(encoder=TokenMethodCompressed, decoder=TokenMethodCompressed)
		ctoken = th._encode_to_token(raw_data)
		self.assertEqual(
			ctoken,
			"c.eNqrVspOrTRUslIqS8wpTTVU0gHxjWB8IyA_Nz8lFcgvSS0uUaoFAFm1Do4.65ZCydYX1UAQ-gpCDej_iiVPTWQ4S68YlQ4bG-9FYFI"
		)

		decoded = th._decode_from_token(ctoken)
		self.assertDictEqual(decoded, raw_data)

	def test_compressed_token_with_float(self):
		raw_data = {
			"mode": "test",
			"key1": "value1",
			"key2": 592.80 * 100.0,  # 59279.99999999999
		}

		th = MockTokenHandler(encoder=TokenMethodCompressed, decoder=TokenMethodCompressed)
		ctoken = th._encode_to_token(raw_data)
		decoded = th._decode_from_token(ctoken)
		self.assertDictEqual(decoded, raw_data)
		self.assertEqual(decoded["key2"], 592.80 * 100.0)

	"""
	def test_compressed_token_large(self):
		import random
		import string

		def random_string(length):
			letters = string.ascii_lowercase
			return ''.join(random.choice(letters) for i in range(length))

		raw_data = {
			"mode": "test",
			"key1": "value1",
			"key2": random_string(1000),
		}

		th = MockTokenHandler(encoder=TokenMethodCompressed, decoder=TokenMethodCompressed)
		ctoken = th._encode_to_token(raw_data)

		# print("Token length (non-deterministic):", len(ctoken))
		# print("JSON length:", len(json.dumps(raw_data)))

		decoded = th._decode_from_token(ctoken)
		self.assertDictEqual(decoded, raw_data)
	"""
