"""
Хеширование и проверка паролей.

Используем pbkdf2_hmac из стандартной библиотеки (без bcrypt/passlib),
чтобы не тянуть внешние C-зависимости, которые иногда проблемно собираются
на хостинге. Для MVP этого достаточно.
"""

import hashlib
import hmac
import os

_ITERATIONS = 200_000
_ALGO = "sha256"


def hash_password(password: str) -> str:
    """Возвращает строку вида 'salt$hash' (обе части — hex)."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, _ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Сравнивает пароль с сохранённым хешем, защищено от timing-атак."""
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, _ITERATIONS)
    return hmac.compare_digest(actual, expected)
