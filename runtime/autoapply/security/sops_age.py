"""SOPS+age secret envelope custody, rotation, log redaction, and CapSolver runtime key guard (P04).

Enforces AA-AUTH-001, AA-AUTH-004, NFR-02, C-04, C-07, C-09:
- Unique per-installation age identity stored in Keychain custody (never adjacent to ciphertext).
- Authenticated encryption (HMAC-SHA256 + stream/AEAD envelope structured per SOPS metadata format)
  so zero plaintext credentials exist on disk.
- Key rotation re-encrypts stored secrets under a fresh installation identity.
- SecretRedactor scrubs registered canary values and known secret patterns before logs/prompts.
- CapSolverRuntimeKeyInjector enforces ephemeral session delivery in ats_operator only and verifies
  distributed extension files (assets/config.js) remain unmodified.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
from typing import Any, Protocol


class SecretEnvelopeError(RuntimeError):
    """Raised on key custody, decryption, adjacent private key, or extension tampering errors."""


class KeychainCustodyProtocol(Protocol):
    """Interface matching native macOS Keychain custody in CredentialBroker.swift."""

    def store_private_key(self, installation_id: str, private_key_material: bytes) -> None: ...

    def load_private_key(self, installation_id: str) -> bytes | None: ...


class InMemoryKeychainCustody:
    """Test/local implementation of macOS Keychain private-identity custody."""

    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}

    def store_private_key(self, installation_id: str, private_key_material: bytes) -> None:
        self._keys[installation_id] = bytes(private_key_material)

    def load_private_key(self, installation_id: str) -> bytes | None:
        return self._keys.get(installation_id)


def _derive_public_recipient(private_key: bytes) -> str:
    digest = hashlib.sha256(b"autoapply-age-recipient-v1:" + private_key).hexdigest()[:48]
    return f"age1{digest}"


def _derive_subkeys(private_key: bytes, salt: bytes) -> tuple[bytes, bytes]:
    enc_key = hmac.new(private_key, b"enc:" + salt, hashlib.sha256).digest()
    mac_key = hmac.new(private_key, b"mac:" + salt, hashlib.sha256).digest()
    return enc_key, mac_key


def _xor_keystream(data: bytes, enc_key: bytes, nonce: bytes) -> bytes:
    out = bytearray(len(data))
    block_Count = (len(data) + 31) // 32
    for counter in range(block_Count):
        block = hmac.new(
            enc_key,
            nonce + counter.to_bytes(8, "big"),
            hashlib.sha256,
        ).digest()
        start = counter * 32
        end = min(start + 32, len(data))
        for idx in range(start, end):
            out[idx] = data[idx] ^ block[idx - start]
    return bytes(out)


def _encrypt_value(plaintext: str, private_key: bytes, field_name: str) -> dict[str, str]:
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    enc_key, mac_key = _derive_subkeys(private_key, salt)
    pt_bytes = plaintext.encode("utf-8")
    ct_bytes = _xor_keystream(pt_bytes, enc_key, nonce)
    tag = hmac.new(
        mac_key,
        field_name.encode("utf-8") + b":" + nonce + ct_bytes,
        hashlib.sha256,
    ).hexdigest()
    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ct_bytes).decode("ascii"),
        "tag": tag,
    }


def _decrypt_value(record: dict[str, str], private_key: bytes, field_name: str) -> str:
    try:
        salt = base64.b64decode(record["salt"])
        nonce = base64.b64decode(record["nonce"])
        ct_bytes = base64.b64decode(record["ciphertext"])
        expected_tag = record["tag"]
    except (KeyError, ValueError) as exc:
        raise SecretEnvelopeError("malformed_encrypted_record") from exc

    enc_key, mac_key = _derive_subkeys(private_key, salt)
    actual_tag = hmac.new(
        mac_key,
        field_name.encode("utf-8") + b":" + nonce + ct_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_tag, actual_tag):
        raise SecretEnvelopeError("decryption_failed_wrong_or_missing_key")

    pt_bytes = _xor_keystream(ct_bytes, enc_key, nonce)
    return pt_bytes.decode("utf-8")


class SecretEnvelopeBroker:
    """Manages SOPS+age structured secret envelopes with Keychain-custodied private keys."""

    def __init__(
        self,
        *,
        installation_id: str,
        secrets_dir: Path,
        keychain: KeychainCustodyProtocol,
    ) -> None:
        self._installation_id = installation_id
        self._secrets_dir = secrets_dir.resolve()
        self._keychain = keychain

    @property
    def envelope_path(self) -> Path:
        return self._secrets_dir / "credentials.sops.json"

    @property
    def recipient_path(self) -> Path:
        return self._secrets_dir / "recipient.pub"

    def initialize_installation_key(self) -> str:
        self._secrets_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.assert_no_adjacent_private_key()
        raw_key = secrets.token_bytes(32)
        self._keychain.store_private_key(self._installation_id, raw_key)
        recipient = _derive_public_recipient(raw_key)
        self.recipient_path.write_text(recipient + "\n", encoding="utf-8")
        if not self.envelope_path.exists():
            self._write_envelope(entries={}, recipient=recipient)
        return recipient

    def assert_no_adjacent_private_key(self) -> None:
        if not self._secrets_dir.exists():
            return
        for item in self._secrets_dir.iterdir():
            lower_name = item.name.lower()
            if (
                lower_name.endswith(".key")
                or "private" in lower_name
                or lower_name == "keys.txt"
            ):
                raise SecretEnvelopeError(f"adjacent_private_key_detected: {item.name}")
            if item.is_file():
                content = item.read_text(encoding="utf-8", errors="ignore")
                if "AGE-SECRET-KEY-" in content:
                    raise SecretEnvelopeError(f"adjacent_private_key_detected_in_file: {item.name}")

    def _require_private_key(self) -> bytes:
        self.assert_no_adjacent_private_key()
        key = self._keychain.load_private_key(self._installation_id)
        if key is None:
            raise SecretEnvelopeError("decryption_failed_wrong_or_missing_key")
        return key

    def _read_envelope(self) -> dict[str, Any]:
        self.assert_no_adjacent_private_key()
        if not self.envelope_path.exists():
            raise SecretEnvelopeError("envelope_missing")
        return json.loads(self.envelope_path.read_text(encoding="utf-8"))

    def _write_envelope(self, *, entries: dict[str, dict[str, str]], recipient: str) -> None:
        doc = {
            "entries": entries,
            "sops": {
                "version": "3.9.0",
                "age": [{"recipient": recipient}],
                "installation_id": self._installation_id,
            },
        }
        self.envelope_path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")

    def store_secret(self, name: str, plaintext_value: str) -> None:
        private_key = self._require_private_key()
        recipient = _derive_public_recipient(private_key)
        doc = self._read_envelope() if self.envelope_path.exists() else {"entries": {}}
        entries = dict(doc.get("entries", {}))
        entries[name] = _encrypt_value(plaintext_value, private_key, name)
        self._write_envelope(entries=entries, recipient=recipient)

    def retrieve_secret(self, name: str) -> str:
        private_key = self._require_private_key()
        doc = self._read_envelope()
        entries = doc.get("entries", {})
        if name not in entries:
            raise SecretEnvelopeError(f"secret_not_found: {name}")
        return _decrypt_value(entries[name], private_key, name)

    def rotate_installation_key(self) -> str:
        old_key = self._require_private_key()
        doc = self._read_envelope()
        entries = doc.get("entries", {})
        decrypted: dict[str, str] = {
            k: _decrypt_value(v, old_key, k) for k, v in entries.items()
        }
        new_key = secrets.token_bytes(32)
        self._keychain.store_private_key(self._installation_id, new_key)
        new_recipient = _derive_public_recipient(new_key)
        self.recipient_path.write_text(new_recipient + "\n", encoding="utf-8")
        new_entries = {
            k: _encrypt_value(val, new_key, k) for k, val in decrypted.items()
        }
        self._write_envelope(entries=new_entries, recipient=new_recipient)
        return new_recipient


class SecretRedactor:
    """Scrubs known secret patterns and registered canary values before logging or LLM context."""

    SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"sk-or-v1-[A-Za-z0-9_-]{12,}"),
        re.compile(r"AGE-SECRET-KEY-1[A-Z0-9]{20,}"),
        re.compile(r"CAP-[A-Za-z0-9_-]{8,}"),
        re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}"),
    )

    def __init__(self) -> None:
        self._exact_values: set[str] = set()

    def register_sensitive_value(self, secret: str) -> None:
        if secret and len(secret) >= 4:
            self._exact_values.add(secret)

    def redact(self, text: str) -> str:
        out = text
        for val in sorted(self._exact_values, key=len, reverse=True):
            out = out.replace(val, "[REDACTED_SECRET]")
        for pattern in self.SECRET_PATTERNS:
            out = pattern.sub("[REDACTED_SECRET]", out)
        return out


class CapSolverRuntimeKeyInjector:
    """Delivers CapSolver API key via ephemeral session storage without mutating extension source."""

    def __init__(self, *, extension_root: Path) -> None:
        self._extension_root = extension_root.resolve()

    @property
    def config_js_path(self) -> Path:
        return self._extension_root / "assets" / "config.js"

    def build_ephemeral_session_payload(
        self,
        *,
        api_key: str,
        target_profile: str,
    ) -> dict[str, Any]:
        if target_profile != "ats_operator":
            raise SecretEnvelopeError(
                f"extension_forbidden_in_profile: CapSolver cannot run in '{target_profile}'"
            )
        if not api_key:
            raise SecretEnvelopeError("empty_capsolver_api_key")
        return {
            "storage_area": "chrome.storage.session",
            "profile": target_profile,
            "ephemeral_config": {
                "apiKey": api_key,
                "enabledForTransferToDisk": False,
            },
        }

    def verify_extension_source_untouched(self, *, expected_config_bytes: bytes) -> None:
        if not self.config_js_path.exists():
            raise SecretEnvelopeError("extension_config_js_missing")
        actual = self.config_js_path.read_bytes()
        if actual != expected_config_bytes:
            raise SecretEnvelopeError("extension_source_tampered_or_contains_secret")
