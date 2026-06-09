"""Symmetric encryption for credentials/tokens at rest.

Run ``python -m app.crypto`` to generate a fresh FERNET_KEY for your .env.
"""
from __future__ import annotations

from cryptography.fernet import Fernet


class Crypto:
    def __init__(self, key: str) -> None:
        self._f = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._f.decrypt(token.encode()).decode()


if __name__ == "__main__":
    print(Fernet.generate_key().decode())
