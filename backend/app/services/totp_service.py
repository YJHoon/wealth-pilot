"""TOTP 2FA 서비스 — QR 코드 생성, OTP 검증"""

import base64
import io

import pyotp
import qrcode

from app.services.crypto_service import decrypt_value, encrypt_value


def generate_totp_secret() -> str:
    """새 TOTP 시크릿 생성 (평문)"""
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> str:
    """TOTP 시크릿을 AES-256으로 암호화하여 DB 저장용 반환"""
    return encrypt_value(secret)


def decrypt_totp_secret(encrypted_secret: str) -> str:
    """DB에서 읽은 암호화된 TOTP 시크릿 복호화"""
    return decrypt_value(encrypted_secret)


def generate_qr_code(secret: str, email: str) -> tuple[str, str]:
    """QR 코드 이미지(Base64)와 otpauth URI 반환

    Returns:
        (qr_code_base64, otpauth_uri)
    """
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=email, issuer_name="WealthPilot")

    # QR 코드 이미지 생성
    img = qrcode.make(uri, box_size=6, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    qr_base64 = base64.b64encode(buffer.read()).decode()

    return qr_base64, uri


def verify_totp_code(secret: str, code: str) -> bool:
    """OTP 코드 검증 (전후 30초 허용)"""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
