"""Encrypts the stored YouTube credentials.

Argon2id turns CREDENTIALS_SECRET (plus a random salt kept with the data) into a 32-byte key, and that key
encrypts the data with Fernet. A stored value looks like "<salt>.<encrypted data>".
"""
import base64
import json
import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.fernet import Fernet

from config import CREDENTIALS_SECRET


def _fernet(salt: bytes) -> Fernet:
    if not CREDENTIALS_SECRET:
        raise RuntimeError("CREDENTIALS_SECRET must be set")
    key = hash_secret_raw(
        secret=CREDENTIALS_SECRET.encode(), salt=salt,
        time_cost=3, memory_cost=19456, parallelism=1, hash_len=32, type=Type.ID,   # memory_cost is in KiB (19 MiB)
    )
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(data: dict) -> str:
    salt = os.urandom(16)
    token = _fernet(salt).encrypt(json.dumps(data).encode())
    return f"{base64.urlsafe_b64encode(salt).decode()}.{token.decode()}"


def decrypt(stored: str) -> dict:
    salt, token = stored.split(".", 1)
    return json.loads(_fernet(base64.urlsafe_b64decode(salt)).decrypt(token.encode()))
