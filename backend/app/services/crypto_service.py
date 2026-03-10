"""AES-256 암복호화 서비스

금액, TOTP 시크릿 등 민감 데이터를 DB에 저장할 때 사용.
ENCRYPTION_KEY 환경변수에서 키를 읽어온다.
"""

import base64
import os
from decimal import Decimal

from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    """환경변수의 ENCRYPTION_KEY로 Fernet 인스턴스 생성."""
    key = settings.encryption_key.encode()
    return Fernet(key)


def encrypt_value(value: str) -> str:
    """문자열을 암호화하여 base64 인코딩된 문자열로 반환."""
    f = _get_fernet()
    encrypted = f.encrypt(value.encode())
    return encrypted.decode()


def decrypt_value(encrypted_value: str) -> str:
    """암호화된 문자열을 복호화."""
    f = _get_fernet()
    decrypted = f.decrypt(encrypted_value.encode())
    return decrypted.decode()


def encrypt_decimal(value: Decimal) -> str:
    """Decimal 값을 문자열로 변환 후 암호화."""
    return encrypt_value(str(value))


def decrypt_decimal(encrypted_value: str) -> Decimal:
    """암호화된 값을 복호화 후 Decimal로 변환."""
    return Decimal(decrypt_value(encrypted_value))


def encrypt_optional(value: str | None) -> str | None:
    """None이면 None 반환, 아니면 암호화."""
    if value is None:
        return None
    return encrypt_value(value)


def decrypt_optional(encrypted_value: str | None) -> str | None:
    """None이면 None 반환, 아니면 복호화."""
    if encrypted_value is None:
        return None
    return decrypt_value(encrypted_value)


def encrypt_decimal_optional(value: Decimal | None) -> str | None:
    """None이면 None 반환, 아니면 Decimal 암호화."""
    if value is None:
        return None
    return encrypt_decimal(value)


def decrypt_decimal_optional(encrypted_value: str | None) -> Decimal | None:
    """None이면 None 반환, 아니면 복호화 후 Decimal 변환."""
    if encrypted_value is None:
        return None
    return decrypt_decimal(encrypted_value)


def generate_encryption_key() -> str:
    """새 Fernet 호환 암호화 키 생성 (설정 시 1회 사용)."""
    return Fernet.generate_key().decode()
