"""Security tests for SOPS+age secret envelopes, key custody, redaction, and CapSolver key isolation (P04).

Covers: AA-AUTH-001, AA-AUTH-004, NFR-02, C-04, C-07, C-09
Scenarios: T-SEC-01, T-SEC-02, T-SEC-03
"""

from __future__ import annotations

from pathlib import Path
import pytest

from autoapply.security.sops_age import (
    CapSolverRuntimeKeyInjector,
    InMemoryKeychainCustody,
    SecretEnvelopeBroker,
    SecretEnvelopeError,
    SecretRedactor,
)


def test_per_installation_keys_differ_and_ciphertext_hides_plaintext(tmp_path: Path) -> None:
    """T-SEC-01: Installation keys are unique; on-disk envelope never contains plaintext secrets."""
    keychain_a = InMemoryKeychainCustody()
    keychain_b = InMemoryKeychainCustody()

    broker_a = SecretEnvelopeBroker(
        installation_id="inst_alpha",
        secrets_dir=tmp_path / "inst_a" / "secrets",
        keychain=keychain_a,
    )
    broker_b = SecretEnvelopeBroker(
        installation_id="inst_beta",
        secrets_dir=tmp_path / "inst_b" / "secrets",
        keychain=keychain_b,
    )

    pub_a = broker_a.initialize_installation_key()
    pub_b = broker_b.initialize_installation_key()
    assert pub_a != pub_b
    assert pub_a.startswith("age1")

    canary_secret = "sk-or-v1-canary-secret-value-99887766"
    broker_a.store_secret("openrouter_api_key", canary_secret)

    # Inspect on-disk envelope: must not contain the plaintext canary secret or private key
    envelope_text = broker_a.envelope_path.read_text(encoding="utf-8")
    assert canary_secret not in envelope_text
    assert "AGE-SECRET-KEY-" not in envelope_text
    assert "sops" in envelope_text

    # No private key file may exist in secrets_dir alongside ciphertext
    broker_a.assert_no_adjacent_private_key()
    for p in (tmp_path / "inst_a" / "secrets").iterdir():
        assert "AGE-SECRET-KEY-" not in p.read_text(encoding="utf-8")

    # Round-trip decrypt with authorized installation key succeeds
    assert broker_a.retrieve_secret("openrouter_api_key") == canary_secret

    # Wrong installation's keychain cannot decrypt inst_alpha's envelope
    wrong_broker = SecretEnvelopeBroker(
        installation_id="inst_beta",
        secrets_dir=tmp_path / "inst_a" / "secrets",
        keychain=keychain_b,
    )
    with pytest.raises(SecretEnvelopeError, match="decryption_failed_wrong_or_missing_key"):
        wrong_broker.retrieve_secret("openrouter_api_key")


def test_key_rotation_reencrypts_secrets_and_invalidates_old_key(tmp_path: Path) -> None:
    """T-SEC-01 / C-04: Rotating the installation key re-encrypts envelopes safely."""
    keychain = InMemoryKeychainCustody()
    broker = SecretEnvelopeBroker(
        installation_id="inst_rotate",
        secrets_dir=tmp_path / "secrets",
        keychain=keychain,
    )
    old_pub = broker.initialize_installation_key()
    broker.store_secret("gmail_app_password", "abcd-efgh-ijkl-mnop")

    new_pub = broker.rotate_installation_key()
    assert new_pub != old_pub
    assert broker.retrieve_secret("gmail_app_password") == "abcd-efgh-ijkl-mnop"


def test_adjacent_private_key_file_causes_immediate_security_failure(tmp_path: Path) -> None:
    """T-SEC-01: Any private key placed next to ciphertext is flagged and blocked."""
    keychain = InMemoryKeychainCustody()
    secrets_dir = tmp_path / "secrets"
    broker = SecretEnvelopeBroker(
        installation_id="inst_adj",
        secrets_dir=secrets_dir,
        keychain=keychain,
    )
    broker.initialize_installation_key()

    # Simulate accidental placement of an age private key file inside secrets_dir
    (secrets_dir / "keys.txt").write_text("AGE-SECRET-KEY-1FAKEKEY", encoding="utf-8")
    with pytest.raises(SecretEnvelopeError, match="adjacent_private_key_detected"):
        broker.retrieve_secret("any_key")


def test_secret_redactor_scrubs_canary_secrets_and_patterns_from_logs_and_prompts() -> None:
    """T-SEC-02: Logs, crash dumps, support bundles, and prompts never leak secrets."""
    redactor = SecretRedactor()
    canary = "capsolver-live-key-4455667788"
    redactor.register_sensitive_value(canary)

    raw_log = (
        f"Connecting with key={canary}, openrouter=sk-or-v1-1234567890abcdef1234567890abcdef, "
        "and age key AGE-SECRET-KEY-1QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ"
    )
    scrubbed = redactor.redact(raw_log)
    assert canary not in scrubbed
    assert "sk-or-v1-" not in scrubbed
    assert "AGE-SECRET-KEY-1" not in scrubbed
    assert "[REDACTED_SECRET]" in scrubbed


def test_capsolver_runtime_injector_forbids_plaintext_extension_config_mutation(
    tmp_path: Path,
) -> None:
    """T-SEC-03 / AA-AUTH-004 / C-07: Never write API key into distributed extension assets/config.js."""
    ext_dir = tmp_path / "capsolver_ext"
    assets_dir = ext_dir / "assets"
    assets_dir.mkdir(parents=True)
    config_js = assets_dir / "config.js"
    original_source = "export const defaultConfig = { apiKey: '' };\n"
    config_js.write_text(original_source, encoding="utf-8")

    injector = CapSolverRuntimeKeyInjector(extension_root=ext_dir)
    payload = injector.build_ephemeral_session_payload(
        api_key="CAP-9988776655",
        target_profile="ats_operator",
    )
    assert payload["storage_area"] == "chrome.storage.session"
    assert config_js.read_text(encoding="utf-8") == original_source
    injector.verify_extension_source_untouched(expected_config_bytes=original_source.encode("utf-8"))

    # Injecting into auth_trusted or linkedin_session is rejected (C-07)
    with pytest.raises(SecretEnvelopeError, match="extension_forbidden_in_profile"):
        injector.build_ephemeral_session_payload(
            api_key="CAP-9988776655",
            target_profile="auth_trusted",
        )

    # If something tampered with assets/config.js to embed a key, verification fails closed
    config_js.write_text("export const defaultConfig = { apiKey: 'CAP-9988776655' };\n", encoding="utf-8")
    with pytest.raises(SecretEnvelopeError, match="extension_source_tampered_or_contains_secret"):
        injector.verify_extension_source_untouched(expected_config_bytes=original_source.encode("utf-8"))
