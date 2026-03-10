"""crypto_service 단위 테스트"""

from decimal import Decimal

import pytest

from app.services.crypto_service import (
    decrypt_decimal,
    decrypt_decimal_optional,
    decrypt_optional,
    decrypt_value,
    encrypt_decimal,
    encrypt_decimal_optional,
    encrypt_optional,
    encrypt_value,
    generate_encryption_key,
)


class TestEncryptDecryptValue:
    def test_roundtrip(self):
        original = "hello-world-테스트"
        encrypted = encrypt_value(original)
        assert encrypted != original
        assert decrypt_value(encrypted) == original

    def test_different_ciphertext_each_time(self):
        """Fernet은 매번 다른 암호문을 생성해야 한다 (IV/nonce)."""
        original = "same-plaintext"
        enc1 = encrypt_value(original)
        enc2 = encrypt_value(original)
        assert enc1 != enc2
        assert decrypt_value(enc1) == original
        assert decrypt_value(enc2) == original

    def test_empty_string(self):
        encrypted = encrypt_value("")
        assert decrypt_value(encrypted) == ""


class TestEncryptDecryptDecimal:
    def test_roundtrip(self):
        amount = Decimal("15000000.50")
        encrypted = encrypt_decimal(amount)
        assert decrypt_decimal(encrypted) == amount

    def test_negative(self):
        amount = Decimal("-500000.25")
        assert decrypt_decimal(encrypt_decimal(amount)) == amount

    def test_zero(self):
        amount = Decimal("0")
        assert decrypt_decimal(encrypt_decimal(amount)) == amount

    def test_large_number(self):
        amount = Decimal("99999999999999.9999")
        assert decrypt_decimal(encrypt_decimal(amount)) == amount


class TestOptionalEncryption:
    def test_none_string(self):
        assert encrypt_optional(None) is None
        assert decrypt_optional(None) is None

    def test_value_string(self):
        original = "totp-secret"
        encrypted = encrypt_optional(original)
        assert encrypted is not None
        assert decrypt_optional(encrypted) == original

    def test_none_decimal(self):
        assert encrypt_decimal_optional(None) is None
        assert decrypt_decimal_optional(None) is None

    def test_value_decimal(self):
        amount = Decimal("100000")
        encrypted = encrypt_decimal_optional(amount)
        assert encrypted is not None
        assert decrypt_decimal_optional(encrypted) == amount


class TestGenerateKey:
    def test_generates_valid_key(self):
        key = generate_encryption_key()
        assert isinstance(key, str)
        assert len(key) > 0
