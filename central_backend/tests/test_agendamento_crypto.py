"""Testes unitários do módulo de criptografia."""
import pytest
from backend.agendamento.crypto import encrypt_key, decrypt_key, mask_key


class TestCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        original = "AIzaSyBtest1234567890"
        cifrado = encrypt_key(original)
        assert cifrado != original
        assert decrypt_key(cifrado) == original

    def test_encrypt_gera_valores_diferentes(self):
        """Fernet gera IVs diferentes a cada chamada."""
        plain = "minha-chave-secreta"
        c1 = encrypt_key(plain)
        c2 = encrypt_key(plain)
        assert c1 != c2
        assert decrypt_key(c1) == plain
        assert decrypt_key(c2) == plain

    def test_encrypt_string_vazia(self):
        assert encrypt_key("") == ""
        assert decrypt_key("") == ""

    def test_encrypt_none(self):
        assert encrypt_key(None) is None
        assert decrypt_key(None) is None

    def test_mask_key_formato(self):
        cifrado = encrypt_key("AIzaSyB1234567890ABCDEF")
        masked = mask_key(cifrado)
        assert "***" in masked
        assert masked.startswith("AIza")
        assert masked.endswith("CDEF")

    def test_mask_key_curta(self):
        cifrado = encrypt_key("abc")
        masked = mask_key(cifrado)
        assert masked == "***"

    def test_mask_key_vazia(self):
        assert mask_key("") == ""
        assert mask_key(None) == ""

    def test_mask_key_invalida(self):
        assert mask_key("lixo-nao-fernet") == "***"
