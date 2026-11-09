"""Server-issued 48-hour (2-day) trial, flexible Pro pricing plans ($10/wk, $30/mo, $200/yr, $200 lifetime), 1-device seat lease, and post-expiry export (AA-COM-001..003)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
from typing import Any


TRIAL_DURATION_HOURS = 48
TRIAL_DURATION_DAYS = 2
OFFLINE_LEASE_TTL_HOURS = 72
WEEKLY_PRICE_USD = 10
MONTHLY_PRICE_USD = 30
ANNUAL_PRICE_USD = 200
LIFETIME_PRICE_USD = 200
VALID_PLAN_PRICES_USD = (10, 20, 30, 200)

PRICING_PLANS: dict[str, dict[str, Any]] = {
    "weekly": {
        "id": "weekly",
        "name": "Weekly Pass",
        "price_usd": WEEKLY_PRICE_USD,
        "billing_interval": "week",
        "period_days": 7,
        "display_price": "$10 / week",
        "savings_percent": 0,
        "savings_badge": "Flexible Weekly",
        "savings_detail": "Flexible weekly access · Cancel anytime",
        "is_limited_time": False,
    },
    "monthly": {
        "id": "monthly",
        "name": "Monthly Pro",
        "price_usd": MONTHLY_PRICE_USD,
        "billing_interval": "month",
        "period_days": 30,
        "display_price": "$30 / month",
        "savings_percent": 25,
        "savings_badge": "Save 25% ($10/mo off vs. weekly)",
        "savings_detail": "25% cheaper than weekly — you save $10/month ($160/year)",
        "is_limited_time": False,
    },
    "annual": {
        "id": "annual",
        "name": "Annual Pro",
        "price_usd": ANNUAL_PRICE_USD,
        "billing_interval": "year",
        "period_days": 365,
        "display_price": "$200 / year",
        "savings_percent": 62,
        "savings_badge": "Save 62% ($320/yr off vs. weekly)",
        "savings_detail": "62% cheaper than weekly (save $320/yr) · 44% cheaper than monthly (save $160/yr)",
        "is_limited_time": False,
    },
    "lifetime": {
        "id": "lifetime",
        "name": "Lifetime Pro",
        "price_usd": LIFETIME_PRICE_USD,
        "billing_interval": "lifetime",
        "period_days": 36500,
        "display_price": "$200 Lifetime",
        "savings_percent": 100,
        "savings_badge": "LIMITED-TIME-ONLY SPECIAL",
        "savings_detail": "Limited-Time-Only Special: $200 one-time payment (same price as 1 year — pay once, own forever)",
        "is_limited_time": True,
    },
}


@dataclass(frozen=True)
class EntitlementLease:
    device_id: str
    tier: str
    issued_at: str
    expires_at: str
    lease_expires_at: str
    lease_ttl_hours: int
    trial_duration_hours: int
    price_usd_monthly: int
    signature: str


@dataclass(frozen=True)
class AccessEvaluation:
    device_id: str
    tier: str
    status: str
    can_run_automation: bool
    can_read_and_export: bool


@dataclass(frozen=True)
class WebhookOutcome:
    event_id: str
    license_key: str
    status: str
    expires_at: str
    duplicate_ignored: bool


class EntitlementService:
    """Manages 120h server trials, USD 20/month single-seat keys, 72h offline leases, and idempotent webhooks."""

    def __init__(self, db_path: Path | str, signing_secret: str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._secret = signing_secret.encode("utf-8")
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS device_entitlements (
                    device_id TEXT PRIMARY KEY,
                    tier TEXT NOT NULL,
                    license_key TEXT,
                    status TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    max_seen_timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS license_keys (
                    license_key TEXT PRIMARY KEY,
                    price_usd_monthly INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    active_device_id TEXT,
                    expires_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS webhook_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    license_key TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    resulting_status TEXT NOT NULL,
                    resulting_expires_at TEXT NOT NULL
                );
                """
            )

    def _sign_lease_payload(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(self._secret, canonical, hashlib.sha256).hexdigest()

    def verify_lease_signature(self, lease: EntitlementLease) -> bool:
        payload = {
            "device_id": lease.device_id,
            "tier": lease.tier,
            "issued_at": lease.issued_at,
            "expires_at": lease.expires_at,
            "lease_expires_at": lease.lease_expires_at,
            "lease_ttl_hours": lease.lease_ttl_hours,
            "trial_duration_hours": lease.trial_duration_hours,
            "price_usd_monthly": lease.price_usd_monthly,
        }
        expected = self._sign_lease_payload(payload)
        return hmac.compare_digest(expected, lease.signature)

    def activate_trial(
        self,
        *,
        device_id: str,
        automation_ready: bool,
        server_now: datetime,
    ) -> EntitlementLease:
        if not automation_ready:
            raise PermissionError(
                "TRIAL_REQUIRES_AUTOMATION_READY: 48-hour (2-day) trial starts only after onboarding reaches automation readiness (O-09)"
            )
        issued_at = server_now.isoformat()
        expires_at = (server_now + timedelta(hours=TRIAL_DURATION_HOURS)).isoformat()
        lease_expires_at = (server_now + timedelta(hours=OFFLINE_LEASE_TTL_HOURS)).isoformat()

        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO device_entitlements
                (device_id, tier, license_key, status, issued_at, expires_at, lease_expires_at, max_seen_timestamp)
                VALUES (?, 'trial', NULL, 'active', ?, ?, ?, ?)
                """,
                (device_id, issued_at, expires_at, lease_expires_at, issued_at),
            )

        return self._build_lease(
            device_id=device_id,
            tier="trial",
            issued_at=issued_at,
            expires_at=expires_at,
            lease_expires_at=lease_expires_at,
            trial_duration_hours=TRIAL_DURATION_HOURS,
            price_usd_monthly=0,
        )

    def issue_license_key(
        self,
        *,
        license_key: str,
        price_usd_monthly: int = MONTHLY_PRICE_USD,
        server_now: datetime,
        period_days: int = 30,
    ) -> None:
        if int(price_usd_monthly) not in VALID_PLAN_PRICES_USD:
            raise ValueError(
                f"AutoApply Pro plan price must be one of USD {VALID_PLAN_PRICES_USD} ($10/wk, $30/mo, $200/yr, or $200 lifetime)"
            )
        expires_at = (server_now + timedelta(days=max(1, int(period_days)))).isoformat()
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO license_keys (license_key, price_usd_monthly, status, active_device_id, expires_at)
                VALUES (?, ?, 'active', NULL, ?)
                """,
                (license_key, int(price_usd_monthly), expires_at),
            )

    def activate_license_key(
        self,
        *,
        license_key: str,
        device_id: str,
        server_now: datetime,
    ) -> EntitlementLease:
        row = self._conn.execute(
            "SELECT * FROM license_keys WHERE license_key = ?",
            (license_key,),
        ).fetchone()
        if row is None or row["status"] != "active":
            raise PermissionError("LICENSE_KEY_INVALID_OR_INACTIVE")

        active_device = row["active_device_id"]
        if active_device is not None and active_device != device_id:
            raise PermissionError(
                f"DEVICE_SEAT_LIMIT_EXCEEDED: license key '{license_key}' is already bound to '{active_device}' (max 1 active device)"
            )

        issued_at = server_now.isoformat()
        expires_at = str(row["expires_at"])
        lease_expires_at = (server_now + timedelta(hours=OFFLINE_LEASE_TTL_HOURS)).isoformat()

        with self._conn:
            self._conn.execute(
                "UPDATE license_keys SET active_device_id = ? WHERE license_key = ?",
                (device_id, license_key),
            )
            self._conn.execute(
                """
                INSERT OR REPLACE INTO device_entitlements
                (device_id, tier, license_key, status, issued_at, expires_at, lease_expires_at, max_seen_timestamp)
                VALUES (?, 'paid_monthly', ?, 'active', ?, ?, ?, ?)
                """,
                (device_id, license_key, issued_at, expires_at, lease_expires_at, issued_at),
            )

        return self._build_lease(
            device_id=device_id,
            tier="paid_monthly",
            issued_at=issued_at,
            expires_at=expires_at,
            lease_expires_at=lease_expires_at,
            trial_duration_hours=0,
            price_usd_monthly=int(row["price_usd_monthly"]),
        )

    def transfer_device_seat(
        self,
        *,
        license_key: str,
        from_device_id: str,
        to_device_id: str,
        server_now: datetime,
    ) -> EntitlementLease:
        row = self._conn.execute(
            "SELECT * FROM license_keys WHERE license_key = ?",
            (license_key,),
        ).fetchone()
        if row is None or row["active_device_id"] != from_device_id:
            raise PermissionError("SEAT_TRANSFER_DENIED: license key is not bound to from_device_id")

        with self._conn:
            self._conn.execute(
                "UPDATE device_entitlements SET status = 'seat_transferred', max_seen_timestamp = ? WHERE device_id = ?",
                (server_now.isoformat(), from_device_id),
            )
            self._conn.execute(
                "UPDATE license_keys SET active_device_id = NULL WHERE license_key = ?",
                (license_key,),
            )

        return self.activate_license_key(
            license_key=license_key,
            device_id=to_device_id,
            server_now=server_now,
        )

    def process_webhook_event(
        self,
        *,
        event_id: str,
        event_type: str,
        license_key: str,
        server_now: datetime,
        period_days: int = 30,
    ) -> WebhookOutcome:
        existing = self._conn.execute(
            "SELECT * FROM webhook_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if existing is not None:
            return WebhookOutcome(
                event_id=event_id,
                license_key=license_key,
                status=str(existing["resulting_status"]),
                expires_at=str(existing["resulting_expires_at"]),
                duplicate_ignored=True,
            )

        row = self._conn.execute(
            "SELECT * FROM license_keys WHERE license_key = ?",
            (license_key,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown license_key: {license_key}")

        if event_type in {"subscription.renewed", "subscription.purchased"}:
            new_status = "active"
            new_expires = (server_now + timedelta(days=max(1, int(period_days)))).isoformat()
        elif event_type in {"subscription.refunded", "subscription.cancelled_expired", "payment.failed_final"}:
            new_status = "expired"
            new_expires = server_now.isoformat()
        else:
            raise ValueError(f"Unsupported webhook event_type: {event_type}")

        with self._conn:
            self._conn.execute(
                "UPDATE license_keys SET status = ?, expires_at = ? WHERE license_key = ?",
                (new_status, new_expires, license_key),
            )
            if row["active_device_id"]:
                self._conn.execute(
                    """
                    UPDATE device_entitlements
                    SET status = ?, expires_at = ?, max_seen_timestamp = ?
                    WHERE device_id = ?
                    """,
                    (new_status, new_expires, server_now.isoformat(), row["active_device_id"]),
                )
            self._conn.execute(
                """
                INSERT INTO webhook_events
                (event_id, event_type, license_key, processed_at, resulting_status, resulting_expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, event_type, license_key, server_now.isoformat(), new_status, new_expires),
            )

        return WebhookOutcome(
            event_id=event_id,
            license_key=license_key,
            status=new_status,
            expires_at=new_expires,
            duplicate_ignored=False,
        )

    def evaluate_access(
        self,
        *,
        device_id: str,
        current_time: datetime,
    ) -> AccessEvaluation:
        row = self._conn.execute(
            "SELECT * FROM device_entitlements WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        if row is None:
            return AccessEvaluation(
                device_id=device_id,
                tier="none",
                status="unactivated",
                can_run_automation=False,
                can_read_and_export=True,
            )

        max_seen = datetime.fromisoformat(str(row["max_seen_timestamp"]))
        if current_time < max_seen:
            raise PermissionError(
                "CLOCK_ROLLBACK_DETECTED: local clock is earlier than previously observed timestamp; online revalidation required"
            )

        with self._conn:
            self._conn.execute(
                "UPDATE device_entitlements SET max_seen_timestamp = ? WHERE device_id = ?",
                (current_time.isoformat(), device_id),
            )

        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        status = str(row["status"])
        if current_time >= expires_at or status != "active":
            return AccessEvaluation(
                device_id=device_id,
                tier=str(row["tier"]),
                status="expired" if current_time >= expires_at else status,
                can_run_automation=False,
                can_read_and_export=True,
            )

        return AccessEvaluation(
            device_id=device_id,
            tier=str(row["tier"]),
            status="active",
            can_run_automation=True,
            can_read_and_export=True,
        )

    @staticmethod
    def export_user_bundle(
        *,
        device_id: str,
        applications: list[dict[str, Any]],
        documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Always permitted even after trial or paid subscription expiry (AA-COM-003, T-LIC-04)."""
        return {
            "device_id": device_id,
            "read_only_mode": True,
            "applications": list(applications),
            "documents": list(documents),
        }

    def _build_lease(
        self,
        *,
        device_id: str,
        tier: str,
        issued_at: str,
        expires_at: str,
        lease_expires_at: str,
        trial_duration_hours: int,
        price_usd_monthly: int,
    ) -> EntitlementLease:
        payload = {
            "device_id": device_id,
            "tier": tier,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "lease_expires_at": lease_expires_at,
            "lease_ttl_hours": OFFLINE_LEASE_TTL_HOURS,
            "trial_duration_hours": trial_duration_hours,
            "price_usd_monthly": price_usd_monthly,
        }
        sig = self._sign_lease_payload(payload)
        return EntitlementLease(
            device_id=device_id,
            tier=tier,
            issued_at=issued_at,
            expires_at=expires_at,
            lease_expires_at=lease_expires_at,
            lease_ttl_hours=OFFLINE_LEASE_TTL_HOURS,
            trial_duration_hours=trial_duration_hours,
            price_usd_monthly=price_usd_monthly,
            signature=sig,
        )

    def process_paddle_webhook(
        self,
        *,
        payload: dict[str, Any],
        server_now: datetime,
        raw_body: bytes | str | None = None,
        signature_header: str | None = None,
        webhook_secret: str | None = None,
    ) -> dict[str, Any]:
        """Verify and process an official Paddle Billing v2 webhook event."""
        if webhook_secret:
            body_to_verify: bytes | str = (
                raw_body if raw_body is not None else json.dumps(payload, separators=(",", ":"))
            )
            if not verify_paddle_webhook_signature(
                raw_body=body_to_verify,
                signature_header=str(signature_header or ""),
                webhook_secret=webhook_secret,
            ):
                raise PermissionError("PADDLE_SIGNATURE_INVALID: webhook signature verification failed")

        norm = normalize_paddle_webhook_payload(payload)
        license_key = norm["license_key"]
        existing = self._conn.execute(
            "SELECT * FROM license_keys WHERE license_key = ?",
            (license_key,),
        ).fetchone()
        if existing is None:
            self.issue_license_key(
                license_key=license_key,
                price_usd_monthly=MONTHLY_PRICE_USD,
                server_now=server_now,
                period_days=int(norm["period_days"]),
            )

        outcome = self.process_webhook_event(
            event_id=norm["event_id"],
            event_type=norm["internal_event_type"],
            license_key=license_key,
            server_now=server_now,
            period_days=int(norm["period_days"]),
        )

        device_id = norm.get("device_id") or ""
        lease: EntitlementLease | None = None
        if device_id and outcome.status == "active":
            cur_row = self._conn.execute(
                "SELECT active_device_id FROM license_keys WHERE license_key = ?",
                (license_key,),
            ).fetchone()
            bound_dev = str(cur_row["active_device_id"] or "") if cur_row else ""
            if not bound_dev or bound_dev == device_id:
                lease = self.activate_license_key(
                    license_key=license_key,
                    device_id=device_id,
                    server_now=server_now,
                )

        return {
            "outcome": outcome,
            "license_key": license_key,
            "paddle_event_type": norm["paddle_event_type"],
            "internal_event_type": norm["internal_event_type"],
            "subscription_id": norm["subscription_id"],
            "transaction_id": norm["transaction_id"],
            "customer_id": norm["customer_id"],
            "customer_email": norm["customer_email"],
            "device_id": device_id,
            "support_code": norm["support_code"],
            "lease": lease,
        }


def derive_paddle_license_key(seed: str) -> str:
    """Derive a deterministic, high-entropy AA-LIVE-20USD-XXXX-XXXX-XXXX license key."""
    clean = str(seed or "AUTOAPPLY-PRO").strip()
    digest = hashlib.sha256(f"autoapply-paddle-v1:{clean}".encode("utf-8")).hexdigest().upper()
    return f"AA-LIVE-20USD-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}"


def verify_paddle_webhook_signature(
    *,
    raw_body: bytes | str,
    signature_header: str,
    webhook_secret: str,
    tolerance_seconds: int = 300,
    current_timestamp: int | None = None,
) -> bool:
    """Verify Paddle Billing v2 `Paddle-Signature: ts=...;h1=...` HMAC-SHA256 header."""
    if not signature_header or not webhook_secret:
        return False
    ts_val = ""
    h1_values: list[str] = []
    for part in str(signature_header).replace(",", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if k == "ts":
            ts_val = v
        elif k == "h1" and v:
            h1_values.append(v.lower())
    if not ts_val or not h1_values:
        return False
    try:
        ts_int = int(ts_val)
    except ValueError:
        return False
    if current_timestamp is not None and tolerance_seconds > 0:
        if abs(int(current_timestamp) - ts_int) > tolerance_seconds:
            return False
    body_str = raw_body.decode("utf-8", errors="replace") if isinstance(raw_body, bytes) else str(raw_body)
    signed_payload = f"{ts_val}:{body_str}".encode("utf-8")
    expected = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest().lower()
    return any(hmac.compare_digest(expected, cand) for cand in h1_values)


def normalize_paddle_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Paddle Billing v2 webhook event into internal EntitlementService fields."""
    event_id = str(payload.get("event_id") or payload.get("notification_id") or "").strip()
    if not event_id:
        raise ValueError("Missing Paddle event_id")
    paddle_event_type = str(payload.get("event_type") or "").strip().lower()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    custom_data = data.get("custom_data") if isinstance(data.get("custom_data"), dict) else {}

    obj_id = str(data.get("id") or "").strip()
    subscription_id = str(
        data.get("subscription_id")
        or (obj_id if obj_id.startswith("sub_") else "")
        or custom_data.get("subscription_id")
        or ""
    ).strip()
    transaction_id = str(
        data.get("transaction_id")
        or (obj_id if obj_id.startswith("txn_") else "")
        or custom_data.get("transaction_id")
        or ""
    ).strip()
    customer_id = str(data.get("customer_id") or custom_data.get("customer_id") or "").strip()

    customer_obj = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    customer_email = str(
        custom_data.get("email")
        or custom_data.get("customer_email")
        or customer_obj.get("email")
        or data.get("customer_email")
        or ""
    ).strip()
    device_id = str(custom_data.get("device_id") or "").strip()
    support_code = str(custom_data.get("support_code") or "").strip()

    explicit_key = str(custom_data.get("license_key") or data.get("license_key") or "").strip()
    if explicit_key and explicit_key.upper().startswith("AA-LIVE-20USD-"):
        license_key = explicit_key.upper()
    else:
        seed = subscription_id or support_code or device_id or customer_email or transaction_id or event_id
        license_key = derive_paddle_license_key(seed)

    plan_id = str(custom_data.get("plan") or custom_data.get("plan_id") or data.get("plan") or "monthly").strip().lower()
    if plan_id in PRICING_PLANS:
        period_days = int(PRICING_PLANS[plan_id]["period_days"])
    else:
        period_days = 30
    billing_period = data.get("current_billing_period")
    if isinstance(billing_period, dict):
        starts_at = str(billing_period.get("starts_at") or "").strip()
        ends_at = str(billing_period.get("ends_at") or "").strip()
        if starts_at and ends_at:
            try:
                dt_start = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
                dt_end = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
                computed_days = int(round((dt_end - dt_start).total_seconds() / 86400.0))
                if 1 <= computed_days <= 36600:
                    period_days = computed_days
            except Exception:
                pass

    data_status = str(data.get("status") or "").strip().lower()
    action = str(data.get("action") or "").strip().lower()

    if paddle_event_type in ("transaction.completed", "transaction.paid", "subscription.created", "subscription.activated"):
        internal_event_type = "subscription.purchased"
    elif paddle_event_type in ("subscription.updated", "subscription.resumed"):
        if data_status in ("canceled", "cancelled"):
            internal_event_type = "subscription.cancelled_expired"
        elif data_status in ("past_due", "paused"):
            internal_event_type = "payment.failed_final"
        else:
            internal_event_type = "subscription.renewed"
    elif paddle_event_type in ("subscription.canceled", "subscription.cancelled"):
        internal_event_type = "subscription.cancelled_expired"
    elif paddle_event_type in ("subscription.past_due", "subscription.paused", "transaction.payment_failed"):
        internal_event_type = "payment.failed_final"
    elif paddle_event_type in ("adjustment.updated", "adjustment.created"):
        if action in ("refund", "chargeback", "credit") and data_status in ("approved", "completed", ""):
            internal_event_type = "subscription.refunded"
        else:
            internal_event_type = "subscription.renewed"
    elif paddle_event_type in (
        "subscription.purchased",
        "subscription.renewed",
        "subscription.refunded",
        "subscription.cancelled_expired",
        "payment.failed_final",
    ):
        internal_event_type = paddle_event_type
    else:
        raise ValueError(f"Unsupported Paddle webhook event_type: {paddle_event_type}")

    return {
        "event_id": event_id,
        "paddle_event_type": paddle_event_type,
        "internal_event_type": internal_event_type,
        "license_key": license_key,
        "subscription_id": subscription_id,
        "transaction_id": transaction_id,
        "customer_id": customer_id,
        "customer_email": customer_email,
        "device_id": device_id,
        "support_code": support_code,
        "period_days": period_days,
    }
