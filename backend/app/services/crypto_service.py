"""AES-256-GCM 암복호화 서비스

금액, TOTP 시크릿 등 민감 데이터를 DB에 저장할 때 사용.
ENCRYPTION_KEY 환경변수에서 키를 읽어온다 (URL-safe base64, 32바이트 이상).

AES-256-GCM 특성:
- 32바이트(256-bit) 키 사용
- 12바이트 nonce (암호화마다 랜덤 생성)
- 16바이트 인증 태그 내장 (무결성 검증)

저장 형식: base64url(nonce[12] + ciphertext + auth_tag[16])
"""

import base64
import secrets
from decimal import Decimal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_NONCE_SIZE = 12  # AES-GCM 표준 nonce 크기


def _get_key() -> bytes:
    """환경변수에서 AES-256 키(32바이트)를 추출.

    키가 정확히 32바이트가 아니면 즉시 실패 (묵시적 잘라내기 금지).
    generate_encryption_key()로 생성한 키는 항상 정확히 32바이트.
    """
    padding = "=" * (-len(settings.encryption_key) % 4)
    raw = base64.urlsafe_b64decode(settings.encryption_key + padding)
    if len(raw) != 32:
        raise ValueError(
            f"ENCRYPTION_KEY는 정확히 32바이트여야 합니다. 현재: {len(raw)}바이트. "
            "generate_encryption_key()로 새 키를 생성하세요."
        )
    return raw


def encrypt_value(value: str) -> str:
    """문자열을 AES-256-GCM으로 암호화 → URL-safe base64 반환."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(_NONCE_SIZE)
    ciphertext = aesgcm.encrypt(nonce, value.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_value(encrypted_value: str) -> str:
    """AES-256-GCM 암호문 복호화."""
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.urlsafe_b64decode(encrypted_value + "==")
    nonce, ciphertext = raw[:_NONCE_SIZE], raw[_NONCE_SIZE:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()


def encrypt_decimal(value: Decimal) -> str:
    """Decimal 값을 문자열로 변환 후 AES-256-GCM 암호화."""
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
    """AES-256용 새 암호화 키 생성 (32바이트, URL-safe base64 인코딩)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
