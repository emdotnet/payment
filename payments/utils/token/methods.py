from hashlib import sha256
from zlib import compress, decompress
import hmac
import json

# from base64 import urlsafe_b64decode, urlsafe_b64encode
from jwt.utils import base64url_decode, base64url_encode
import jwt

class InvalidTokenError(Exception):
	pass

class _BaseTokenMethod:
	def encode(self, data: dict) -> str:
		raise NotImplementedError

	def decode(self, tok: str, verify=True) -> dict:
		raise NotImplementedError

class TokenMethodJWT(_BaseTokenMethod):
	JWT_ALGO = "HS256"

	def __init__(self, secret: str) -> None:
		self.secret = secret

	def encode(self, data: dict) -> str:
		print("encode", data)
		return jwt.encode(data, self.secret, algorithm=self.JWT_ALGO)

	def decode(self, tok: str, verify=True) -> dict:
		return jwt.decode(tok, self.secret, algorithms=[self.JWT_ALGO], options={"verify_signature": verify})

class TokenMethodCompressed(_BaseTokenMethod):
	CTOKEN_ALGO = sha256

	def __init__(self, secret: str) -> None:
		self.secret = secret

	def _ctok_sign(self, data: bytes):
		key = self.secret.encode("utf-8")
		return hmac.new(key, data, self.CTOKEN_ALGO).digest()

	def _ctok_verify(self, data: bytes, signature: bytes):
		return hmac.compare_digest(signature, self._ctok_sign(data))

	def encode(self, data: dict) -> str:
		# bytes
		payload = json.dumps(data, separators=(",", ":"), sort_keys=True, indent=None, ensure_ascii=False).encode("utf-8")
		signature = self._ctok_sign(payload)
		compressed = compress(payload, level=9)
		# base64 strings
		compressed_b64 = base64url_encode(compressed).decode("ascii")
		signature_b64 = base64url_encode(signature).decode("ascii")
		ctoken = f"c.{compressed_b64}.{signature_b64}"

		if not self._ctok_verify(payload, signature):
			raise ValueError("Unable to create valid token (sig): " + ctoken)
		if data != self.decode(ctoken, verify=True):
			raise ValueError("Unable to create valid token (dat): " + ctoken, data, self.decode(ctoken, verify=True))
		return ctoken

	def decode(self, tok: str, verify=True) -> dict:
		if not tok.startswith("c."):
			return TokenMethodJWT(self.secret).decode(tok, verify=verify)  # fallback to JWT

		if not (0 < len(tok) < 8000):
			raise ValueError("Invalid token length")
		# bytes
		compressed_b64, signature_b64 = tok[2:].split(".")
		compressed = base64url_decode(compressed_b64)
		signature = base64url_decode(signature_b64)
		payload = decompress(compressed)
		# verify signature
		if verify and not self._ctok_verify(payload, signature):
			raise ValueError("Invalid signature")

		# raw data
		decoded = json.loads(payload)
		if not isinstance(decoded, dict):
			raise ValueError("Invalid payload")
		return decoded

class TokenMethodUnsafe(_BaseTokenMethod):
	def encode(self, data: dict) -> str:
		raise NotImplementedError("Unsafe token method cannot be used to encode data.")

	def decode(self, tok: str) -> dict:
		raise NotImplementedError("Unsafe token method cannot be used to decode data.")
