import os
from cryptography.fernet import Fernet

_fernet = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.getenv("FERNET_SECRET_KEY")
        if not key:
            raise RuntimeError("FERNET_SECRET_KEY não configurada")
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_key(plain: str) -> str:
    if not plain:
        return plain
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_key(cipher: str) -> str:
    if not cipher:
        return cipher
    return _get_fernet().decrypt(cipher.encode()).decode()


def mask_key(cipher: str) -> str:
    if not cipher:
        return ""
    try:
        plain = decrypt_key(cipher)
        if len(plain) <= 8:
            return "***"
        return plain[:4] + "***" + plain[-4:]
    except Exception:
        return "***"
