"""Tests for mcp_odbc.vault — uses mock to avoid a real win32crypt dependency."""

from __future__ import annotations

import base64
import sys
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Fixtures: inject a fake win32crypt module before importing vault so that the
# tests run on any platform (including Linux CI).
# ---------------------------------------------------------------------------

_FAKE_ENCRYPTED_PREFIX = b"FAKE_DPAPI:"


def _fake_CryptProtectData(data: bytes, desc, entropy, reserved, prompt, flags) -> bytes:
    return _FAKE_ENCRYPTED_PREFIX + data


def _fake_CryptUnprotectData(data: bytes, entropy, reserved, prompt, flags):
    if not data.startswith(_FAKE_ENCRYPTED_PREFIX):
        raise OSError("Fake DPAPI: invalid ciphertext")
    plaintext = data[len(_FAKE_ENCRYPTED_PREFIX):]
    return ("mcp-odbc credential", plaintext)


@pytest.fixture(autouse=True)
def patch_win32crypt(monkeypatch):
    """Inject a fake win32crypt and force sys.platform = 'win32'."""
    fake_module = mock.MagicMock()
    fake_module.CryptProtectData.side_effect = _fake_CryptProtectData
    fake_module.CryptUnprotectData.side_effect = _fake_CryptUnprotectData

    monkeypatch.setitem(sys.modules, "win32crypt", fake_module)

    import mcp_odbc.vault as vault_mod
    monkeypatch.setattr(vault_mod, "_is_windows", lambda: True)

    # Re-import to pick up patched _is_windows
    yield vault_mod


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEncryptPassword:
    def test_returns_dpapi_prefix(self, patch_win32crypt):
        vault = patch_win32crypt
        token = vault.encrypt_password("secret")
        assert token.startswith("dpapi:")

    def test_base64_payload_is_valid(self, patch_win32crypt):
        vault = patch_win32crypt
        token = vault.encrypt_password("secret")
        b64 = token[len("dpapi:"):]
        # Should not raise
        decoded = base64.b64decode(b64)
        assert isinstance(decoded, bytes)

    def test_empty_password(self, patch_win32crypt):
        vault = patch_win32crypt
        token = vault.encrypt_password("")
        assert token.startswith("dpapi:")

    def test_non_windows_raises(self, patch_win32crypt, monkeypatch):
        vault = patch_win32crypt
        monkeypatch.setattr(vault, "_is_windows", lambda: False)
        with pytest.raises(RuntimeError, match="Windows"):
            vault.encrypt_password("secret")


class TestDecryptPassword:
    def test_round_trip(self, patch_win32crypt):
        vault = patch_win32crypt
        original = "my$uper$ecret"
        token = vault.encrypt_password(original)
        assert vault.decrypt_password(token) == original

    def test_plain_text_passthrough(self, patch_win32crypt):
        vault = patch_win32crypt
        assert vault.decrypt_password("plainpassword") == "plainpassword"

    def test_empty_plain_text(self, patch_win32crypt):
        vault = patch_win32crypt
        assert vault.decrypt_password("") == ""

    def test_malformed_base64_raises(self, patch_win32crypt):
        vault = patch_win32crypt
        with pytest.raises(ValueError, match="base64"):
            vault.decrypt_password("dpapi:!!!not-valid-base64!!!")

    def test_non_windows_dpapi_token_raises(self, patch_win32crypt, monkeypatch):
        vault = patch_win32crypt
        monkeypatch.setattr(vault, "_is_windows", lambda: False)
        token = "dpapi:" + base64.b64encode(b"anything").decode()
        with pytest.raises(RuntimeError, match="Windows"):
            vault.decrypt_password(token)

    def test_wrong_ciphertext_raises(self, patch_win32crypt):
        vault = patch_win32crypt
        # Valid base64 but not produced by our fake encrypt → CryptUnprotectData fails
        bad_token = "dpapi:" + base64.b64encode(b"GARBAGE").decode()
        with pytest.raises(ValueError, match="DPAPI decryption failed"):
            vault.decrypt_password(bad_token)


class TestDecryptConnectionString:
    def test_no_dpapi_token_unchanged(self, patch_win32crypt):
        vault = patch_win32crypt
        cs = "DRIVER={Sybase};SERVER=prod;UID=sa;PWD=plain"
        assert vault.decrypt_connection_string(cs) == cs

    def test_single_dpapi_token_decrypted(self, patch_win32crypt):
        vault = patch_win32crypt
        pwd = "s3cr3t"
        token = vault.encrypt_password(pwd)
        cs = f"DRIVER={{Sybase}};SERVER=prod;UID=sa;PWD={token}"
        decrypted = vault.decrypt_connection_string(cs)
        assert "PWD=s3cr3t" in decrypted
        assert "dpapi:" not in decrypted

    def test_multiple_dpapi_tokens(self, patch_win32crypt):
        vault = patch_win32crypt
        uid_enc = vault.encrypt_password("admin")
        pwd_enc = vault.encrypt_password("pass123")
        cs = f"SERVER=db;UID={uid_enc};PWD={pwd_enc}"
        result = vault.decrypt_connection_string(cs)
        assert "UID=admin" in result
        assert "PWD=pass123" in result

    def test_mixed_plain_and_encrypted(self, patch_win32crypt):
        vault = patch_win32crypt
        pwd_enc = vault.encrypt_password("mypass")
        cs = f"SERVER=db;UID=plainuser;PWD={pwd_enc}"
        result = vault.decrypt_connection_string(cs)
        assert "UID=plainuser" in result
        assert "PWD=mypass" in result

    def test_empty_connection_string(self, patch_win32crypt):
        vault = patch_win32crypt
        assert vault.decrypt_connection_string("") == ""

    def test_fast_path_no_prefix(self, patch_win32crypt, monkeypatch):
        """Ensure no decryption calls are made when no dpapi: prefix is present."""
        vault = patch_win32crypt
        fake_w32 = sys.modules["win32crypt"]
        vault.decrypt_connection_string("SERVER=x;UID=y;PWD=z")
        fake_w32.CryptUnprotectData.assert_not_called()
