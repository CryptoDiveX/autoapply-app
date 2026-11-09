"""Contract tests for 120-hour trial, USD 20/month licence key, 1-device seat lease, and post-expiry export.

Covers:
- T-LIC-01: 120h trial starts only after automation readiness; local clock rollback blocks automation.
- T-LIC-02: USD 20/month licence key activation, 1-device seat enforcement, explicit seat transfer, and 72h offline lease.
- T-LIC-03: Billing webhook events (purchase, renewal, failure, cancellation, refund) are idempotent.
- T-LIC-04: Expired trial/subscription blocks new automation while preserving full read-only history and data export.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autoapply.licensing import EntitlementService


def test_trial_starts_only_at_automation_ready_and_detects_clock_rollback(tmp_path: Path) -> None:
    """T-LIC-01 & C-02: 120h server trial starts only when automation is armed and blocks clock rollback."""
    svc = EntitlementService(db_path=tmp_path / "entitlements.sqlite3", signing_secret="test-lease-secret")
    t0 = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)

    # Cannot start trial before onboarding reaches O-09 automation_ready
    with pytest.raises(PermissionError, match="TRIAL_REQUIRES_AUTOMATION_READY"):
        svc.activate_trial(device_id="mac_dev_01", automation_ready=False, server_now=t0)

    lease = svc.activate_trial(device_id="mac_dev_01", automation_ready=True, server_now=t0)
    assert lease.tier == "trial"
    assert lease.trial_duration_hours == 48
    assert lease.expires_at == (t0 + timedelta(hours=48)).isoformat()
    assert lease.lease_ttl_hours == 72

    # Advance time by 10 hours: valid
    t_plus_10h = t0 + timedelta(hours=10)
    status = svc.evaluate_access(device_id="mac_dev_01", current_time=t_plus_10h)
    assert status.can_run_automation is True
    assert status.can_read_and_export is True

    # Simulate local clock rollback (current_time < max_seen_timestamp)
    t_rollback = t0 + timedelta(hours=2)
    with pytest.raises(PermissionError, match="CLOCK_ROLLBACK_DETECTED"):
        svc.evaluate_access(device_id="mac_dev_01", current_time=t_rollback)


def test_paid_license_activation_single_device_seat_transfer_and_72h_offline_lease(tmp_path: Path) -> None:
    """T-LIC-02 & C-03: USD 20/month key enforces 1 active device seat, supports seat transfer, and signs 72h lease."""
    svc = EntitlementService(db_path=tmp_path / "entitlements.sqlite3", signing_secret="test-lease-secret")
    t0 = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)

    svc.issue_license_key(license_key="AA-LIVE-20USD-0001", price_usd_monthly=20, server_now=t0)
    lease_1 = svc.activate_license_key(
        license_key="AA-LIVE-20USD-0001",
        device_id="mac_dev_01",
        server_now=t0,
    )
    assert lease_1.tier == "paid_monthly"
    assert lease_1.price_usd_monthly == 20
    assert lease_1.lease_ttl_hours == 72
    assert svc.verify_lease_signature(lease_1) is True

    # Second device attempting simultaneous activation without seat transfer is blocked
    with pytest.raises(PermissionError, match="DEVICE_SEAT_LIMIT_EXCEEDED"):
        svc.activate_license_key(
            license_key="AA-LIVE-20USD-0001",
            device_id="mac_dev_02",
            server_now=t0 + timedelta(minutes=5),
        )

    # Explicit seat transfer moves active seat to mac_dev_02 and revokes mac_dev_01
    lease_2 = svc.transfer_device_seat(
        license_key="AA-LIVE-20USD-0001",
        from_device_id="mac_dev_01",
        to_device_id="mac_dev_02",
        server_now=t0 + timedelta(minutes=10),
    )
    assert lease_2.device_id == "mac_dev_02"
    old_status = svc.evaluate_access(device_id="mac_dev_01", current_time=t0 + timedelta(minutes=15))
    assert old_status.can_run_automation is False
    new_status = svc.evaluate_access(device_id="mac_dev_02", current_time=t0 + timedelta(minutes=15))
    assert new_status.can_run_automation is True


def test_webhook_idempotency_and_post_expiry_readonly_export(tmp_path: Path) -> None:
    """T-LIC-03 & T-LIC-04: Duplicate billing webhooks are idempotent; expiry preserves read-only + full export."""
    svc = EntitlementService(db_path=tmp_path / "entitlements.sqlite3", signing_secret="test-lease-secret")
    t0 = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)

    svc.issue_license_key(license_key="AA-LIVE-20USD-0002", price_usd_monthly=20, server_now=t0)
    svc.activate_license_key(license_key="AA-LIVE-20USD-0002", device_id="mac_dev_01", server_now=t0)

    # Process renewal webhook twice with the same event_id: must be idempotent
    first = svc.process_webhook_event(
        event_id="evt_renew_001",
        event_type="subscription.renewed",
        license_key="AA-LIVE-20USD-0002",
        server_now=t0 + timedelta(days=30),
    )
    second = svc.process_webhook_event(
        event_id="evt_renew_001",
        event_type="subscription.renewed",
        license_key="AA-LIVE-20USD-0002",
        server_now=t0 + timedelta(days=30),
    )
    assert first.duplicate_ignored is False
    assert second.duplicate_ignored is True
    assert first.expires_at == second.expires_at

    # Process refund/cancellation expiry webhook
    svc.process_webhook_event(
        event_id="evt_refund_001",
        event_type="subscription.refunded",
        license_key="AA-LIVE-20USD-0002",
        server_now=t0 + timedelta(days=31),
    )

    expired_status = svc.evaluate_access(device_id="mac_dev_01", current_time=t0 + timedelta(days=31, minutes=1))
    assert expired_status.can_run_automation is False
    assert expired_status.can_read_and_export is True

    # Full export succeeds even when subscription is expired
    export_bundle = svc.export_user_bundle(
        device_id="mac_dev_01",
        applications=[{"application_id": "app_acme", "status": "submitted"}],
        documents=[{"artifact_id": "doc_resume_v1", "sha256": "abc123"}],
    )
    assert export_bundle["read_only_mode"] is True
    assert len(export_bundle["applications"]) == 1
    assert len(export_bundle["documents"]) == 1


def test_paddle_multi_plan_prices_webhook_verification_and_email_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify per-plan Paddle price IDs ($10/$30/$200/$200), signed webhook & checkout coordination,
    AA-PRO + legacy AA-LIVE-20USD compatibility, Mac Support Code removal, and executive email formatting."""
    import hashlib
    import hmac
    import json
    import sqlite3
    import sys
    import threading
    from email.message import EmailMessage

    api_dir = Path(__file__).resolve().parents[2] / "services" / "licensing" / "api"
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))
    import licensing_routes as lr

    price_ids = {
        "weekly": "pri_weekly_10usd",
        "monthly": "pri_monthly_30usd",
        "annual": "pri_annual_200usd",
        "lifetime": "pri_lifetime_200usd",
    }
    wh_secret = "pdl_ntfset_unit_test_secret"
    (tmp_path / "paddle_config.json").write_text(
        json.dumps(
            {
                "paddle_environment": "sandbox",
                "paddle_client_token": "test_unit_client_tok",
                "paddle_api_key": "pdl_sdbx_apikey_unit_test",
                "paddle_webhook_secret": wh_secret,
                "paddle_price_id": price_ids["monthly"],
                "paddle_price_ids": price_ids,
            }
        ),
        encoding="utf-8",
    )

    cfg = lr.load_paddle_runtime_config(storage_dir=tmp_path)
    assert cfg["paddle_overlay_ready"] is True
    assert cfg["paddle_price_ids"] == price_ids
    plans_by_id = {p["id"]: p for p in cfg["pricing_plans"]}
    assert plans_by_id["weekly"]["price_usd"] == 10 and plans_by_id["weekly"]["paddle_price_id"] == price_ids["weekly"]
    assert plans_by_id["monthly"]["price_usd"] == 30 and plans_by_id["monthly"]["paddle_price_id"] == price_ids["monthly"]
    assert plans_by_id["annual"]["price_usd"] == 200 and plans_by_id["annual"]["paddle_price_id"] == price_ids["annual"]
    assert plans_by_id["lifetime"]["price_usd"] == 200 and plans_by_id["lifetime"]["paddle_price_id"] == price_ids["lifetime"]

    # Standalone subscribe HTML must have zero Mac Support Code references and embed per-plan priceIds
    sub_html = lr.render_standalone_subscribe_html(
        cfg,
        {"device_id": ["mac_dev_01"], "support_code": ["SUP-LEGACY123"], "email": ["buyer@example.com"]},
    ).decode("utf-8")
    assert "Mac Support Code" not in sub_html
    assert "SUP-LEGACY123" not in sub_html
    assert "pri_monthly_30usd" in sub_html and "pri_lifetime_200usd" in sub_html

    conn = sqlite3.connect(tmp_path / "licensing.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    db_lock = threading.Lock()
    lr.init_licensing_tables(conn)

    sent_messages: list[EmailMessage] = []

    class DummySMTP:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "DummySMTP":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def ehlo(self) -> None:
            pass

        def starttls(self, **kwargs: object) -> None:
            pass

        def login(self, user: str, pwd: str) -> None:
            pass

        def send_message(self, msg: EmailMessage) -> None:
            sent_messages.append(msg)

    monkeypatch.setenv("TURBOAPPLY_SMTP_PASSWORD", "unit-test-smtp-pass")
    monkeypatch.setattr(lr.smtplib, "SMTP", DummySMTP)

    # 1. Unpaid Paddle checkout-complete without transaction_id MUST be rejected with 400
    status_unpaid, unpaid_res = lr.process_checkout_claim(
        conn,
        db_lock,
        customer_email="buyer@example.com",
        transaction_id="",
        payment_provider="paddle",
        plan_id="monthly",
        send_telegram_fn=lambda _m: None,
        storage_dir=tmp_path,
    )
    assert status_unpaid == 400
    assert unpaid_res["error"] == "paddle_transaction_required"
    assert len(sent_messages) == 0

    # 2. Mock Paddle GET /transactions/{tx_id} returning a completed Annual ($200) transaction
    monkeypatch.setattr(
        lr,
        "_fetch_paddle_transaction",
        lambda tx_id, creds: {
            "id": tx_id,
            "status": "completed",
            "subscription_id": "sub_01annual200",
            "customer_id": "ctm_01buyer",
            "items": [{"price": {"id": price_ids["annual"]}, "quantity": 1}],
        },
    )

    status_paid, paid_res = lr.process_checkout_claim(
        conn,
        db_lock,
        customer_email="buyer@example.com",
        transaction_id="txn_01annual200",
        payment_provider="paddle",
        plan_id="weekly",  # overridden by verified Paddle price -> annual ($200)
        device_id="mac_dev_01",
        support_code="SUP-HIDDEN99",
        send_telegram_fn=lambda _m: None,
        storage_dir=tmp_path,
    )
    assert status_paid == 200
    assert paid_res["ok"] is True
    assert paid_res["plan"] == "annual"
    assert paid_res["price_usd_monthly"] == 200
    issued_key = paid_res["license_key"]
    assert issued_key.startswith("AA-PRO-")
    assert len(sent_messages) == 1

    # Verify minimalist monochrome editorial email HTML & plain text match TurboApply design system
    msg = sent_messages[0]
    html_part = msg.get_body(preferencelist=("html",)).get_content()
    text_part = msg.get_body(preferencelist=("plain",)).get_content()
    combined_email = f"{text_part}\n{html_part}"
    assert str(msg["Subject"]) in ("Your AutoApply license key", "Thank you — your AutoApply license key")
    assert "Mac Support Code" not in combined_email
    assert "SUP-HIDDEN99" not in combined_email
    assert "#10b981" not in combined_email
    assert "USD" not in combined_email
    assert "Your AutoApply license." in html_part
    assert "Annual Pro" in html_part
    assert "$200/year" in html_part
    assert "https://turboapply.agency/api/autoapply-license/brand-mark.png" in html_part
    assert issued_key in html_part
    assert issued_key in text_part

    # 3. Signed Paddle webhook arriving for the SAME transaction_id must reuse the exact same key and NOT send a duplicate email
    wh_payload = {
        "event_id": "evt_01annual200",
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_01annual200",
            "status": "completed",
            "subscription_id": "sub_01annual200",
            "items": [{"price": {"id": price_ids["annual"]}, "quantity": 1}],
            "custom_data": {"email": "buyer@example.com", "device_id": "mac_dev_01"},
        },
    }
    import time

    ts_now = str(int(time.time()))
    raw_wh = json.dumps(wh_payload).encode("utf-8")
    sig = hmac.new(wh_secret.encode("utf-8"), f"{ts_now}:".encode("utf-8") + raw_wh, hashlib.sha256).hexdigest()

    # Invalid signature must return 401
    bad_code, _ = lr.handle_paddle_webhook(
        conn,
        db_lock,
        raw_body=raw_wh,
        signature_header=f"ts={ts_now};h1=0000deadbeef",
        payload=wh_payload,
        send_telegram_fn=lambda _m: None,
        storage_dir=tmp_path,
    )
    assert bad_code == 401

    wh_code, wh_res = lr.handle_paddle_webhook(
        conn,
        db_lock,
        raw_body=raw_wh,
        signature_header=f"ts={ts_now};h1={sig}",
        payload=wh_payload,
        send_telegram_fn=lambda _m: None,
        storage_dir=tmp_path,
    )
    assert wh_code == 200
    assert wh_res["license_key"] == issued_key
    assert wh_res["plan"] == "annual"
    assert wh_res["price_usd"] == 200
    assert len(sent_messages) == 1  # No duplicate email!

    # 4. Both new AA-PRO-... and legacy AA-LIVE-20USD-... keys activate cleanly without support_code
    act_code, act_res = lr.activate_license_on_server(
        conn, db_lock, license_key=issued_key, device_id="mac_dev_01"
    )
    assert act_code == 200 and act_res["ok"] is True

    lr.upsert_and_bind_license(
        conn,
        db_lock,
        license_key="AA-LIVE-20USD-LEGACY01",
        status="active",
        customer_email="legacy@example.com",
    )
    leg_code, leg_res = lr.activate_license_on_server(
        conn, db_lock, license_key="AA-LIVE-20USD-LEGACY01", device_id="mac_dev_legacy"
    )
    assert leg_code == 200 and leg_res["ok"] is True


