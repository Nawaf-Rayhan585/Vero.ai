from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().camera_credentials_key.encode())


def encrypt_password(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_password(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