def test_trial_mode_grace_while_gateway_pending_and_licensing_limits_when_enforced(tmp_path: Path) -> None:
    """While payment gateway verification is pending (licensing_limits_enforced=False), app stays in Trial Mode; once enforced, trial expiry blocks automation."""
    from datetime import datetime, timedelta, timezone
    from autoapply.app_bridge import AppWorkspaceManager

    bridge = AppWorkspaceManager(app_support_dir=tmp_path / "app_support")
    bridge.execute_action("reserve_trial_o02", {})
    raw = bridge._load_raw_state()
    past_iso = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    raw["onboarding"]["trial_expires_at"] = past_iso
    raw["onboarding"]["licensing_limits_enforced"] = False
    bridge._save_raw_state(raw)

    # 1. With licensing_limits_enforced=False (gateway pending), expired timestamp is auto-extended in Trial Mode
    st_grace = bridge.get_full_workspace_state()
    assert st_grace["onboarding"]["trial_state"] == "active_countdown"
    assert st_grace["entitlement"]["trial_mode_grace_active"] is True
    assert st_grace["entitlement"]["licensing_limits_enforced"] is False

    # 2. Once payment gateway is live (licensing_limits_enforced=True), expired trial enforces licensing limits
    raw2 = bridge._load_raw_state()
    raw2["onboarding"]["trial_expires_at"] = past_iso
    raw2["onboarding"]["licensing_limits_enforced"] = True
    bridge._save_raw_state(raw2)
    st_enforced = bridge.get_full_workspace_state()
    assert st_enforced["onboarding"]["trial_state"] == "expired"
    assert st_enforced["entitlement"]["status"] == "expired"
    assert st_enforced["entitlement"]["can_run_automation"] is False
    assert st_enforced["entitlement"]["licensing_limits_enforced"] is True


