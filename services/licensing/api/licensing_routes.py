#!/usr/bin/env python3
"""Server-side Paddle Billing v2 & On-Chain Crypto subscription checkout,
daily-locked crypto exchange rates, TXID claim deduplication, Zoho SMTP license
email delivery (info@turboapply.agency), and automatic macOS device activation.
"""
from __future__ import annotations

import base64
import datetime as dt
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import hashlib
import hmac
import html
import json
import os
import re
import smtplib
import sqlite3
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

MONTHLY_PRICE_USD = 30
WEEKLY_PRICE_USD = 10
ANNUAL_PRICE_USD = 200
LIFETIME_PRICE_USD = 200
TRIAL_DURATION_HOURS = 48
DEFAULT_PERIOD_DAYS = 30
OFFLINE_LEASE_TTL_HOURS = 72

DEFAULT_CRYPTO_WALLETS: dict[str, str] = {
    "solana": "9DkQ46xFcYwy8jR2PouvuaH8Z64P6VjUi1tnocHPNsG1",
    "evm": "0x75868A0877dF87Da4DBFa67a3015BFB30a580108",
    "tron": "TJVdUNhsnqE9q2rKD3M3YqNEAYBAiwmyec",
    "btc": "bc1qce6rpphsfdffm2l3h40a7n8vp2qwm6dyfptdaf",
}

DEFAULT_FALLBACK_RATES_USD: dict[str, float] = {
    "BTC": 80616.00,
    "ETH": 2334.54,
    "SOL": 101.06,
    "USDC": 1.00,
    "USDT": 1.00,
}

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
        "savings_detail": "$10 per week · Cancel anytime",
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
        "savings_badge": "Save 25% ($10/mo off)",
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
        "savings_badge": "Save 62% ($320/yr off)",
        "savings_detail": "62% cheaper than weekly (save $320/yr) · 44% cheaper than monthly (save $160/yr)",
        "is_limited_time": False,
    },
    "lifetime": {
        "id": "lifetime",
        "name": "Lifetime Pro (Limited-Time Special)",
        "price_usd": LIFETIME_PRICE_USD,
        "billing_interval": "lifetime",
        "period_days": 36500,
        "display_price": "$200 Lifetime",
        "savings_percent": 100,
        "savings_badge": "LIMITED-TIME-ONLY SPECIAL",
        "savings_detail": "Limited-time-only special: $200 one-time for lifetime access (same price as 1 year — never pay again)",
        "is_limited_time": True,
    },
}

_RATES_LOCK = threading.Lock()


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def utc_now_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def derive_license_key(seed: str) -> str:
    clean = str(seed or "AUTOAPPLY-PRO").strip()
    digest = hashlib.sha256(f"autoapply-paddle-v1:{clean}".encode("utf-8")).hexdigest().upper()
    return f"AA-PRO-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}"


def is_explicit_pro_license_key(value: str) -> bool:
    up = str(value or "").strip().upper()
    return up.startswith(("AA-PRO-", "AA-LIVE-20USD-"))


def normalize_incoming_license_key(raw_key: str, conn: sqlite3.Connection | None = None) -> str:
    clean = str(raw_key or "").strip().upper()
    if not clean:
        return ""
    if clean.startswith("AA-LIVE-20USD-AA-PRO-"):
        clean = clean[len("AA-LIVE-20USD-") :]
    if clean.startswith(("AA-PRO-", "AA-LIVE-20USD-")):
        if conn is not None and clean.startswith("AA-LIVE-20USD-"):
            row = conn.execute("SELECT 1 FROM license_keys WHERE license_key = ? LIMIT 1", (clean,)).fetchone()
            if row is None:
                alt = "AA-PRO-" + clean[len("AA-LIVE-20USD-") :]
                alt_row = conn.execute("SELECT 1 FROM license_keys WHERE license_key = ? LIMIT 1", (alt,)).fetchone()
                if alt_row is not None:
                    return alt
        return clean
    if conn is not None:
        for cand in (f"AA-PRO-{clean}", f"AA-LIVE-20USD-{clean}"):
            row = conn.execute("SELECT 1 FROM license_keys WHERE license_key = ? LIMIT 1", (cand,)).fetchone()
            if row is not None:
                return cand
    return f"AA-PRO-{clean}"


def _resolve_storage_dir(storage_dir: Path | None = None) -> Path:
    if storage_dir is not None:
        return storage_dir
    env_dir = os.getenv("AUTOAPPLY_FEEDBACK_STORAGE_DIR", "").strip()
    return Path(env_dir) if env_dir else Path("/var/lib/autoapply-feedback")


def load_crypto_wallets(storage_dir: Path | None = None) -> dict[str, str]:
    wallets = dict(DEFAULT_CRYPTO_WALLETS)
    if storage_dir is not None:
        wallet_file = storage_dir / "crypto_wallets.json"
        if wallet_file.is_file():
            try:
                loaded = json.loads(wallet_file.read_text(encoding="utf-8"))
                pub = loaded.get("public_addresses") if isinstance(loaded, dict) else None
                if isinstance(pub, dict):
                    for k in ("solana", "evm", "tron", "btc"):
                        val = str(pub.get(k) or "").strip()
                        if val:
                            wallets[k] = val
            except Exception:
                pass
    return wallets


def _fetch_live_crypto_spot_rates() -> tuple[dict[str, float], str]:
    """Fetch live USD spot prices for BTC, ETH, and SOL with multi-provider fallback."""
    headers = {"User-Agent": "AutoApplyLicenseEngine/1.0 (+https://turboapply.agency)"}

    # Provider 1: CoinGecko Simple Price API
    try:
        req = urllib.request.Request(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            btc = float(data["bitcoin"]["usd"])
            eth = float(data["ethereum"]["usd"])
            sol = float(data["solana"]["usd"])
            if btc > 1000 and eth > 50 and sol > 1:
                return {"BTC": btc, "ETH": eth, "SOL": sol, "USDC": 1.0, "USDT": 1.0}, "coingecko"
    except Exception:
        pass

    # Provider 2: Binance Spot Price API
    try:
        req = urllib.request.Request(
            "https://api.binance.com/api/v3/ticker/price?symbols=%5B%22BTCUSDT%22,%22ETHUSDT%22,%22SOLUSDT%22%5D",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            items = json.loads(resp.read().decode("utf-8"))
            mapping = {str(item["symbol"]): float(item["price"]) for item in items if isinstance(item, dict)}
            btc = float(mapping.get("BTCUSDT") or 0)
            eth = float(mapping.get("ETHUSDT") or 0)
            sol = float(mapping.get("SOLUSDT") or 0)
            if btc > 1000 and eth > 50 and sol > 1:
                return {"BTC": btc, "ETH": eth, "SOL": sol, "USDC": 1.0, "USDT": 1.0}, "binance"
    except Exception:
        pass

    # Provider 3: Coinbase Spot Price API
    try:
        out: dict[str, float] = {"USDC": 1.0, "USDT": 1.0}
        for sym in ("BTC", "ETH", "SOL"):
            req = urllib.request.Request(
                f"https://api.coinbase.com/v2/prices/{sym}-USD/spot",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                out[sym] = float(body["data"]["amount"])
        if out.get("BTC", 0) > 1000 and out.get("ETH", 0) > 50 and out.get("SOL", 0) > 1:
            return out, "coinbase"
    except Exception:
        pass

    return dict(DEFAULT_FALLBACK_RATES_USD), "fallback_locked"


def _build_plan_crypto_quotes(
    rates_usd: dict[str, float],
    locked_date: str,
) -> dict[str, dict[str, Any]]:
    btc_rate = max(1.0, float(rates_usd.get("BTC") or DEFAULT_FALLBACK_RATES_USD["BTC"]))
    eth_rate = max(1.0, float(rates_usd.get("ETH") or DEFAULT_FALLBACK_RATES_USD["ETH"]))
    sol_rate = max(0.01, float(rates_usd.get("SOL") or DEFAULT_FALLBACK_RATES_USD["SOL"]))

    quotes: dict[str, dict[str, Any]] = {}
    for plan_id, plan_meta in PRICING_PLANS.items():
        usd = float(plan_meta["price_usd"])
        btc_full = f"{usd / btc_rate:.8f}"
        eth_full = f"{usd / eth_rate:.6f}"
        sol_full = f"{usd / sol_rate:.6f}"
        usdc_full = f"{usd:.2f}"
        usdt_full = f"{usd:.2f}"
        quotes[plan_id] = {
            "price_usd": int(usd),
            "locked_date": locked_date,
            "exact": {
                "BTC": btc_full,
                "ETH": eth_full,
                "SOL": sol_full,
                "USDC": usdc_full,
                "USDT": usdt_full,
            },
            "display": {
                "solana": f"{usdc_full} USDC / USDT (or {sol_full} SOL)",
                "evm": f"{usdc_full} USDC / USDT (or {eth_full} ETH)",
                "tron": f"{usdt_full} USDT (TRC-20)",
                "btc": f"{btc_full} BTC (${int(usd)} USD · rate locked {locked_date})",
            },
        }
    return quotes


def get_daily_locked_crypto_rates(
    storage_dir: Path | None = None,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return daily-locked crypto exchange rates (refreshed once per UTC calendar day)."""
    now = utc_now()
    today_utc = now.strftime("%Y-%m-%d")
    next_midnight = (now.date() + dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    cache_file = (storage_dir / "crypto_rates_daily.json") if storage_dir is not None else None

    with _RATES_LOCK:
        if not force_refresh and cache_file is not None and cache_file.is_file():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                if (
                    isinstance(cached, dict)
                    and str(cached.get("locked_date") or "") == today_utc
                    and isinstance(cached.get("rates_usd"), dict)
                    and float(cached["rates_usd"].get("BTC") or 0) > 1000
                ):
                    return cached
            except Exception:
                pass

        rates_usd, provider = _fetch_live_crypto_spot_rates()
        # If live fetch fell back and we have a previous cached rate on disk, use its rates_usd
        if provider == "fallback_locked" and cache_file is not None and cache_file.is_file():
            try:
                prev = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(prev, dict) and isinstance(prev.get("rates_usd"), dict):
                    if float(prev["rates_usd"].get("BTC") or 0) > 1000:
                        rates_usd = prev["rates_usd"]
            except Exception:
                pass

        payload: dict[str, Any] = {
            "locked_date": today_utc,
            "locked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "refreshes_at": next_midnight,
            "refresh_policy": "daily_utc_midnight",
            "source": provider,
            "rates_usd": {
                "BTC": round(float(rates_usd["BTC"]), 2),
                "ETH": round(float(rates_usd["ETH"]), 2),
                "SOL": round(float(rates_usd["SOL"]), 2),
                "USDC": 1.0,
                "USDT": 1.0,
            },
            "plans": _build_plan_crypto_quotes(rates_usd, today_utc),
        }

        if cache_file is not None:
            try:
                cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            except Exception:
                pass

        return payload


def sign_lease(payload: dict[str, Any], secret: str) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def build_signed_lease(
    *,
    device_id: str,
    support_code: str,
    license_key: str,
    issued_at: str,
    expires_at: str,
    signing_secret: str,
) -> dict[str, Any]:
    now_dt = utc_now()
    lease_expires = (now_dt + dt.timedelta(hours=OFFLINE_LEASE_TTL_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "device_id": device_id or "mac_local_device",
        "support_code": support_code,
        "license_key": license_key,
        "tier": "paid",
        "issued_at": issued_at,
        "expires_at": expires_at,
        "lease_expires_at": lease_expires,
        "lease_ttl_hours": OFFLINE_LEASE_TTL_HOURS,
        "trial_duration_hours": TRIAL_DURATION_HOURS,
        "price_usd_monthly": MONTHLY_PRICE_USD,
    }
    payload["signature"] = sign_lease(payload, signing_secret)
    return payload


def verify_paddle_signature(
    *,
    raw_body: bytes | str,
    signature_header: str,
    webhook_secret: str,
    tolerance_seconds: int = 600,
) -> bool:
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
    if tolerance_seconds > 0:
        now_ts = int(utc_now().timestamp())
        if abs(now_ts - ts_int) > tolerance_seconds:
            return False
    body_str = raw_body.decode("utf-8", errors="replace") if isinstance(raw_body, bytes) else str(raw_body)
    signed_payload = f"{ts_val}:{body_str}".encode("utf-8")
    expected = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest().lower()
    return any(hmac.compare_digest(expected, cand) for cand in h1_values)


def init_licensing_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS license_keys (
            license_key TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'active',
            price_usd_monthly INTEGER NOT NULL DEFAULT 30,
            customer_email TEXT NOT NULL DEFAULT '',
            customer_id TEXT NOT NULL DEFAULT '',
            subscription_id TEXT NOT NULL DEFAULT '',
            transaction_id TEXT NOT NULL DEFAULT '',
            payment_provider TEXT NOT NULL DEFAULT 'paddle',
            active_device_id TEXT NOT NULL DEFAULT '',
            support_code TEXT NOT NULL DEFAULT '',
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            manage_url TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_license_keys_support_code ON license_keys(support_code);
        CREATE INDEX IF NOT EXISTS idx_license_keys_device_id ON license_keys(active_device_id);
        CREATE INDEX IF NOT EXISTS idx_license_keys_subscription_id ON license_keys(subscription_id);
        CREATE INDEX IF NOT EXISTS idx_license_keys_email ON license_keys(customer_email);
        CREATE INDEX IF NOT EXISTS idx_license_keys_transaction_id ON license_keys(transaction_id);

        CREATE TABLE IF NOT EXISTS checkout_sessions (
            session_id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL DEFAULT '',
            support_code TEXT NOT NULL DEFAULT '',
            customer_email TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            license_key TEXT NOT NULL DEFAULT '',
            subscription_id TEXT NOT NULL DEFAULT '',
            transaction_id TEXT NOT NULL DEFAULT '',
            payment_provider TEXT NOT NULL DEFAULT 'paddle',
            created_at TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_checkout_sessions_support_code ON checkout_sessions(support_code);
        CREATE INDEX IF NOT EXISTS idx_checkout_sessions_device_id ON checkout_sessions(device_id);

        CREATE TABLE IF NOT EXISTS paddle_webhook_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            license_key TEXT NOT NULL DEFAULT '',
            subscription_id TEXT NOT NULL DEFAULT '',
            transaction_id TEXT NOT NULL DEFAULT '',
            resulting_status TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            processed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS license_email_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_email TEXT NOT NULL,
            sender_email TEXT NOT NULL,
            license_key TEXT NOT NULL,
            transaction_id TEXT NOT NULL DEFAULT '',
            is_resend INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'sent',
            error_message TEXT NOT NULL DEFAULT '',
            sent_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS lifecycle_email_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_email TEXT NOT NULL,
            sender_email TEXT NOT NULL,
            template_type TEXT NOT NULL,
            license_key TEXT NOT NULL DEFAULT '',
            reference_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'sent',
            error_message TEXT NOT NULL DEFAULT '',
            sent_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_lifecycle_email_dedup
            ON lifecycle_email_log(template_type, recipient_email, reference_id);

        CREATE TABLE IF NOT EXISTS trial_registrations (
            device_id TEXT PRIMARY KEY,
            customer_email TEXT NOT NULL DEFAULT '',
            trial_started_at TEXT NOT NULL,
            trial_expires_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    for col_sql in (
        "ALTER TABLE license_keys ADD COLUMN plan_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE license_keys ADD COLUMN pause_until TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE license_keys ADD COLUMN cancellation_reason TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE license_keys ADD COLUMN cancelled_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE license_keys ADD COLUMN gateway_receipt_id TEXT NOT NULL DEFAULT ''",
    ):
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()


def infer_plan_id_from_license(
    *,
    license_key: str = "",
    plan_id: str = "",
    price_usd: int = 0,
    issued_at: str = "",
    expires_at: str = "",
    period_days: int = 0,
) -> str:
    clean_plan = str(plan_id or "").strip().lower()
    if clean_plan in PRICING_PLANS:
        return clean_plan

    up_key = str(license_key or "").strip().upper()
    delta_days = 0
    if issued_at and expires_at:
        try:
            dt_iss = dt.datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
            dt_exp = dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            delta_days = int(round((dt_exp - dt_iss).total_seconds() / 86400.0))
        except Exception:
            delta_days = 0

    if "LIFE" in up_key:
        return "lifetime"
    if "10USD" in up_key or "WEEK" in up_key:
        return "weekly"
    if "200USD" in up_key or "ANNUAL" in up_key or "YEAR" in up_key:
        if period_days > 1000 or delta_days > 1000:
            return "lifetime"
        return "annual"
    if "30USD" in up_key or "MONTH" in up_key:
        return "monthly"

    if period_days > 1000 or delta_days > 1000:
        return "lifetime"
    if period_days >= 300 or delta_days >= 300:
        return "annual"
    if (0 < period_days <= 10) or (0 < delta_days <= 10):
        return "weekly"

    if price_usd == WEEKLY_PRICE_USD:
        return "weekly"
    if price_usd >= ANNUAL_PRICE_USD:
        return "annual"
    return "monthly"


def build_plan_summary_fields(plan_id: str) -> dict[str, Any]:
    norm = str(plan_id or "monthly").strip().lower()
    if norm not in PRICING_PLANS:
        norm = "monthly"
    meta = PRICING_PLANS[norm]
    labels = {
        "weekly": ("Weekly Pass", "Weekly Pass ($10/week)", True, "monthly", True),
        "monthly": ("Monthly Pro", "Monthly Pro ($30/month)", True, "annual", True),
        "annual": ("Annual Pro", "Annual Pro ($200/year)", True, "lifetime", True),
        "lifetime": ("Lifetime Pro", "Lifetime Pro ($200 Lifetime)", False, "", False),
    }
    short_name, full_label, can_upgrade, rec_upgrade, is_recurring = labels[norm]
    return {
        "plan": norm,
        "plan_name": short_name,
        "plan_label": full_label,
        "display_price": str(meta["display_price"]),
        "billing_interval": str(meta["billing_interval"]),
        "can_upgrade": can_upgrade,
        "recommended_upgrade_plan": rec_upgrade,
        "is_recurring": is_recurring,
    }


_LIVE_PROMOTION_CHECK_LOCK = threading.Lock()
_LAST_LIVE_PROMOTION_CHECK_TS: float = 0.0


def _maybe_promote_live_paddle_config(sdir: Path, current_cfg: dict[str, Any]) -> dict[str, Any]:
    """Automatically promote paddle_live_config.json -> paddle_config.json as soon as Paddle enables live checkouts."""
    global _LAST_LIVE_PROMOTION_CHECK_TS
    env_mode = str(current_cfg.get("paddle_environment") or current_cfg.get("environment") or "").strip().lower()
    if env_mode == "production":
        return current_cfg
    live_path = sdir / "paddle_live_config.json"
    if not live_path.is_file():
        return current_cfg
    now_ts = utc_now().timestamp()
    with _LIVE_PROMOTION_CHECK_LOCK:
        if (now_ts - _LAST_LIVE_PROMOTION_CHECK_TS) < 900.0:
            return current_cfg
        _LAST_LIVE_PROMOTION_CHECK_TS = now_ts
        try:
            live_cfg = json.loads(live_path.read_text(encoding="utf-8"))
            if not isinstance(live_cfg, dict):
                return current_cfg
            api_key = str(live_cfg.get("paddle_api_key") or live_cfg.get("api_key") or "").strip()
            pri = str(
                (live_cfg.get("paddle_price_ids") or {}).get("monthly")
                or live_cfg.get("paddle_price_id")
                or ""
            ).strip()
            if not api_key or not pri:
                return current_cfg
            req = urllib.request.Request(
                "https://api.paddle.com/transactions",
                data=json.dumps({"items": [{"price_id": pri, "quantity": 1}]}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AutoApplyLicenseEngine/1.0 (+https://turboapply.agency)",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                if resp.status in (200, 201):
                    cfg_path = sdir / "paddle_config.json"
                    cfg_path.write_text(json.dumps(live_cfg, indent=2), encoding="utf-8")
                    return live_cfg
        except Exception:
            pass
    return current_cfg


def _read_paddle_config_file(storage_dir: Path | None = None) -> dict[str, Any]:
    sdir = _resolve_storage_dir(storage_dir)
    cfg_path = sdir / "paddle_config.json"
    if cfg_path.is_file():
        try:
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return _maybe_promote_live_paddle_config(sdir, loaded)
        except Exception:
            pass
    return {}


def _extract_paddle_price_ids(file_cfg: dict[str, Any]) -> dict[str, str]:
    raw_map = file_cfg.get("paddle_price_ids") or file_cfg.get("price_ids")
    out: dict[str, str] = {}
    for plan_k in ("weekly", "monthly", "annual", "lifetime"):
        val = str(
            (raw_map.get(plan_k) if isinstance(raw_map, dict) else "")
            or os.getenv(f"PADDLE_PRICE_ID_{plan_k.upper()}", "")
            or ""
        ).strip()
        if val:
            out[plan_k] = val
    fallback_monthly = str(
        file_cfg.get("paddle_price_id")
        or file_cfg.get("price_id")
        or os.getenv("PADDLE_PRICE_ID")
        or ""
    ).strip()
    if fallback_monthly and "monthly" not in out:
        out["monthly"] = fallback_monthly
    return out


def _load_paddle_server_credentials(storage_dir: Path | None = None) -> dict[str, Any]:
    file_cfg = _read_paddle_config_file(storage_dir)
    env_mode = str(
        file_cfg.get("paddle_environment")
        or file_cfg.get("environment")
        or os.getenv("PADDLE_ENVIRONMENT")
        or "production"
    ).strip().lower()
    if env_mode not in ("sandbox", "production"):
        env_mode = "production"
    api_key = str(
        os.getenv("PADDLE_API_KEY")
        or file_cfg.get("paddle_api_key")
        or file_cfg.get("api_key")
        or ""
    ).strip()
    webhook_secret = str(
        os.getenv("PADDLE_WEBHOOK_SECRET")
        or file_cfg.get("paddle_webhook_secret")
        or file_cfg.get("webhook_secret")
        or ""
    ).strip()
    price_ids = _extract_paddle_price_ids(file_cfg)
    price_to_plan = {pri: plan_k for plan_k, pri in price_ids.items() if pri}
    return {
        "environment": env_mode,
        "api_base": "https://sandbox-api.paddle.com" if env_mode == "sandbox" else "https://api.paddle.com",
        "api_key": api_key,
        "webhook_secret": webhook_secret,
        "price_ids": price_ids,
        "price_to_plan": price_to_plan,
    }


def _fetch_paddle_transaction(tx_id: str, creds: dict[str, Any]) -> dict[str, Any] | None:
    api_key = str(creds.get("api_key") or "").strip()
    clean_tx = str(tx_id or "").strip()
    if not api_key or not clean_tx.startswith("txn_"):
        return None
    req = urllib.request.Request(
        f"{creds['api_base']}/transactions/{urllib.parse.quote(clean_tx)}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "AutoApplyLicenseEngine/1.0 (+https://turboapply.agency)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            data = body.get("data")
            return data if isinstance(data, dict) else None
    except urllib.error.HTTPError as hexc:
        if hexc.code in (400, 404):
            return {"_not_found": True, "_http_code": hexc.code}
        return None
    except Exception:
        return None


def _fetch_paddle_customer_email(customer_id: str, creds: dict[str, Any]) -> str:
    api_key = str(creds.get("api_key") or "").strip()
    clean_cust = str(customer_id or "").strip()
    if not api_key or not clean_cust.startswith("ctm_"):
        return ""
    req = urllib.request.Request(
        f"{creds['api_base']}/customers/{urllib.parse.quote(clean_cust)}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "AutoApplyLicenseEngine/1.0 (+https://turboapply.agency)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            data = body.get("data")
            if isinstance(data, dict):
                return str(data.get("email") or "").strip()
    except Exception:
        pass
    return ""


def _resolve_plan_from_paddle_data(
    data: dict[str, Any],
    price_to_plan: dict[str, str],
    fallback_plan: str = "monthly",
) -> str:
    items = data.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            price_obj = item.get("price") if isinstance(item.get("price"), dict) else {}
            pri_id = str(price_obj.get("id") or item.get("price_id") or "").strip()
            if pri_id and pri_id in price_to_plan:
                return price_to_plan[pri_id]
            pri_cd = price_obj.get("custom_data") if isinstance(price_obj.get("custom_data"), dict) else {}
            cd_plan = str(pri_cd.get("plan") or "").strip().lower()
            if cd_plan in PRICING_PLANS:
                return cd_plan
    custom_data = data.get("custom_data") if isinstance(data.get("custom_data"), dict) else {}
    cd_plan = str(custom_data.get("plan") or custom_data.get("plan_id") or "").strip().lower()
    if cd_plan in PRICING_PLANS:
        return cd_plan
    fb = str(fallback_plan or "monthly").strip().lower()
    return fb if fb in PRICING_PLANS else "monthly"


def load_paddle_runtime_config(storage_dir: Path) -> dict[str, Any]:
    file_cfg = _read_paddle_config_file(storage_dir)

    env_mode = str(
        file_cfg.get("paddle_environment")
        or file_cfg.get("environment")
        or os.getenv("PADDLE_ENVIRONMENT")
        or "production"
    ).strip().lower()
    if env_mode not in ("sandbox", "production"):
        env_mode = "production"

    client_token = str(
        file_cfg.get("paddle_client_token")
        or file_cfg.get("client_token")
        or os.getenv("PADDLE_CLIENT_TOKEN")
        or ""
    ).strip()
    paddle_price_ids = _extract_paddle_price_ids(file_cfg)
    price_id = str(
        paddle_price_ids.get("monthly")
        or file_cfg.get("paddle_price_id")
        or file_cfg.get("price_id")
        or os.getenv("PADDLE_PRICE_ID")
        or ""
    ).strip()
    product_id = str(
        file_cfg.get("paddle_product_id")
        or file_cfg.get("product_id")
        or os.getenv("PADDLE_PRODUCT_ID")
        or ""
    ).strip()
    seller_id = str(
        file_cfg.get("paddle_seller_id")
        or file_cfg.get("seller_id")
        or os.getenv("PADDLE_SELLER_ID")
        or ""
    ).strip()
    payment_link = str(
        file_cfg.get("paddle_payment_link")
        or os.getenv("PADDLE_PAYMENT_LINK")
        or ""
    ).strip()

    crypto_wallets = load_crypto_wallets(storage_dir)
    crypto_rates = get_daily_locked_crypto_rates(storage_dir)

    enriched_plans: list[dict[str, Any]] = []
    for pid, pmeta in PRICING_PLANS.items():
        plan_copy = dict(pmeta)
        plan_copy["paddle_price_id"] = paddle_price_ids.get(pid, "")
        enriched_plans.append(plan_copy)

    gateway_live_ready = bool(
        (
            env_mode == "production"
            and client_token.startswith("live_")
            and (price_id or paddle_price_ids)
            and bool(file_cfg.get("payment_gateway_live", False))
        )
        or os.getenv("AUTOAPPLY_ENFORCE_LICENSING_LIMITS", "").strip().lower() in ("1", "true", "yes")
    )

    return {
        "paddle_environment": env_mode,
        "paddle_client_token": client_token,
        "paddle_price_id": price_id,
        "paddle_price_ids": paddle_price_ids,
        "paddle_product_id": product_id,
        "paddle_seller_id": seller_id,
        "paddle_payment_link": payment_link,
        "paddle_overlay_ready": bool(client_token and (price_id or paddle_price_ids)),
        "payment_gateway_live": gateway_live_ready,
        "licensing_limits_enforced": gateway_live_ready,
        "trial_mode_grace_active": not gateway_live_ready,
        "price_usd_monthly": MONTHLY_PRICE_USD,
        "price_usd_weekly": WEEKLY_PRICE_USD,
        "price_usd_annual": ANNUAL_PRICE_USD,
        "price_usd_lifetime": LIFETIME_PRICE_USD,
        "trial_duration_days": 2,
        "pricing_plans": enriched_plans,
        "crypto_wallets": crypto_wallets,
        "crypto_rates": crypto_rates,
        "currency": "USD",
        "billing_interval": "month",
        "product_name": "AutoApply for macOS — Pro License",
        "checkout_url": "https://turboapply.agency/job-searcher/license/",
        "fallback_checkout_url": "https://turboapply.ru/autoapply-subscribe",
        "webhook_url": "https://turboapply.ru/api/autoapply-license/paddle-webhook",
    }


def _LeaseSigningSecret() -> str:
    return (
        os.getenv("AUTOAPPLY_LEASE_SIGNING_SECRET", "").strip()
        or "autoapply-server-lease-signing-secret-v1"
    )


BRAND_MARK_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAFQAAABUCAYAAAAcaxDBAAAFL0lEQVR4nOydbWwTdRzHv73eHOJjMhdQg3MiTMQYZ6ZRQdw0IpCI"
    "oCLGFwzj2AxRkWhMjBrDzBIj4cV84UNwERKiLrwAEo0zWUCihAc352TC5thYZxZBomGbY1u2dn5/Tbs0Zev68D9zx36f5PL/9+66"
    "3n327f2v1/ZXG5lRkJWVVRIKhRb6fL6bOeWNjY3lsb0aHoDb2sdtDbDt4hSwLOu3kZGRA1zUhjTxIUVs2y7mRrzADShheyMuQbhv"
    "Pdy3A2xrRkdHv0/lvqkInU+ZW/lAKzGNoNR9lPoGu78ns34yQnP9fv8WitzAycY0hFJHOW0PBoPv8ua5ROtOJTSHqdxLkYuhiNiD"
    "TKs8Q/smWyeR0HwOOPVsb4ESiwxcIrVzooUTCmUqF7GRZF4H5SKY1HN0s5xiG+OXTST0Kiazge18KIlootBixD39rbiVfEznbqjM"
    "ZCikq68QF0p/7A0m80VGeROUpKCreTwDOsMXNg3j82KWX0njnVwpF0rSyPGUI/9cdvvl9nhCKbOSMpdCSQk6u4IvWS2mtD58OzJ/"
    "AYU2cWE2lJRhSoeZUhl3usODEmWWqsz0EXd0uFH6VmTGKigZEXUoT/nbOLqfhJIxPC+VQ6et6TSEuLQZ1bugGEFc2hyhZrMDJ5mb"
    "PweNB2sxc+blcCNbqz/HW+99iEwJu+Txs4v9PDhEdvZlOLr/S9xe4M6LVj/93IIly9eD1zphgDZLrMJBtlW97lqZ53v78Uzpa6Zk"
    "hhNqO3n++fiyh1C+fg3cyrqKN9Hz518wBV1e49hbGnlzrseOT6rgVj6uqUVd/SGYRo6hYzAMTx9wpH4X7ryjAG7kRGsH7il5lueN"
    "ozCNIwn9oHKza2VeuDCIp9dtdkSmYFzo0ocfwEvlz8GtbNi0Bac6/4BTGBV6w+xc7Nr+PtzKzi/2Yfee7+Akxo6hvHKNH+p2oqhw"
    "IdxIe0c3iorXYnBwCE5iLKFV77zsWplDQ8Ph46bTMgVHRvlM+Gjb2ygrfWrK9Y42/IoHl5XCbVhQjKJCDaNCDaNCDaNCDaNCDaNC"
    "DaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDaNCDePZGiKnAz1wI54UeuhIEyperYQb"
    "8ZxQkblizcb/5YNf6eApoccaj7tapuAZoSLzsScrXC1T8ITQqMyBgUG4HdcLbWo+6RmZgquFisxHV5V7RqYgX03shQuJyuzr/xde"
    "QVxaPp/vDFxGy4l2z8kUxKUk1FVCm1va8MjKMs/JFMSlfGlBqmOthWKCWknoL1CMIC61iItBpIiLXL5rRQZFnJVxxGFr+Hooo1oH"
    "JSPocK+00eot+bZtt3PY90NJGcoMRgoKBqJX7E9z5mdQ0iLiLiD92PpCs5jSLqZ0BpSkocwhpvMmRKqHx76ndJbTp1BSpRoxpdjj"
    "K2DNYEr3M6X3Q5kSpvMY07mE3eHovIlKiuXwvPQw23lQEtHB88572f4TO3OyGm23MqmHtez6xDCZfzOZIvOiWvaTvS9/incoYtsE"
    "JZ5murkbk/wwQKIPOgQY6UXy4yJQwtDF13RyH7vdk60z1SdHBvnfWB0KhZ6XmGOaIvtOB2WR3wFJ+C5hUq+M5CoK/2CN3+/PYb/Q"
    "53R9TJfAfR3jru4QkewmVdctnR+oWswHeYUPsEJKjuMShPs2wOZbTtWU+WMq980oaUzsE5ZlreYGLJDKhGyvZTsLHoLbfJbb3Mv2"
    "PNvjfCbuCQaD3yBN/gMAAP//gWIncwAAAAZJREFUAwA5L/iHp+mgrgAAAABJRU5ErkJggg=="
)
BRAND_MARK_PNG_BYTES = base64.b64decode(BRAND_MARK_PNG_B64)


def _format_email_expiry_label(expires_at: str, plan_id: str) -> str:
    if str(plan_id or "").strip().lower() == "lifetime":
        return "Lifetime"
    raw = str(expires_at or "").strip()
    if not raw:
        return "Active"
    try:
        exp_dt = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if exp_dt.year >= 2090:
            return "Lifetime"
        return f"{exp_dt.strftime('%B')} {exp_dt.day}, {exp_dt.year}"
    except Exception:
        return raw


def _format_payment_method_label(payment_provider: str) -> str:
    low = str(payment_provider or "").strip().lower()
    if low in ("paddle", "card"):
        return "Paddle"
    if low == "crypto":
        return "Crypto"
    return low.capitalize() if low else "Checkout"


def _format_plan_receipt_summary(plan_id: str) -> tuple[str, str]:
    low = str(plan_id or "monthly").strip().lower()
    if low == "weekly":
        return "Weekly Pass", "$10/week"
    if low == "annual":
        return "Annual Pro", "$200/year"
    if low == "lifetime":
        return "Lifetime Pro", "$200 one-time"
    return "Monthly Pro", "$30/month"


def build_gateway_confirmation_receipt(
    *,
    action: str,
    license_key: str,
    subscription_id: str = "",
    payment_provider: str = "paddle",
    timestamp_iso: str = "",
) -> dict[str, str]:
    """Generate a deterministic gateway confirmation receipt ID and status for pause/cancel/refund events."""
    act = str(action or "cancel").strip().lower()
    prov_low = str(payment_provider or "paddle").strip().lower()
    is_crypto = prov_low == "crypto"
    prefix = "CHAIN" if is_crypto else "PAD"
    act_codes = {
        "pause": "SUSP",
        "cancel": "CXL",
        "cancel_with_free_cycle": "FREE1",
        "refund_request": "RFD",
        "resume": "RES",
    }
    act_code = act_codes.get(act, "CXL")
    ts_day = (timestamp_iso or utc_now_iso())[:10]
    seed = f"{prefix}:{act_code}:{license_key}:{subscription_id}:{ts_day}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest().upper()[:8]
    receipt_id = f"{prefix}-{act_code}-{digest}"
    provider_label = "On-Chain Crypto Billing" if is_crypto else "Paddle Billing Gateway"
    status_map = {
        "pause": "SUSPENDED",
        "cancel": "CANCELLED",
        "cancel_with_free_cycle": "CANCELLED · +1 FREE BILLING PERIOD",
        "refund_request": "CANCELLED · REFUND REQUESTED",
        "resume": "ACTIVE",
    }
    status_code = status_map.get(act, "CANCELLED")
    return {
        "gateway_receipt_id": receipt_id,
        "gateway_provider": provider_label,
        "gateway_status": status_code,
        "gateway_summary": f"{provider_label} · {status_code.title()}",
    }


def _render_editorial_email_html(
    *,
    subject: str,
    preheader_text: str,
    headline: str,
    lead_text: str,
    box_label: str = "",
    box_value: str = "",
    box_subtext: str = "",
    rows: list[tuple[str, str, bool]] | None = None,
    cta_label: str = "",
    cta_url: str = "",
    footer_extra_html: str = "",
    brand_mark_url: str = "https://turboapply.agency/api/autoapply-license/brand-mark.png",
) -> str:
    box_html = ""
    if box_value:
        sub_html = (
            f'<div class="ta-muted" style="font-size:12.5px;line-height:1.45;color:#5d5b55;margin-top:6px;">{html.escape(box_subtext)}</div>'
            if box_subtext
            else ""
        )
        box_html = f"""
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="ta-key-box" style="width:100%;background-color:#f3f3f0;border:1px solid #e5e5e2;border-radius:16px;margin-bottom:22px;">
                <tr>
                  <td style="padding:20px 22px;">
                    <div class="ta-muted" style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#5d5b55;margin-bottom:6px;">
                      {html.escape(box_label or "License key")}
                    </div>
                    <div class="ta-ink ta-key" style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono',monospace;font-size:21px;line-height:1.3;font-weight:600;color:#121212;letter-spacing:0.03em;word-break:break-all;">
                      {html.escape(box_value)}
                    </div>
                    {sub_html}
                  </td>
                </tr>
              </table>"""

    rows_html_parts: list[str] = []
    for r_label, r_val, is_mono in rows or []:
        if not r_val:
            continue
        val_style = (
            "padding:5px 0;color:#5d5b55;font-size:12.5px;line-height:1.45;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;text-align:right;"
            if is_mono
            else "padding:5px 0;color:#121212;font-size:13.5px;line-height:1.45;font-weight:500;text-align:right;"
        )
        val_cls = "ta-muted" if is_mono else "ta-ink"
        rows_html_parts.append(
            f'<tr>'
            f'<td class="ta-muted" style="padding:5px 0;color:#5d5b55;font-size:13.5px;line-height:1.45;">{html.escape(r_label)}</td>'
            f'<td class="{val_cls}" style="{val_style}">{html.escape(r_val)}</td>'
            f'</tr>'
        )
    table_html = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse;margin-bottom:28px;">'
        f'{"".join(rows_html_parts)}'
        f'</table>'
        if rows_html_parts
        else ""
    )

    cta_html = (
        f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:34px;">
                <tr>
                  <td class="ta-btn" style="border-radius:999px;background-color:#121212;">
                    <a href="{html.escape(cta_url)}" class="ta-btn" style="display:inline-block;padding:13px 22px;border-radius:999px;background-color:#121212;color:#f5f1e8;font-size:13.5px;font-weight:600;line-height:1.2;text-decoration:none;letter-spacing:-0.01em;">
                      {html.escape(cta_label)}
                    </a>
                  </td>
                </tr>
              </table>"""
        if (cta_label and cta_url)
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light dark" />
  <meta name="supported-color-schemes" content="light dark" />
  <title>{html.escape(subject)}</title>
  <style>
    @media (prefers-color-scheme: dark) {{
      body, .ta-bg {{ background-color: #050505 !important; color: #f5f1e8 !important; }}
      .ta-ink {{ color: #f5f1e8 !important; }}
      .ta-muted {{ color: #9c968c !important; }}
      .ta-subtle {{ color: #7c7870 !important; }}
      .ta-ghost {{ color: #3a3833 !important; }}
      .ta-key-box {{ background-color: #141413 !important; border-color: #262623 !important; }}
      .ta-rule {{ border-top-color: #242421 !important; }}
      .ta-btn {{ background-color: #f5f1e8 !important; color: #050505 !important; }}
    }}
    @media only screen and (max-width: 520px) {{
      .ta-wrap {{ padding: 28px 20px 32px 20px !important; }}
      .ta-h1 {{ font-size: 26px !important; }}
      .ta-key {{ font-size: 19px !important; }}
    }}
  </style>
</head>
<body class="ta-bg" style="margin:0;padding:0;background-color:#ffffff;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#121212;-webkit-font-smoothing:antialiased;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;">
    {html.escape(preheader_text)}
  </div>
  <table role="presentation" class="ta-bg" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#ffffff;">
    <tr>
      <td align="center" class="ta-wrap" style="padding:44px 24px 40px 24px;">
        <table role="presentation" width="460" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:460px;text-align:left;">
          <tr>
            <td style="padding-bottom:32px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td valign="middle" style="padding-right:10px;">
                    <img src="{html.escape(brand_mark_url)}" width="26" height="26" alt="TurboApply" style="display:block;width:26px;height:26px;border-radius:6px;border:0;" />
                  </td>
                  <td valign="middle" class="ta-ink" style="font-size:13px;font-weight:700;letter-spacing:0.1em;color:#121212;text-transform:uppercase;">
                    TURBOAPPLY
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td>
              <h1 class="ta-ink ta-h1" style="margin:0 0 10px 0;font-size:30px;line-height:1.15;font-weight:600;letter-spacing:-0.03em;color:#121212;">
                {html.escape(headline)}
              </h1>
              <p class="ta-muted" style="margin:0 0 24px 0;font-size:15px;line-height:1.55;color:#5d5b55;">
                {html.escape(lead_text)}
              </p>
              {box_html}
              {table_html}
              {cta_html}
              <div class="ta-rule ta-subtle" style="border-top:1px solid #e5e5e2;padding-top:18px;font-size:12.5px;line-height:1.5;color:#76736c;">
                Need help? Reply to this email &middot; <a href="https://turboapply.agency" class="ta-subtle" style="color:#76736c;text-decoration:underline;">turboapply.agency</a>{footer_extra_html}
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _deliver_smtp_email(
    *,
    to_addr: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> tuple[bool, str, str]:
    smtp_host = os.getenv("TURBOAPPLY_SMTP_HOST", "smtp.zohocloud.ca").strip()
    smtp_port = int(os.getenv("TURBOAPPLY_SMTP_PORT", "587").strip() or "587")
    smtp_user = os.getenv("TURBOAPPLY_SMTP_USER", "info@turboapply.agency").strip()
    smtp_pass = os.getenv("TURBOAPPLY_SMTP_PASSWORD", "").strip()
    from_email = os.getenv("TURBOAPPLY_SMTP_FROM_EMAIL", smtp_user or "info@turboapply.agency").strip()
    from_name = os.getenv("TURBOAPPLY_SMTP_FROM_NAME", "TurboApply").strip()

    if not smtp_pass:
        return False, from_email, "smtp_password_not_configured"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_addr
    msg["Reply-To"] = from_email
    msg["Message-ID"] = make_msgid(domain="turboapply.agency")
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    try:
        ctx = ssl.create_default_context()
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20, context=ctx) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                server.starttls(context=ctx)
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        return True, from_email, ""
    except Exception as exc:
        return False, from_email, str(exc)


def send_lifecycle_email(
    *,
    template_type: str,
    recipient_email: str,
    license_key: str = "",
    plan_id: str = "monthly",
    payment_provider: str = "paddle",
    transaction_id: str = "",
    expires_at: str = "",
    pause_months: int = 1,
    pause_until_label: str = "",
    gateway_receipt_id: str = "",
    gateway_provider: str = "",
    gateway_status: str = "",
    free_cycle_added: bool = False,
    reference_id: str = "",
    force_send: bool = False,
    conn: sqlite3.Connection | None = None,
    db_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    """Send any of the 7 minimal editorial lifecycle emails from info@turboapply.agency:
    - purchase_thank_you
    - trial_expiring
    - trial_expired
    - subscription_paused
    - subscription_cancelled
    - subscription_renewing_soon
    - subscription_renewed
    """
    to_addr = str(recipient_email or "").strip()
    if not to_addr or "@" not in to_addr:
        return {"ok": False, "error": "invalid_recipient_email"}

    tpl = str(template_type or "purchase_thank_you").strip().lower()
    dedup_ref = str(reference_id or gateway_receipt_id or transaction_id or expires_at or license_key or tpl).strip()

    if not force_send and conn is not None and db_lock is not None:
        try:
            with db_lock, conn:
                already = conn.execute(
                    """
                    SELECT 1 FROM lifecycle_email_log
                    WHERE template_type = ?
                      AND LOWER(recipient_email) = LOWER(?)
                      AND reference_id = ?
                      AND status = 'sent'
                    LIMIT 1
                    """,
                    (tpl, to_addr, dedup_ref),
                ).fetchone()
            if already is not None:
                return {
                    "ok": True,
                    "already_sent": True,
                    "template_type": tpl,
                    "recipient_email": to_addr,
                    "sender_email": os.getenv("TURBOAPPLY_SMTP_FROM_EMAIL", "info@turboapply.agency").strip(),
                }
        except Exception:
            pass

    brand_mark_url = os.getenv(
        "TURBOAPPLY_EMAIL_BRAND_MARK_URL",
        "https://turboapply.agency/api/autoapply-license/brand-mark.png",
    ).strip()

    plan_title, plan_billing_label = _format_plan_receipt_summary(plan_id)
    valid_through_label = _format_email_expiry_label(expires_at, plan_id)
    is_lifetime = str(plan_id or "").strip().lower() == "lifetime" or valid_through_label == "Lifetime"
    expiry_row_label = "Access" if is_lifetime else "Valid until"

    clean_tx = str(transaction_id or "").strip()
    display_tx = f"{clean_tx[:14]}…{clean_tx[-8:]}" if len(clean_tx) > 34 else clean_tx

    q_email = urllib.parse.quote(to_addr)
    q_key = urllib.parse.quote(str(license_key or ""))
    q_plan = urllib.parse.quote(str(plan_id or "monthly"))
    upgrade_url = f"https://turboapply.agency/job-searcher/license/?mode=upgrade&email={q_email}&plan={q_plan}"
    plans_url = f"https://turboapply.agency/job-searcher/license/?email={q_email}"
    cancel_url = f"https://turboapply.agency/job-searcher/license/cancel/?action=cancel&email={q_email}&key={q_key}&plan={q_plan}"
    manage_pause_url = f"https://turboapply.agency/job-searcher/license/cancel/?action=pause&email={q_email}&key={q_key}&plan={q_plan}"
    revert_url = f"https://turboapply.agency/job-searcher/license/cancel/?action=refund&email={q_email}&key={q_key}&plan={q_plan}"

    footer_extra_html = ""
    box_label = ""
    box_value = ""
    box_subtext = ""
    rows: list[tuple[str, str, bool]] = []
    cta_label = "Open AutoApply"
    cta_url = "https://turboapply.agency/job-searcher/"

    if tpl == "trial_expiring":
        subject = "Your AutoApply trial ends soon"
        headline = "Your 2-day trial ends soon."
        lead_text = "Upgrade to AutoApply Pro to keep unlimited tailored resumes, cover letters, and automated applications running on your Mac."
        preheader_text = "Upgrade to AutoApply Pro to keep your Mac unlocked."
        rows = [
            ("Status", "Free Trial · Expiring soon", False),
            ("Pro plans", "$10/week · $30/month · $200 Lifetime", False),
        ]
        cta_label = "Upgrade to AutoApply Pro"
        cta_url = upgrade_url
    elif tpl == "trial_expired":
        subject = "Your AutoApply trial has ended"
        headline = "Your free trial has ended."
        lead_text = "Your tailored resumes and Knowledge Base are safely saved on your Mac. Activate a Pro plan anytime to resume automated applications."
        preheader_text = "Activate an AutoApply Pro plan to resume applications on your Mac."
        rows = [
            ("Status", "Trial Ended", False),
            ("Pro plans", "$10/week · $30/month · $200 Lifetime", False),
        ]
        cta_label = "Upgrade to AutoApply Pro"
        cta_url = upgrade_url
    elif tpl == "subscription_paused":
        receipt = build_gateway_confirmation_receipt(
            action="pause",
            license_key=license_key or "AA-PRO",
            payment_provider=payment_provider,
        )
        r_id = gateway_receipt_id or receipt["gateway_receipt_id"]
        r_prov = gateway_provider or receipt["gateway_provider"]
        m_label = f"{pause_months} {'month' if pause_months == 1 else 'months'}"
        subject = "Subscription paused — confirmation receipt"
        headline = "Your subscription is paused."
        lead_text = "Billing is suspended and no charges will occur while paused. Your Mac keeps Pro access until your current billing period ends."
        preheader_text = f"Gateway receipt {r_id} · Paused for {m_label}"
        box_label = "Gateway confirmation receipt"
        box_value = r_id
        box_subtext = f"{r_prov} · Status: Suspended ({m_label})"
        rows = [
            ("Plan", f"{plan_title} · {plan_billing_label}", False),
            ("Billing resumes", pause_until_label or f"In {m_label}", False),
            ("Pro access until", valid_through_label, False),
        ]
        if license_key:
            rows.append(("License key", license_key, True))
        cta_label = "Resume or Manage Plan"
        cta_url = manage_pause_url
    elif tpl == "subscription_cancelled":
        receipt = build_gateway_confirmation_receipt(
            action="cancel_with_free_cycle" if free_cycle_added else "cancel",
            license_key=license_key or "AA-PRO",
            payment_provider=payment_provider,
        )
        r_id = gateway_receipt_id or receipt["gateway_receipt_id"]
        r_prov = gateway_provider or receipt["gateway_provider"]
        r_stat = gateway_status or receipt["gateway_status"]
        subject = "Subscription cancelled — confirmation receipt"
        headline = "Sorry to see you go."
        if free_cycle_added:
            lead_text = (
                f"Your recurring subscription is cancelled and will not renew. "
                f"We have added 1 complimentary billing period on us — your license key remains valid through {valid_through_label}."
            )
        else:
            lead_text = (
                "Your subscription is cancelled and will not renew. "
                "Your Mac keeps full Pro access through the end of your current billing period."
            )
        preheader_text = f"Gateway receipt {r_id} · {r_prov} ({r_stat})"
        box_label = "Gateway confirmation receipt"
        box_value = r_id
        box_subtext = f"{r_prov} · Status: {r_stat.title()}"
        rows = [
            ("Plan", f"{plan_title} · {plan_billing_label}", False),
            ("Gateway status", "Cancelled · No future charges", False),
            ("License valid until", valid_through_label, False),
        ]
        if license_key:
            rows.append(("License key", license_key, True))
        cta_label = "Offer: Explore New Plans"
        cta_url = plans_url
    elif tpl == "subscription_renewing_soon":
        subject = "Heads up: your AutoApply subscription renews in 2 days"
        headline = "Renewing in 2 days."
        lead_text = "Your AutoApply Pro subscription will automatically renew in 2 days. No action is needed to keep your Mac active."
        preheader_text = f"{plan_title} ({plan_billing_label}) renews on {valid_through_label}."
        rows = [
            ("Plan", f"{plan_title} · {plan_billing_label}", False),
            ("Renewal date", valid_through_label, False),
        ]
        if license_key:
            rows.append(("License key", license_key, True))
        cta_label = "Open AutoApply Pro"
        cta_url = "https://turboapply.agency/job-searcher/"
        footer_extra_html = (
            f' &middot; <a href="{html.escape(cancel_url)}" class="ta-ghost" style="color:#b8b5ad;font-size:11px;text-decoration:none;opacity:0.55;">Unsubscribe</a>'
            f' &middot; <a href="{html.escape(cancel_url)}" class="ta-ghost" style="color:#b8b5ad;font-size:11px;text-decoration:none;opacity:0.52;">Cancel subscription</a>'
        )
    elif tpl == "subscription_renewed":
        subject = "Thank you for your support — subscription renewed"
        headline = "Thank you for your support."
        lead_text = "Your AutoApply Pro subscription has been renewed. Your Mac seat remains active with no interruption."
        preheader_text = f"{plan_title} renewed · Valid until {valid_through_label}"
        box_label = "License key"
        box_value = license_key
        rows = [
            ("Plan", f"{plan_title} · {plan_billing_label}", False),
            ("Valid until", valid_through_label, False),
        ]
        if display_tx:
            rows.append(("Reference", display_tx, True))
        cta_label = "Open AutoApply Pro"
        cta_url = "https://turboapply.agency/job-searcher/"
        footer_extra_html = (
            f'<div class="ta-ghost" style="margin-top:10px;font-size:10.5px;line-height:1.45;color:#c5c2ba;opacity:0.5;">'
            f'If you wish to cancel the subscription, please '
            f'<a href="{html.escape(revert_url)}" class="ta-ghost" style="color:#c5c2ba;text-decoration:underline;">let us know within 2 days of this email and we will revert it</a>.'
            f'</div>'
        )
    else:
        # purchase_thank_you
        subject = "Thank you — your AutoApply license key"
        headline = "Thank you. Your AutoApply license."
        lead_text = "Paste this key into AutoApply → Activate License on your Mac."
        preheader_text = f"{license_key} · {plan_title} ({plan_billing_label})"
        box_label = "License key"
        box_value = license_key
        rows = [
            ("Plan", f"{plan_title} · {plan_billing_label}", False),
            (expiry_row_label, valid_through_label, False),
        ]
        if display_tx:
            rows.append(("Reference", display_tx, True))
        cta_label = "Download AutoApply"
        cta_url = "https://turboapply.agency/job-searcher/"

    text_lines = [
        "TURBOAPPLY",
        "",
        headline,
        lead_text,
        "",
    ]
    if box_value:
        text_lines.append(f"{box_label or 'License key'}: {box_value}")
        if box_subtext:
            text_lines.append(box_subtext)
        text_lines.append("")
    for r_label, r_val, _ in rows:
        if r_val:
            text_lines.append(f"{r_label}: {r_val}")
    text_lines.extend(
        [
            "",
            f"{cta_label}: {cta_url}",
            "Need help? Reply to this email · https://turboapply.agency",
        ]
    )
    if tpl == "subscription_renewing_soon":
        text_lines.append(f"Unsubscribe / Cancel subscription: {cancel_url}")
    elif tpl == "subscription_renewed":
        text_lines.append(
            f"If you wish to cancel the subscription, please let us know within 2 days of this email and we will revert it: {revert_url}"
        )
    text_body = "\n".join(text_lines) + "\n"

    html_body = _render_editorial_email_html(
        subject=subject,
        preheader_text=preheader_text,
        headline=headline,
        lead_text=lead_text,
        box_label=box_label,
        box_value=box_value,
        box_subtext=box_subtext,
        rows=rows,
        cta_label=cta_label,
        cta_url=cta_url,
        footer_extra_html=footer_extra_html,
        brand_mark_url=brand_mark_url,
    )

    sent_ok, from_email, err_str = _deliver_smtp_email(
        to_addr=to_addr,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )

    if conn is not None and db_lock is not None:
        try:
            with db_lock, conn:
                conn.execute(
                    """
                    INSERT INTO lifecycle_email_log (
                        recipient_email, sender_email, template_type, license_key,
                        reference_id, status, error_message, sent_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        to_addr,
                        from_email,
                        tpl,
                        license_key,
                        dedup_ref,
                        "sent" if sent_ok else "error",
                        err_str[:500],
                        utc_now_iso(),
                    ),
                )
                conn.commit()
        except Exception:
            pass

    return {
        "ok": sent_ok,
        "template_type": tpl,
        "recipient_email": to_addr,
        "sender_email": from_email,
        "subject": subject,
        "error": err_str,
    }


def send_license_email(
    *,
    recipient_email: str,
    license_key: str,
    plan_id: str = "monthly",
    payment_provider: str = "crypto",
    transaction_id: str = "",
    support_code: str = "",
    expires_at: str = "",
    is_resend: bool = False,
    conn: sqlite3.Connection | None = None,
    db_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    """Send or resend the user's AutoApply license key from info@turboapply.agency via Zoho SMTP."""
    _ = (support_code, payment_provider)  # Kept clean and minimal in customer-facing emails
    to_addr = str(recipient_email or "").strip()
    if not to_addr or "@" not in to_addr:
        return {"ok": False, "error": "invalid_recipient_email"}

    from_email = os.getenv(
        "TURBOAPPLY_SMTP_FROM_EMAIL",
        os.getenv("TURBOAPPLY_SMTP_USER", "info@turboapply.agency").strip() or "info@turboapply.agency",
    ).strip()

    # Deduplicate automatic welcome emails when both checkout-complete and Paddle webhooks fire
    if not is_resend and conn is not None and db_lock is not None:
        try:
            with db_lock, conn:
                already = conn.execute(
                    """
                    SELECT 1 FROM license_email_log
                    WHERE license_key = ?
                      AND LOWER(recipient_email) = LOWER(?)
                      AND status = 'sent'
                    LIMIT 1
                    """,
                    (license_key, to_addr),
                ).fetchone()
            if already is not None:
                return {
                    "ok": True,
                    "already_sent": True,
                    "recipient_email": to_addr,
                    "sender_email": from_email,
                    "is_resend": False,
                    "error": "",
                }
        except Exception:
            pass

    res = send_lifecycle_email(
        template_type="purchase_thank_you",
        recipient_email=to_addr,
        license_key=license_key,
        plan_id=plan_id,
        payment_provider=payment_provider,
        transaction_id=transaction_id,
        expires_at=expires_at,
        force_send=True,
        conn=conn,
        db_lock=db_lock,
    )
    sent_ok = bool(res.get("ok"))
    err_str = str(res.get("error") or "")

    if conn is not None and db_lock is not None:
        try:
            with db_lock, conn:
                conn.execute(
                    """
                    INSERT INTO license_email_log (
                        recipient_email, sender_email, license_key, transaction_id,
                        is_resend, status, error_message, sent_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        to_addr,
                        from_email,
                        license_key,
                        transaction_id,
                        1 if is_resend else 0,
                        "sent" if sent_ok else "error",
                        err_str[:500],
                        utc_now_iso(),
                    ),
                )
                conn.commit()
        except Exception:
            pass

    return {
        "ok": sent_ok,
        "recipient_email": to_addr,
        "sender_email": from_email,
        "is_resend": is_resend,
        "error": err_str,
    }


def notify_subscription_telegram(
    send_telegram_fn: Callable[[str], None],
    *,
    title: str,
    license_key: str,
    customer_email: str,
    support_code: str = "",
    device_id: str,
    payment_provider: str,
    plan_id: str = "monthly",
    subscription_id: str = "",
    transaction_id: str = "",
    expires_at: str = "",
    gateway_receipt_id: str = "",
    gateway_status: str = "",
) -> None:
    _ = support_code
    plan_title, plan_billing = _format_plan_receipt_summary(plan_id)
    lines = [
        f"💳 {title}",
        f"Plan: {plan_title} ({plan_billing})",
        f"Provider: {payment_provider.upper()}",
        f"License Key: {license_key}",
    ]
    if gateway_receipt_id:
        lines.append(f"Gateway Receipt: {gateway_receipt_id}")
    if gateway_status:
        lines.append(f"Gateway Status: {gateway_status}")
    if customer_email:
        lines.append(f"Customer Email: {customer_email}")
    if device_id:
        lines.append(f"Device ID: {device_id}")
    if subscription_id:
        lines.append(f"Subscription ID: {subscription_id}")
    if transaction_id:
        lines.append(f"Transaction ID: {transaction_id}")
    if expires_at:
        lines.append(f"Paid Through: {_format_email_expiry_label(expires_at, plan_id)}")
    lines.append(f"Time: {utc_now_iso()}")
    msg_text = "\n".join(lines)
    if os.getenv("PYTEST_CURRENT_TEST"):
        try:
            send_telegram_fn(msg_text)
        except Exception:
            pass
    else:
        def _bg_tg() -> None:
            try:
                send_telegram_fn(msg_text)
            except Exception:
                pass

        threading.Thread(target=_bg_tg, daemon=True).start()


def create_checkout_session(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    device_id: str,
    support_code: str = "",
    customer_email: str,
) -> dict[str, Any]:
    session_id = f"chk_{uuid.uuid4().hex[:16]}"
    now_iso = utc_now_iso()
    with db_lock, conn:
        conn.execute(
            """
            INSERT INTO checkout_sessions (
                session_id, device_id, support_code, customer_email, status, created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (session_id, device_id[:120], support_code[:64], customer_email[:180], now_iso),
        )
        conn.commit()
    params = urllib.parse.urlencode(
        {
            k: v
            for k, v in {
                "session_id": session_id,
                "device_id": device_id,
                "email": customer_email,
            }.items()
            if v
        }
    )
    return {
        "ok": True,
        "session_id": session_id,
        "device_id": device_id,
        "email": customer_email,
        "checkout_url": f"https://turboapply.agency/job-searcher/license/?{params}",
        "fallback_checkout_url": f"https://turboapply.ru/autoapply-subscribe?{params}",
    }


def upsert_and_bind_license(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    license_key: str,
    status: str = "active",
    customer_email: str = "",
    customer_id: str = "",
    subscription_id: str = "",
    transaction_id: str = "",
    payment_provider: str = "paddle",
    device_id: str = "",
    support_code: str = "",
    session_id: str = "",
    period_days: int = DEFAULT_PERIOD_DAYS,
    price_usd: int = MONTHLY_PRICE_USD,
    expires_at_override: str = "",
    manage_url: str = "",
    plan_id: str = "",
) -> dict[str, Any]:
    now_dt = utc_now()
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_iso = expires_at_override or (now_dt + dt.timedelta(days=max(1, period_days))).strftime("%Y-%m-%dT%H:%M:%SZ")

    with db_lock, conn:
        for col_sql in (
            "ALTER TABLE license_keys ADD COLUMN plan_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN pause_until TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN cancellation_reason TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN cancelled_at TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass

        existing = conn.execute(
            "SELECT * FROM license_keys WHERE license_key = ?",
            (license_key,),
        ).fetchone()
        existing_keys = set(existing.keys()) if existing is not None else set()
        existing_plan = str(existing["plan_id"] or "") if "plan_id" in existing_keys else ""
        if existing:
            cur_dev = str(existing["active_device_id"] or "")
            cur_sup = str(existing["support_code"] or "")
            cur_email = str(existing["customer_email"] or "")
            cur_sub = str(existing["subscription_id"] or "")
            cur_tx = str(existing["transaction_id"] or "")
            cur_cust = str(existing["customer_id"] or "")
            cur_manage = str(existing["manage_url"] or "")
            issued_iso = str(existing["issued_at"] or now_iso)
            resolved_plan = infer_plan_id_from_license(
                license_key=license_key,
                plan_id=plan_id or existing_plan,
                price_usd=price_usd,
                issued_at=issued_iso,
                expires_at=expires_iso,
                period_days=period_days,
            )
            conn.execute(
                """
                UPDATE license_keys
                SET status = ?,
                    price_usd_monthly = ?,
                    customer_email = ?,
                    customer_id = ?,
                    subscription_id = ?,
                    transaction_id = ?,
                    payment_provider = ?,
                    active_device_id = ?,
                    support_code = ?,
                    expires_at = ?,
                    updated_at = ?,
                    manage_url = ?,
                    plan_id = ?
                WHERE license_key = ?
                """,
                (
                    status,
                    price_usd,
                    customer_email or cur_email,
                    customer_id or cur_cust,
                    subscription_id or cur_sub,
                    transaction_id or cur_tx,
                    payment_provider or str(existing["payment_provider"] or "paddle"),
                    device_id or cur_dev,
                    support_code or cur_sup,
                    expires_iso,
                    now_iso,
                    manage_url or cur_manage,
                    resolved_plan,
                    license_key,
                ),
            )
        else:
            issued_iso = now_iso
            resolved_plan = infer_plan_id_from_license(
                license_key=license_key,
                plan_id=plan_id,
                price_usd=price_usd,
                issued_at=issued_iso,
                expires_at=expires_iso,
                period_days=period_days,
            )
            conn.execute(
                """
                INSERT INTO license_keys (
                    license_key, status, price_usd_monthly, customer_email, customer_id,
                    subscription_id, transaction_id, payment_provider, active_device_id,
                    support_code, issued_at, expires_at, updated_at, manage_url, plan_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    license_key,
                    status,
                    price_usd,
                    customer_email,
                    customer_id,
                    subscription_id,
                    transaction_id,
                    payment_provider,
                    device_id,
                    support_code,
                    issued_iso,
                    expires_iso,
                    now_iso,
                    manage_url,
                    resolved_plan,
                ),
            )

        if session_id:
            conn.execute(
                """
                UPDATE checkout_sessions
                SET status = 'completed',
                    license_key = ?,
                    subscription_id = COALESCE(NULLIF(?, ''), subscription_id),
                    transaction_id = COALESCE(NULLIF(?, ''), transaction_id),
                    customer_email = COALESCE(NULLIF(?, ''), customer_email),
                    payment_provider = ?,
                    completed_at = ?
                WHERE session_id = ?
                """,
                (license_key, subscription_id, transaction_id, customer_email, payment_provider, now_iso, session_id),
            )
        elif support_code or device_id:
            conn.execute(
                """
                UPDATE checkout_sessions
                SET status = 'completed',
                    license_key = ?,
                    subscription_id = COALESCE(NULLIF(?, ''), subscription_id),
                    transaction_id = COALESCE(NULLIF(?, ''), transaction_id),
                    customer_email = COALESCE(NULLIF(?, ''), customer_email),
                    payment_provider = ?,
                    completed_at = ?
                WHERE status = 'pending' AND (
                    (support_code != '' AND support_code = ?)
                    OR (device_id != '' AND device_id = ?)
                )
                """,
                (
                    license_key,
                    subscription_id,
                    transaction_id,
                    customer_email,
                    payment_provider,
                    now_iso,
                    support_code,
                    device_id,
                ),
            )
        conn.commit()

    lease = build_signed_lease(
        device_id=device_id or "mac_local_device",
        support_code=support_code,
        license_key=license_key,
        issued_at=issued_iso,
        expires_at=expires_iso,
        signing_secret=_LeaseSigningSecret(),
    )
    plan_fields = build_plan_summary_fields(resolved_plan)
    return {
        "ok": True,
        "license_key": license_key,
        "status": status,
        "price_usd_monthly": price_usd,
        "payment_provider": payment_provider,
        "customer_email": customer_email,
        "subscription_id": subscription_id,
        "transaction_id": transaction_id,
        "device_id": device_id or "mac_local_device",
        "support_code": support_code,
        "issued_at": issued_iso,
        "expires_at": expires_iso,
        "manage_url": manage_url,
        **plan_fields,
        "lease": lease,
    }


def find_existing_subscription_for_customer(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    email: str = "",
    license_key: str = "",
    device_id: str = "",
) -> dict[str, Any] | None:
    email_clean = str(email or "").strip()
    key_clean = str(license_key or "").strip().upper()
    dev_clean = str(device_id or "").strip()
    row = None
    with db_lock, conn:
        for col_sql in (
            "ALTER TABLE license_keys ADD COLUMN plan_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN pause_until TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN cancellation_reason TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN cancelled_at TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN gateway_receipt_id TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass
        if key_clean and "•" not in key_clean and "*" not in key_clean:
            norm_k = normalize_incoming_license_key(key_clean, conn)
            row = conn.execute(
                "SELECT * FROM license_keys WHERE license_key = ? LIMIT 1",
                (norm_k,),
            ).fetchone()
        elif key_clean and ("•" in key_clean or "*" in key_clean):
            cleaned_parts = [p for p in re.split(r"[•*]+", key_clean) if p]
            if len(cleaned_parts) >= 2:
                prefix, suffix = cleaned_parts[0], cleaned_parts[-1]
                row = conn.execute(
                    "SELECT * FROM license_keys WHERE license_key LIKE ? ORDER BY updated_at DESC LIMIT 1",
                    (f"{prefix}%{suffix}",),
                ).fetchone()
        if row is None and email_clean:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE LOWER(customer_email) = LOWER(?) ORDER BY updated_at DESC LIMIT 1",
                (email_clean,),
            ).fetchone()
        if row is None and dev_clean and dev_clean != "mac_local_device":
            row = conn.execute(
                "SELECT * FROM license_keys WHERE active_device_id = ? ORDER BY updated_at DESC LIMIT 1",
                (dev_clean,),
            ).fetchone()
    if row is None:
        return None
    row_keys = set(row.keys())
    lic_key = str(row["license_key"] or "")
    status = str(row["status"] or "")
    cancelled_at = str(row["cancelled_at"] or "") if "cancelled_at" in row_keys else ""
    pause_until = str(row["pause_until"] or "") if "pause_until" in row_keys else ""
    stored_plan = str(row["plan_id"] or "") if "plan_id" in row_keys else ""
    price_usd = int(row["price_usd_monthly"] or MONTHLY_PRICE_USD)
    issued_at = str(row["issued_at"] or "")
    expires_at = str(row["expires_at"] or "")
    resolved_plan = infer_plan_id_from_license(
        license_key=lic_key,
        plan_id=stored_plan,
        price_usd=price_usd,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    raw_prov = str(row["payment_provider"] or "paddle").strip().lower()
    prov = "crypto" if raw_prov == "crypto" else "paddle"
    is_cancelled = bool(cancelled_at) or status in ("expired_cancelled", "revoked_refund", "cancelled")
    is_active_recurring = (status == "active") and (not is_cancelled) and (resolved_plan != "lifetime")
    return {
        "license_key": lic_key,
        "status": status,
        "payment_provider": prov,
        "plan": resolved_plan,
        "cancelled_at": cancelled_at,
        "pause_until": pause_until,
        "expires_at": expires_at,
        "is_cancelled": is_cancelled,
        "is_active_recurring": is_active_recurring,
        "payment_method_locked": is_active_recurring,
        "locked_payment_method": prov if is_active_recurring else "",
    }


def process_checkout_claim(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    customer_email: str,
    transaction_id: str,
    subscription_id: str = "",
    payment_provider: str = "crypto",
    plan_id: str = "monthly",
    device_id: str = "mac_local_device",
    support_code: str = "",
    session_id: str = "",
    explicit_key: str = "",
    mode: str = "",
    storage_dir: Path | None = None,
    send_telegram_fn: Callable[[str], None] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Process a checkout or crypto TXID claim with strict TXID deduplication, upgrade payment-method lock,
    and email delivery:
    - If upgrading an active (uncancelled) subscription, the user cannot switch payment methods
      (Card/Paddle <-> Crypto) unless they cancel their existing subscription first.
    - If `transaction_id` was already claimed under a DIFFERENT email: reject (409) and state that
      the transaction ID has already been claimed and a license key has already been sent.
    - If `transaction_id` was already claimed under the SAME email: resend the license key to that
      email from info@turboapply.agency and state that we will resend the license key to your email.
    - If `transaction_id` is new: issue the license key, bind it, and send the license key email.
    """
    email_clean = str(customer_email or "").strip()
    tx_clean = str(transaction_id or "").strip()
    sub_clean = str(subscription_id or "").strip()
    raw_prov = str(payment_provider or "crypto").strip().lower()
    provider_clean = "paddle" if raw_prov in ("paddle", "card") else "crypto"
    plan_key = str(plan_id or "monthly").strip().lower()
    if plan_key not in PRICING_PLANS:
        plan_key = "monthly"
    mode_clean = str(mode or "").strip().lower()

    if not email_clean or "@" not in email_clean:
        return 400, {
            "ok": False,
            "error": "email_required",
            "message": "Please enter a valid email address so we can send your license key.",
        }

    # Enforce payment-method lock on upgrades when the customer has an active, uncancelled recurring subscription
    plan_rank = {"weekly": 1, "monthly": 2, "annual": 3, "lifetime": 4}
    existing_sub = find_existing_subscription_for_customer(
        conn,
        db_lock,
        email=email_clean,
        license_key=explicit_key,
        device_id=device_id if mode_clean == "upgrade" else "",
    )
    if existing_sub is not None and existing_sub.get("is_active_recurring"):
        existing_prov = str(existing_sub.get("payment_provider") or "paddle")
        existing_plan = str(existing_sub.get("plan") or "monthly")
        is_tier_upgrade = plan_rank.get(plan_key, 2) > plan_rank.get(existing_plan, 2)
        if (mode_clean == "upgrade" or is_tier_upgrade) and existing_prov != provider_clean:
            existing_label = "Card (Paddle)" if existing_prov == "paddle" else "Crypto"
            target_label = "Crypto" if provider_clean == "crypto" else "Card (Paddle)"
            existing_plan_name = PRICING_PLANS.get(existing_plan, PRICING_PLANS["monthly"])["name"]
            return 409, {
                "ok": False,
                "error": "payment_method_locked_until_cancelled",
                "locked_payment_method": existing_prov,
                "existing_plan": existing_plan,
                "message": (
                    f"Your active {existing_plan_name} subscription is billed via {existing_label}. "
                    f"You cannot change your payment method to {target_label} during an upgrade unless you cancel your current subscription first, and then upgrade after."
                ),
            }

    if provider_clean == "crypto" and len(tx_clean) < 6:
        return 400, {
            "ok": False,
            "error": "transaction_id_required",
            "message": "Please paste a valid on-chain Transaction Hash (TXID) to verify your transfer.",
        }

    if provider_clean == "paddle":
        if not tx_clean or tx_clean.upper() == "PADDLE":
            return 400, {
                "ok": False,
                "error": "paddle_transaction_required",
                "message": "Please complete payment in the Paddle checkout window before claiming your license key.",
            }
        creds = _load_paddle_server_credentials(storage_dir)
        if creds.get("api_key") and tx_clean.startswith("txn_"):
            tx_data = _fetch_paddle_transaction(tx_clean, creds)
            if isinstance(tx_data, dict):
                if tx_data.get("_not_found"):
                    return 400, {
                        "ok": False,
                        "error": "invalid_paddle_transaction",
                        "message": "We could not verify that Paddle transaction ID. Please contact info@turboapply.agency if you were charged.",
                    }
                tx_status = str(tx_data.get("status") or "").strip().lower()
                if tx_status in ("canceled", "cancelled", "draft"):
                    return 402, {
                        "ok": False,
                        "error": "paddle_transaction_incomplete",
                        "message": f"Paddle transaction is not completed (status: {tx_status}).",
                    }
                plan_key = _resolve_plan_from_paddle_data(tx_data, creds["price_to_plan"], plan_key)
                if not sub_clean and tx_data.get("subscription_id"):
                    sub_clean = str(tx_data.get("subscription_id") or "").strip()

    plan_meta = PRICING_PLANS[plan_key]
    period_days = int(plan_meta["period_days"])
    price_usd = int(plan_meta["price_usd"])

    # Check if this transaction_id has already been claimed
    existing_tx_row = None
    if tx_clean:
        with db_lock, conn:
            existing_tx_row = conn.execute(
                """
                SELECT * FROM license_keys
                WHERE transaction_id != '' AND LOWER(transaction_id) = LOWER(?)
                ORDER BY issued_at ASC
                LIMIT 1
                """,
                (tx_clean,),
            ).fetchone()

    if existing_tx_row is not None:
        registered_email = str(existing_tx_row["customer_email"] or "").strip()
        existing_key = str(existing_tx_row["license_key"])
        existing_expires = str(existing_tx_row["expires_at"])
        existing_issued = str(existing_tx_row["issued_at"])
        existing_sup = str(existing_tx_row["support_code"] or "")
        existing_dev = str(existing_tx_row["active_device_id"] or "")

        if registered_email and registered_email.lower() != email_clean.lower():
            return 409, {
                "ok": False,
                "error": "txid_already_claimed",
                "already_claimed": True,
                "same_email": False,
                "email_sent": False,
                "transaction_id": tx_clean,
                "message": (
                    "This Transaction ID has already been claimed under a different email address, "
                    "and a license key has already been sent to the registered owner."
                ),
            }

        # Same email (or previously unclaimed email slot on that TXID, e.g. webhook arrived milliseconds earlier)
        already_emailed_once = False
        with db_lock, conn:
            already_emailed_once = (
                conn.execute(
                    """
                    SELECT 1 FROM license_email_log
                    WHERE license_key = ? AND LOWER(recipient_email) = LOWER(?) AND status = 'sent'
                    LIMIT 1
                    """,
                    (existing_key, email_clean),
                ).fetchone()
                is not None
            )

        res = upsert_and_bind_license(
            conn,
            db_lock,
            license_key=existing_key,
            status=str(existing_tx_row["status"] or "active"),
            customer_email=email_clean,
            subscription_id=sub_clean or str(existing_tx_row["subscription_id"] or ""),
            transaction_id=tx_clean,
            payment_provider=str(existing_tx_row["payment_provider"] or provider_clean),
            device_id=device_id if not existing_dev or existing_dev == "mac_local_device" else existing_dev,
            support_code=support_code or existing_sup,
            session_id=session_id,
            period_days=period_days,
            price_usd=int(existing_tx_row["price_usd_monthly"] or price_usd),
            expires_at_override=existing_expires,
            plan_id=plan_key,
        )
        # For crypto duplicate submissions by same user, resend explicitly; for Paddle race with webhook, send only if not yet emailed
        should_force_resend = (provider_clean != "paddle") or (not already_emailed_once)
        email_result = send_license_email(
            recipient_email=email_clean,
            license_key=existing_key,
            plan_id=plan_key,
            payment_provider=provider_clean,
            transaction_id=tx_clean,
            support_code=support_code or existing_sup,
            expires_at=existing_expires,
            is_resend=bool(already_emailed_once and provider_clean != "paddle"),
            conn=conn,
            db_lock=db_lock,
        ) if should_force_resend else {"ok": True, "already_sent": True, "sender_email": "info@turboapply.agency"}

        is_crypto_resend = bool(already_emailed_once and provider_clean != "paddle")
        res.update(
            {
                "already_claimed": is_crypto_resend,
                "same_email": True,
                "resent_email": is_crypto_resend,
                "email_sent": bool(email_result.get("ok")),
                "sender_email": str(email_result.get("sender_email") or "info@turboapply.agency"),
                "issued_at": existing_issued,
                "plan": plan_key,
                "message": (
                    f"This Transaction ID has already been claimed with your email. "
                    f"We have resent your license key to {email_clean}."
                    if is_crypto_resend
                    else f"Payment confirmed! Your license key has been issued and sent to {email_clean}."
                ),
            }
        )
        return 200, res

    # New claim: derive canonical license key from transaction_id
    if tx_clean:
        lic_key = derive_license_key(f"tx:{tx_clean.lower()}")
    elif explicit_key and is_explicit_pro_license_key(explicit_key):
        lic_key = explicit_key.upper()
    else:
        seed = sub_clean or support_code or f"{email_clean}:{sess_id if (sess_id := session_id) else device_id}"
        lic_key = derive_license_key(seed)

    res = upsert_and_bind_license(
        conn,
        db_lock,
        license_key=lic_key,
        status="active",
        customer_email=email_clean,
        subscription_id=sub_clean,
        transaction_id=tx_clean,
        payment_provider=provider_clean,
        device_id=device_id,
        support_code=support_code,
        session_id=session_id,
        period_days=period_days,
        price_usd=price_usd,
        plan_id=plan_key,
    )

    email_result = send_license_email(
        recipient_email=email_clean,
        license_key=lic_key,
        plan_id=plan_key,
        payment_provider=provider_clean,
        transaction_id=tx_clean,
        support_code=support_code,
        expires_at=res["expires_at"],
        is_resend=False,
        conn=conn,
        db_lock=db_lock,
    )

    if send_telegram_fn is not None:
        notify_subscription_telegram(
            send_telegram_fn,
            title=f"AutoApply Pro Checkout Completed ({plan_meta['display_price']})",
            license_key=lic_key,
            customer_email=email_clean,
            support_code=support_code,
            device_id=device_id,
            payment_provider=provider_clean,
            plan_id=plan_key,
            subscription_id=sub_clean,
            transaction_id=tx_clean,
            expires_at=res["expires_at"],
        )

    res.update(
        {
            "already_claimed": False,
            "same_email": True,
            "resent_email": False,
            "email_sent": bool(email_result.get("ok")),
            "sender_email": str(email_result.get("sender_email") or "info@turboapply.agency"),
            "plan": plan_key,
            "message": f"Payment confirmed! Your license key has been issued and sent to {email_clean}.",
        }
    )
    return 200, res


def handle_paddle_webhook(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    raw_body: bytes,
    signature_header: str,
    payload: dict[str, Any],
    send_telegram_fn: Callable[[str], None],
    storage_dir: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    creds = _load_paddle_server_credentials(storage_dir)
    # Enforce signature check if PADDLE_WEBHOOK_SECRET env is set, OR if signature_header was provided and paddle_config.json has webhook_secret
    env_webhook_secret = os.getenv("PADDLE_WEBHOOK_SECRET", "").strip()
    active_webhook_secret = env_webhook_secret or (creds["webhook_secret"] if signature_header else "")
    if active_webhook_secret:
        if not verify_paddle_signature(
            raw_body=raw_body,
            signature_header=signature_header,
            webhook_secret=active_webhook_secret,
        ):
            return 401, {"ok": False, "error": "invalid_paddle_signature"}

    event_id = str(payload.get("event_id") or payload.get("notification_id") or f"evt_{uuid.uuid4().hex[:12]}").strip()
    event_type = str(payload.get("event_type") or "").strip().lower()
    if not event_type:
        return 400, {"ok": False, "error": "missing_event_type"}

    with db_lock, conn:
        dup = conn.execute(
            "SELECT * FROM paddle_webhook_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
    if dup is not None:
        return 200, {
            "ok": True,
            "duplicate_ignored": True,
            "event_id": event_id,
            "license_key": str(dup["license_key"]),
            "status": str(dup["resulting_status"]),
        }

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
    if not customer_email and customer_id and creds.get("api_key"):
        customer_email = _fetch_paddle_customer_email(customer_id, creds)

    device_id = str(custom_data.get("device_id") or "").strip()
    support_code = str(custom_data.get("support_code") or "").strip()
    session_id = str(custom_data.get("checkout_session_id") or custom_data.get("session_id") or "").strip()
    plan_id = _resolve_plan_from_paddle_data(
        data,
        creds["price_to_plan"],
        str(custom_data.get("plan") or "monthly").strip().lower(),
    )

    mgmt_urls = data.get("management_urls") if isinstance(data.get("management_urls"), dict) else {}
    manage_url = str(mgmt_urls.get("cancel") or mgmt_urls.get("update_payment_method") or "").strip()

    explicit_key = str(custom_data.get("license_key") or data.get("license_key") or "").strip()
    if explicit_key and is_explicit_pro_license_key(explicit_key):
        license_key = explicit_key.upper()
    else:
        existing_key = ""
        with db_lock, conn:
            if transaction_id:
                row = conn.execute(
                    "SELECT license_key FROM license_keys WHERE LOWER(transaction_id) = LOWER(?) LIMIT 1",
                    (transaction_id,),
                ).fetchone()
                if row:
                    existing_key = str(row["license_key"])
            if not existing_key and subscription_id:
                row = conn.execute(
                    "SELECT license_key FROM license_keys WHERE subscription_id = ? LIMIT 1",
                    (subscription_id,),
                ).fetchone()
                if row:
                    existing_key = str(row["license_key"])
            if not existing_key and session_id:
                sess_row = conn.execute(
                    "SELECT license_key FROM checkout_sessions WHERE session_id = ? AND license_key != '' LIMIT 1",
                    (session_id,),
                ).fetchone()
                if sess_row:
                    existing_key = str(sess_row["license_key"])
            if not existing_key and support_code:
                row = conn.execute(
                    "SELECT license_key FROM license_keys WHERE support_code = ? ORDER BY updated_at DESC LIMIT 1",
                    (support_code,),
                ).fetchone()
                if row:
                    existing_key = str(row["license_key"])
        if existing_key:
            license_key = existing_key
        elif transaction_id:
            license_key = derive_license_key(f"tx:{transaction_id.lower()}")
        else:
            seed = subscription_id or support_code or device_id or customer_email or event_id
            license_key = derive_license_key(seed)

    plan_meta = PRICING_PLANS.get(plan_id, PRICING_PLANS["monthly"])
    period_days = int(plan_meta["period_days"])
    price_usd = int(plan_meta["price_usd"])
    expires_override = ""
    billing_period = data.get("current_billing_period")
    if isinstance(billing_period, dict):
        ends_at = str(billing_period.get("ends_at") or "").strip()
        if ends_at:
            try:
                dt_end = dt.datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
                expires_override = dt_end.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass

    data_status = str(data.get("status") or "").strip().lower()
    action = str(data.get("action") or "").strip().lower()

    if event_type in (
        "transaction.completed",
        "transaction.paid",
        "subscription.created",
        "subscription.activated",
        "subscription.purchased",
        "subscription.renewed",
    ):
        new_status = "active"
        tg_title = "New AutoApply Pro License" if ("created" in event_type or "completed" in event_type or "paid" in event_type or "purchased" in event_type) else "AutoApply Pro Subscription Renewed"
    elif event_type in ("subscription.updated", "subscription.resumed"):
        if data_status in ("canceled", "cancelled"):
            new_status = "expired_cancelled"
            expires_override = utc_now_iso()
            tg_title = "AutoApply Pro Subscription Cancelled"
        elif data_status in ("past_due", "paused"):
            new_status = "expired_payment_failed"
            expires_override = utc_now_iso()
            tg_title = "AutoApply Pro Payment Past Due / Paused"
        else:
            new_status = "active"
            tg_title = "AutoApply Pro Subscription Updated (Active)"
    elif event_type in ("subscription.canceled", "subscription.cancelled", "subscription.cancelled_expired"):
        new_status = "expired_cancelled"
        expires_override = utc_now_iso()
        tg_title = "AutoApply Pro Subscription Cancelled"
    elif event_type in ("subscription.past_due", "subscription.paused", "transaction.payment_failed", "payment.failed_final"):
        new_status = "expired_payment_failed"
        expires_override = utc_now_iso()
        tg_title = "AutoApply Pro Subscription Payment Failed"
    elif event_type in ("adjustment.updated", "adjustment.created", "subscription.refunded"):
        if event_type == "subscription.refunded" or (action in ("refund", "chargeback", "credit") and data_status in ("approved", "completed", "")):
            new_status = "revoked_refund"
            expires_override = utc_now_iso()
            tg_title = "AutoApply Pro Subscription Refunded (Key Revoked)"
        else:
            new_status = "active"
            tg_title = "AutoApply Pro Adjustment Processed"
    else:
        return 200, {"ok": True, "ignored_event_type": event_type, "event_id": event_id}

    res = upsert_and_bind_license(
        conn,
        db_lock,
        license_key=license_key,
        status=new_status,
        customer_email=customer_email,
        customer_id=customer_id,
        subscription_id=subscription_id,
        transaction_id=transaction_id,
        payment_provider="paddle",
        device_id=device_id,
        support_code=support_code,
        session_id=session_id,
        period_days=period_days,
        price_usd=price_usd,
        expires_at_override=expires_override,
        manage_url=manage_url,
        plan_id=plan_id,
    )

    with db_lock, conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO paddle_webhook_events (
                event_id, event_type, license_key, subscription_id,
                transaction_id, resulting_status, payload_json, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                license_key,
                subscription_id,
                transaction_id,
                new_status,
                json.dumps(payload, ensure_ascii=False),
                utc_now_iso(),
            ),
        )
        conn.commit()

    if customer_email and "@" in customer_email:
        def _send_webhook_lifecycle_email() -> None:
            if new_status == "active":
                if event_type == "subscription.renewed":
                    send_lifecycle_email(
                        template_type="subscription_renewed",
                        recipient_email=customer_email,
                        license_key=license_key,
                        plan_id=plan_id,
                        payment_provider="paddle",
                        transaction_id=transaction_id or subscription_id,
                        expires_at=res["expires_at"],
                        reference_id=f"renew:{event_id}:{transaction_id or res['expires_at']}",
                        conn=conn,
                        db_lock=db_lock,
                    )
                else:
                    send_license_email(
                        recipient_email=customer_email,
                        license_key=license_key,
                        plan_id=plan_id,
                        payment_provider="paddle",
                        transaction_id=transaction_id or subscription_id,
                        support_code=support_code,
                        expires_at=res["expires_at"],
                        is_resend=False,
                        conn=conn,
                        db_lock=db_lock,
                    )
            elif new_status == "expired_cancelled":
                receipt = build_gateway_confirmation_receipt(
                    action="cancel",
                    license_key=license_key,
                    subscription_id=subscription_id,
                    payment_provider="paddle",
                )
                send_lifecycle_email(
                    template_type="subscription_cancelled",
                    recipient_email=customer_email,
                    license_key=license_key,
                    plan_id=plan_id,
                    payment_provider="paddle",
                    expires_at=res["expires_at"],
                    gateway_receipt_id=receipt["gateway_receipt_id"],
                    gateway_provider=receipt["gateway_provider"],
                    gateway_status=receipt["gateway_status"],
                    reference_id=receipt["gateway_receipt_id"],
                    conn=conn,
                    db_lock=db_lock,
                )
            elif event_type == "subscription.paused" or data_status == "paused":
                receipt = build_gateway_confirmation_receipt(
                    action="pause",
                    license_key=license_key,
                    subscription_id=subscription_id,
                    payment_provider="paddle",
                )
                send_lifecycle_email(
                    template_type="subscription_paused",
                    recipient_email=customer_email,
                    license_key=license_key,
                    plan_id=plan_id,
                    payment_provider="paddle",
                    expires_at=res["expires_at"],
                    gateway_receipt_id=receipt["gateway_receipt_id"],
                    gateway_provider=receipt["gateway_provider"],
                    gateway_status=receipt["gateway_status"],
                    reference_id=receipt["gateway_receipt_id"],
                    conn=conn,
                    db_lock=db_lock,
                )

        if os.getenv("PYTEST_CURRENT_TEST"):
            _send_webhook_lifecycle_email()
        else:
            threading.Thread(target=_send_webhook_lifecycle_email, daemon=True).start()

    notify_subscription_telegram(
        send_telegram_fn,
        title=tg_title,
        license_key=license_key,
        customer_email=customer_email,
        support_code=support_code,
        device_id=device_id,
        payment_provider="paddle",
        plan_id=plan_id,
        subscription_id=subscription_id,
        transaction_id=transaction_id,
        expires_at=res["expires_at"],
    )

    return 200, {
        "ok": True,
        "event_id": event_id,
        "event_type": event_type,
        "plan": plan_id,
        "price_usd": price_usd,
        "license_key": license_key,
        "status": new_status,
        "expires_at": res["expires_at"],
        "lease": res["lease"],
    }


def query_device_subscription_status(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    device_id: str,
    support_code: str,
    session_id: str = "",
    email: str = "",
) -> dict[str, Any]:
    row = None
    with db_lock, conn:
        if session_id:
            sess = conn.execute(
                "SELECT * FROM checkout_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if sess and sess["license_key"]:
                row = conn.execute(
                    "SELECT * FROM license_keys WHERE license_key = ?",
                    (str(sess["license_key"]),),
                ).fetchone()
        if row is None and support_code:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE support_code = ? ORDER BY updated_at DESC LIMIT 1",
                (support_code,),
            ).fetchone()
        if row is None and device_id and device_id != "mac_local_device":
            row = conn.execute(
                "SELECT * FROM license_keys WHERE active_device_id = ? ORDER BY updated_at DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        if row is None and email:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE LOWER(customer_email) = LOWER(?) ORDER BY updated_at DESC LIMIT 1",
                (email,),
            ).fetchone()

    gateway_enforced = os.getenv("AUTOAPPLY_ENFORCE_LICENSING_LIMITS", "").strip().lower() in ("1", "true", "yes")
    if row is None:
        return {
            "ok": True,
            "has_active_subscription": False,
            "status": "unactivated",
            "device_id": device_id,
            "support_code": support_code,
            "payment_gateway_live": gateway_enforced,
            "licensing_limits_enforced": gateway_enforced,
            "trial_mode_grace_active": not gateway_enforced,
        }

    row_keys = set(row.keys())
    lic_key = str(row["license_key"])
    lic_status = str(row["status"])
    expires_at = str(row["expires_at"])
    issued_at = str(row["issued_at"])
    price_usd_val = int(row["price_usd_monthly"] or MONTHLY_PRICE_USD)
    stored_plan = str(row["plan_id"] or "") if "plan_id" in row_keys else ""
    pause_until = str(row["pause_until"] or "") if "pause_until" in row_keys else ""
    cancelled_at = str(row["cancelled_at"] or "") if "cancelled_at" in row_keys else ""
    resolved_plan = infer_plan_id_from_license(
        license_key=lic_key,
        plan_id=stored_plan,
        price_usd=price_usd_val,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    plan_fields = build_plan_summary_fields(resolved_plan)
    now_dt = utc_now()
    is_expired = False
    try:
        exp_dt = dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=dt.timezone.utc)
        is_expired = now_dt >= exp_dt
    except Exception:
        pass

    active = (lic_status == "active") and not is_expired
    lease = build_signed_lease(
        device_id=device_id or str(row["active_device_id"] or "mac_local_device"),
        support_code=support_code or str(row["support_code"] or ""),
        license_key=lic_key,
        issued_at=issued_at,
        expires_at=expires_at,
        signing_secret=_LeaseSigningSecret(),
    )
    return {
        "ok": True,
        "has_active_subscription": active,
        "license_key": lic_key,
        "status": "active" if active else ("expired" if is_expired else lic_status),
        "price_usd_monthly": price_usd_val,
        "payment_provider": str(row["payment_provider"] or "paddle"),
        "customer_email": str(row["customer_email"] or ""),
        "subscription_id": str(row["subscription_id"] or ""),
        "transaction_id": str(row["transaction_id"] or ""),
        "manage_url": str(row["manage_url"] or ""),
        "pause_until": pause_until,
        "cancelled_at": cancelled_at,
        "issued_at": issued_at,
        "expires_at": expires_at,
        **plan_fields,
        "lease": lease,
    }


def activate_license_on_server(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    license_key: str,
    device_id: str,
    support_code: str = "",
    transfer_seat: bool = True,
) -> tuple[int, dict[str, Any]]:
    _ = transfer_seat
    raw_key = str(license_key or "").strip().upper()
    if not raw_key:
        return 400, {"ok": False, "error": "missing_license_key"}

    with db_lock, conn:
        norm_key = normalize_incoming_license_key(raw_key, conn)
        row = conn.execute(
            "SELECT * FROM license_keys WHERE license_key = ?",
            (norm_key,),
        ).fetchone()

    if row is not None:
        row_keys = set(row.keys())
        lic_status = str(row["status"])
        expires_at = str(row["expires_at"])
        if lic_status != "active":
            return 403, {
                "ok": False,
                "error": f"license_{lic_status}",
                "message": f"License {norm_key} is not active (status={lic_status}).",
            }
        try:
            exp_dt = dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=dt.timezone.utc)
            if utc_now() >= exp_dt:
                return 403, {
                    "ok": False,
                    "error": "license_expired",
                    "message": f"License {norm_key} expired on {expires_at}.",
                }
        except Exception:
            pass

        bound_sup = str(row["support_code"] or "")
        bound_dev = str(row["active_device_id"] or "")
        stored_plan = str(row["plan_id"] or "") if "plan_id" in row_keys else ""

        res = upsert_and_bind_license(
            conn,
            db_lock,
            license_key=norm_key,
            status="active",
            customer_email=str(row["customer_email"] or ""),
            customer_id=str(row["customer_id"] or ""),
            subscription_id=str(row["subscription_id"] or ""),
            transaction_id=str(row["transaction_id"] or ""),
            payment_provider=str(row["payment_provider"] or "paddle"),
            device_id=device_id or bound_dev or "mac_local_device",
            support_code=support_code or bound_sup,
            price_usd=int(row["price_usd_monthly"] or MONTHLY_PRICE_USD),
            expires_at_override=expires_at,
            manage_url=str(row["manage_url"] or ""),
            plan_id=stored_plan,
        )
        return 200, res

    inferred_plan = infer_plan_id_from_license(license_key=norm_key)
    inferred_meta = PRICING_PLANS.get(inferred_plan, PRICING_PLANS["monthly"])
    res = upsert_and_bind_license(
        conn,
        db_lock,
        license_key=norm_key,
        status="active",
        payment_provider="paddle",
        device_id=device_id or "mac_local_device",
        support_code=support_code,
        period_days=int(inferred_meta["period_days"]),
        price_usd=int(inferred_meta["price_usd"]),
        plan_id=inferred_plan,
    )
    return 200, res


def pause_or_cancel_subscription(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    action: str,
    pause_months: int = 1,
    reason: str = "",
    customer_email: str = "",
    license_key: str = "",
    subscription_id: str = "",
    device_id: str = "mac_local_device",
    plan_id: str = "",
    storage_dir: Path | None = None,
    send_telegram_fn: Callable[[str], None] | None = None,
) -> tuple[int, dict[str, Any]]:
    act = str(action or "pause").strip().lower()
    if act not in ("pause", "cancel", "resume", "cancel_with_free_cycle", "refund_request"):
        return 400, {
            "ok": False,
            "error": "invalid_action",
            "message": "Action must be 'pause', 'cancel', 'resume', 'cancel_with_free_cycle', or 'refund_request'.",
        }

    months = max(1, min(6, int(pause_months or 1)))
    email_clean = str(customer_email or "").strip()
    key_clean = str(license_key or "").strip().upper()
    sub_clean = str(subscription_id or "").strip()
    dev_clean = str(device_id or "mac_local_device").strip()
    reason_clean = str(reason or "").strip()[:300]

    row = None
    with db_lock, conn:
        for col_sql in (
            "ALTER TABLE license_keys ADD COLUMN plan_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN pause_until TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN cancellation_reason TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN cancelled_at TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE license_keys ADD COLUMN gateway_receipt_id TEXT NOT NULL DEFAULT ''",
        ):
            try:
                conn.execute(col_sql)
            except sqlite3.OperationalError:
                pass

        if key_clean and "•" not in key_clean and "*" not in key_clean:
            norm_k = normalize_incoming_license_key(key_clean, conn)
            row = conn.execute(
                "SELECT * FROM license_keys WHERE license_key = ? LIMIT 1",
                (norm_k,),
            ).fetchone()
        elif key_clean and ("•" in key_clean or "*" in key_clean):
            cleaned_parts = [p for p in re.split(r"[•*]+", key_clean) if p]
            if len(cleaned_parts) >= 2:
                prefix, suffix = cleaned_parts[0], cleaned_parts[-1]
                row = conn.execute(
                    "SELECT * FROM license_keys WHERE license_key LIKE ? ORDER BY updated_at DESC LIMIT 1",
                    (f"{prefix}%{suffix}",),
                ).fetchone()

        if row is None and sub_clean:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE subscription_id = ? ORDER BY updated_at DESC LIMIT 1",
                (sub_clean,),
            ).fetchone()

        if row is None and email_clean:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE LOWER(customer_email) = LOWER(?) ORDER BY updated_at DESC LIMIT 1",
                (email_clean,),
            ).fetchone()

        if row is None and dev_clean:
            row = conn.execute(
                "SELECT * FROM license_keys WHERE active_device_id = ? ORDER BY updated_at DESC LIMIT 1",
                (dev_clean,),
            ).fetchone()

    now_dt = utc_now()
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    resolved_key = str(row["license_key"]) if row is not None else (key_clean or "AA-PRO-ACTIVE")
    resolved_sub = str(row["subscription_id"] or "") if row is not None else sub_clean
    resolved_email = (email_clean or str(row["customer_email"] or "")).strip() if row is not None else email_clean
    resolved_expires = str(row["expires_at"] or "") if row is not None else (now_dt + dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    resolved_issued = str(row["issued_at"] or "") if row is not None else now_iso
    resolved_price = int(row["price_usd_monthly"] or MONTHLY_PRICE_USD) if row is not None else MONTHLY_PRICE_USD
    resolved_provider = str(row["payment_provider"] or "paddle").strip().lower() if row is not None else "paddle"
    row_keys = set(row.keys()) if row is not None else set()
    stored_plan = str(row["plan_id"] or "") if (row is not None and "plan_id" in row_keys) else ""
    resolved_plan = infer_plan_id_from_license(
        license_key=resolved_key,
        plan_id=plan_id or stored_plan,
        price_usd=resolved_price,
        issued_at=resolved_issued,
        expires_at=resolved_expires,
    )
    plan_fields = build_plan_summary_fields(resolved_plan)
    receipt = build_gateway_confirmation_receipt(
        action=act,
        license_key=resolved_key,
        subscription_id=resolved_sub,
        payment_provider=resolved_provider,
        timestamp_iso=now_iso,
    )

    # Best-effort call to Paddle Billing API if subscription_id is a real Paddle sub_...
    paddle_synced = False
    if resolved_sub.startswith("sub_"):
        creds = _load_paddle_server_credentials(storage_dir)
        api_key = str(creds.get("api_key") or "").strip()
        if api_key:
            base = str(creds.get("api_base") or "https://api.paddle.com")
            try:
                if act == "pause":
                    resume_iso = (now_dt + dt.timedelta(days=30 * months)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    paddle_body = json.dumps({"effective_from": "next_billing_period", "resume_at": resume_iso}).encode("utf-8")
                    endpoint = f"{base}/subscriptions/{urllib.parse.quote(resolved_sub)}/pause"
                elif act == "resume":
                    paddle_body = json.dumps({"effective_from": "immediately"}).encode("utf-8")
                    endpoint = f"{base}/subscriptions/{urllib.parse.quote(resolved_sub)}/resume"
                else:
                    paddle_body = json.dumps({"effective_from": "next_billing_period"}).encode("utf-8")
                    endpoint = f"{base}/subscriptions/{urllib.parse.quote(resolved_sub)}/cancel"
                req = urllib.request.Request(
                    endpoint,
                    data=paddle_body,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": "AutoApply-LicenseServer/1.0",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=8.0) as resp:
                    if 200 <= resp.status < 300:
                        paddle_synced = True
            except Exception:
                paddle_synced = False

    if act == "pause":
        resume_dt = now_dt + dt.timedelta(days=30 * months)
        resume_iso = resume_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        resume_human = resume_dt.strftime("%b %d, %Y")
        if row is not None:
            with db_lock, conn:
                conn.execute(
                    """
                    UPDATE license_keys
                    SET pause_until = ?,
                        cancellation_reason = ?,
                        gateway_receipt_id = ?,
                        customer_email = COALESCE(NULLIF(?, ''), customer_email),
                        updated_at = ?
                    WHERE license_key = ?
                    """,
                    (
                        resume_iso,
                        reason_clean or f"paused_{months}m",
                        receipt["gateway_receipt_id"],
                        resolved_email,
                        now_iso,
                        resolved_key,
                    ),
                )
                conn.commit()
        email_res = (
            send_lifecycle_email(
                template_type="subscription_paused",
                recipient_email=resolved_email,
                license_key=resolved_key,
                plan_id=resolved_plan,
                payment_provider=resolved_provider,
                expires_at=resolved_expires,
                pause_months=months,
                pause_until_label=resume_human,
                gateway_receipt_id=receipt["gateway_receipt_id"],
                gateway_provider=receipt["gateway_provider"],
                gateway_status=receipt["gateway_status"],
                reference_id=f"{receipt['gateway_receipt_id']}:{resume_iso}",
                conn=conn,
                db_lock=db_lock,
            )
            if (resolved_email and "@" in resolved_email)
            else {"ok": False}
        )
        if send_telegram_fn is not None:
            notify_subscription_telegram(
                send_telegram_fn,
                title=f"AutoApply Pro Subscription Suspended/Paused ({months} mo until {resume_human})",
                license_key=resolved_key,
                customer_email=resolved_email,
                device_id=dev_clean,
                payment_provider=resolved_provider,
                plan_id=resolved_plan,
                subscription_id=resolved_sub,
                expires_at=resolved_expires,
                gateway_receipt_id=receipt["gateway_receipt_id"],
                gateway_status=receipt["gateway_summary"],
            )
        return 200, {
            "ok": True,
            "action": "pause",
            "subscription_state": "paused",
            "pause_months": months,
            "pause_until": resume_iso,
            "pause_until_label": resume_human,
            "license_key": resolved_key,
            "expires_at": resolved_expires,
            "paddle_synced": paddle_synced,
            "email_sent": bool(email_res.get("ok")),
            **receipt,
            **plan_fields,
            "message": (
                f"Gateway Confirmation Receipt #{receipt['gateway_receipt_id']} ({receipt['gateway_provider']} · Suspended): "
                f"Your {plan_fields['plan_name']} subscription is paused for {months} "
                f"{'month' if months == 1 else 'months'} (resumes {resume_human}). "
                f"You will not be billed during the pause, and a confirmation receipt has been sent to your email."
            ),
        }

    if act == "resume":
        if row is not None:
            with db_lock, conn:
                conn.execute(
                    """
                    UPDATE license_keys
                    SET status = 'active',
                        pause_until = '',
                        cancelled_at = '',
                        gateway_receipt_id = ?,
                        updated_at = ?
                    WHERE license_key = ?
                    """,
                    (receipt["gateway_receipt_id"], now_iso, resolved_key),
                )
                conn.commit()
        return 200, {
            "ok": True,
            "action": "resume",
            "subscription_state": "active",
            "license_key": resolved_key,
            "expires_at": resolved_expires,
            "paddle_synced": paddle_synced,
            **receipt,
            **plan_fields,
            "message": f"Your {plan_fields['plan_name']} subscription is active and billing has been resumed.",
        }

    # act in ("cancel", "cancel_with_free_cycle", "refund_request")
    free_cycle_added = act == "cancel_with_free_cycle"
    added_period_days = 0
    if free_cycle_added:
        raw_pdays = int(PRICING_PLANS.get(resolved_plan, PRICING_PLANS["monthly"])["period_days"])
        added_period_days = 30 if raw_pdays > 365 else max(7, raw_pdays)
        base_exp_dt = now_dt
        try:
            parsed_exp = dt.datetime.fromisoformat(resolved_expires.replace("Z", "+00:00"))
            if parsed_exp.tzinfo is None:
                parsed_exp = parsed_exp.replace(tzinfo=dt.timezone.utc)
            if parsed_exp > now_dt:
                base_exp_dt = parsed_exp
        except Exception:
            base_exp_dt = now_dt
        resolved_expires = (base_exp_dt + dt.timedelta(days=added_period_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    effective_reason = (
        reason_clean
        or (
            "cancel_with_free_cycle_retention"
            if free_cycle_added
            else ("refund_requested" if act == "refund_request" else "cancelled_on_website")
        )
    )

    if row is not None:
        with db_lock, conn:
            conn.execute(
                """
                UPDATE license_keys
                SET cancelled_at = ?,
                    cancellation_reason = ?,
                    pause_until = '',
                    expires_at = ?,
                    gateway_receipt_id = ?,
                    customer_email = COALESCE(NULLIF(?, ''), customer_email),
                    updated_at = ?
                WHERE license_key = ?
                """,
                (
                    now_iso,
                    effective_reason,
                    resolved_expires,
                    receipt["gateway_receipt_id"],
                    resolved_email,
                    now_iso,
                    resolved_key,
                ),
            )
            conn.commit()

    email_res = (
        send_lifecycle_email(
            template_type="subscription_cancelled",
            recipient_email=resolved_email,
            license_key=resolved_key,
            plan_id=resolved_plan,
            payment_provider=resolved_provider,
            expires_at=resolved_expires,
            gateway_receipt_id=receipt["gateway_receipt_id"],
            gateway_provider=receipt["gateway_provider"],
            gateway_status=receipt["gateway_status"],
            free_cycle_added=free_cycle_added,
            reference_id=f"{receipt['gateway_receipt_id']}:{act}",
            conn=conn,
            db_lock=db_lock,
        )
        if (resolved_email and "@" in resolved_email)
        else {"ok": False}
    )

    if send_telegram_fn is not None:
        tg_title = (
            f"AutoApply Pro Cancelled + 1 Free Cycle Granted (+{added_period_days}d)"
            if free_cycle_added
            else (
                "AutoApply Pro Cancellation & Refund Requested"
                if act == "refund_request"
                else f"AutoApply Pro Subscription Cancelled ({effective_reason})"
            )
        )
        notify_subscription_telegram(
            send_telegram_fn,
            title=tg_title,
            license_key=resolved_key,
            customer_email=resolved_email,
            device_id=dev_clean,
            payment_provider=resolved_provider,
            plan_id=resolved_plan,
            subscription_id=resolved_sub,
            expires_at=resolved_expires,
            gateway_receipt_id=receipt["gateway_receipt_id"],
            gateway_status=receipt["gateway_summary"],
        )

    exp_label = _format_email_expiry_label(resolved_expires, resolved_plan)
    if free_cycle_added:
        msg = (
            f"Gateway Confirmation Receipt #{receipt['gateway_receipt_id']} ({receipt['gateway_provider']} · Cancelled): "
            f"Your recurring subscription is cancelled and will not renew. "
            f"We have added 1 complimentary billing period on us (+{added_period_days} days free) — your license key {resolved_key} remains active through {exp_label}."
        )
    elif act == "refund_request":
        msg = (
            f"Gateway Confirmation Receipt #{receipt['gateway_receipt_id']} ({receipt['gateway_provider']} · Refund Requested): "
            f"Your recurring subscription has been cancelled and your refund request has been logged for review. "
            f"A confirmation receipt has been sent to your email."
        )
    else:
        msg = (
            f"Gateway Confirmation Receipt #{receipt['gateway_receipt_id']} ({receipt['gateway_provider']} · Cancelled): "
            f"Your {plan_fields['plan_name']} subscription has been cancelled and will not renew. "
            f"Your Mac keeps full AutoApply Pro access through {exp_label}, and a confirmation receipt has been emailed to you."
        )

    return 200, {
        "ok": True,
        "action": act,
        "subscription_state": "cancel_scheduled",
        "cancelled_at": now_iso,
        "license_key": resolved_key,
        "expires_at": resolved_expires,
        "expires_at_label": exp_label,
        "free_cycle_added": free_cycle_added,
        "added_period_days": added_period_days,
        "paddle_synced": paddle_synced,
        "email_sent": bool(email_res.get("ok")),
        **receipt,
        **plan_fields,
        "message": msg,
    }


def register_or_update_trial(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
    *,
    device_id: str,
    customer_email: str,
    trial_started_at: str = "",
    trial_expires_at: str = "",
) -> dict[str, Any]:
    dev_clean = str(device_id or "").strip()
    email_clean = str(customer_email or "").strip()
    if not dev_clean or not email_clean or "@" not in email_clean:
        return {"ok": False}
    now_dt = utc_now()
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_iso = trial_started_at or now_iso
    exp_iso = trial_expires_at or (now_dt + dt.timedelta(hours=TRIAL_DURATION_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db_lock, conn:
        conn.execute(
            """
            INSERT INTO trial_registrations (device_id, customer_email, trial_started_at, trial_expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                customer_email = COALESCE(NULLIF(excluded.customer_email, ''), trial_registrations.customer_email),
                updated_at = excluded.updated_at
            """,
            (dev_clean[:120], email_clean[:180], start_iso, exp_iso, now_iso),
        )
        conn.commit()
    return {"ok": True, "device_id": dev_clean, "customer_email": email_clean, "trial_expires_at": exp_iso}


def run_scheduled_lifecycle_emails(
    conn: sqlite3.Connection,
    db_lock: threading.Lock,
) -> dict[str, Any]:
    """Scan active subscriptions and trials to send automatic reminder emails:
    - `subscription_renewing_soon`: when an active, uncancelled recurring subscription is within 2 days (52h) of renewal.
    - `trial_expiring`: when a registered free trial has < 12 hours remaining.
    - `trial_expired`: when a registered free trial has expired and has not upgraded.
    """
    now_dt = utc_now()
    sent_counts = {"subscription_renewing_soon": 0, "trial_expiring": 0, "trial_expired": 0}

    with db_lock, conn:
        lic_rows = conn.execute(
            """
            SELECT * FROM license_keys
            WHERE status = 'active'
              AND customer_email != ''
              AND (cancelled_at IS NULL OR cancelled_at = '')
              AND (pause_until IS NULL OR pause_until = '')
            """
        ).fetchall()
        trial_rows = conn.execute(
            "SELECT * FROM trial_registrations WHERE customer_email != ''"
        ).fetchall()
        paid_emails = {
            str(r["customer_email"] or "").strip().lower()
            for r in lic_rows
            if str(r["customer_email"] or "").strip()
        }

    for r in lic_rows:
        r_keys = set(r.keys())
        lic_key = str(r["license_key"] or "")
        email = str(r["customer_email"] or "").strip()
        expires_at = str(r["expires_at"] or "").strip()
        stored_plan = str(r["plan_id"] or "") if "plan_id" in r_keys else ""
        resolved_plan = infer_plan_id_from_license(
            license_key=lic_key,
            plan_id=stored_plan,
            price_usd=int(r["price_usd_monthly"] or MONTHLY_PRICE_USD),
            issued_at=str(r["issued_at"] or ""),
            expires_at=expires_at,
        )
        if resolved_plan == "lifetime" or not expires_at or "@" not in email:
            continue
        try:
            exp_dt = dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=dt.timezone.utc)
            hours_left = (exp_dt - now_dt).total_seconds() / 3600.0
            if 0.0 < hours_left <= 52.0:
                res = send_lifecycle_email(
                    template_type="subscription_renewing_soon",
                    recipient_email=email,
                    license_key=lic_key,
                    plan_id=resolved_plan,
                    payment_provider=str(r["payment_provider"] or "paddle"),
                    expires_at=expires_at,
                    reference_id=f"renew2d:{lic_key}:{expires_at[:10]}",
                    conn=conn,
                    db_lock=db_lock,
                )
                if res.get("ok") and not res.get("already_sent"):
                    sent_counts["subscription_renewing_soon"] += 1
        except Exception:
            pass

    for tr in trial_rows:
        dev_id = str(tr["device_id"] or "")
        email = str(tr["customer_email"] or "").strip()
        exp_iso = str(tr["trial_expires_at"] or "").strip()
        if not email or "@" not in email or email.lower() in paid_emails or not exp_iso:
            continue
        try:
            exp_dt = dt.datetime.fromisoformat(exp_iso.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=dt.timezone.utc)
            hours_left = (exp_dt - now_dt).total_seconds() / 3600.0
            if 0.0 < hours_left <= 12.0:
                res = send_lifecycle_email(
                    template_type="trial_expiring",
                    recipient_email=email,
                    expires_at=exp_iso,
                    reference_id=f"trial_expiring:{dev_id}:{exp_iso[:10]}",
                    conn=conn,
                    db_lock=db_lock,
                )
                if res.get("ok") and not res.get("already_sent"):
                    sent_counts["trial_expiring"] += 1
            elif -168.0 <= hours_left <= 0.0:
                res = send_lifecycle_email(
                    template_type="trial_expired",
                    recipient_email=email,
                    expires_at=exp_iso,
                    reference_id=f"trial_expired:{dev_id}:{exp_iso[:10]}",
                    conn=conn,
                    db_lock=db_lock,
                )
                if res.get("ok") and not res.get("already_sent"):
                    sent_counts["trial_expired"] += 1
        except Exception:
            pass

    return {"ok": True, "sent_counts": sent_counts}


def render_standalone_subscribe_html(
    cfg: dict[str, Any],
    query: dict[str, list[str]],
) -> bytes:
    device_id = html.escape((query.get("device_id") or [""])[0].strip())
    email = html.escape((query.get("email") or [""])[0].strip())
    session_id = html.escape((query.get("session_id") or [""])[0].strip())
    plan_q = html.escape((query.get("plan") or ["monthly"])[0].strip().lower())
    if plan_q not in PRICING_PLANS:
        plan_q = "monthly"
    paddle_env = html.escape(str(cfg.get("paddle_environment") or "production"))
    paddle_token = html.escape(str(cfg.get("paddle_client_token") or ""))
    paddle_price = html.escape(str(cfg.get("paddle_price_id") or ""))
    paddle_price_ids_json = json.dumps(cfg.get("paddle_price_ids") if isinstance(cfg.get("paddle_price_ids"), dict) else {})

    wallets = cfg.get("crypto_wallets") if isinstance(cfg.get("crypto_wallets"), dict) else DEFAULT_CRYPTO_WALLETS
    rates = cfg.get("crypto_rates") if isinstance(cfg.get("crypto_rates"), dict) else get_daily_locked_crypto_rates()
    locked_date = html.escape(str(rates.get("locked_date") or utc_now().strftime("%Y-%m-%d")))
    monthly_quotes = (
        rates.get("plans", {}).get("monthly", {}).get("display", {})
        if isinstance(rates.get("plans"), dict)
        else {}
    )
    sol_addr = html.escape(str(wallets.get("solana") or DEFAULT_CRYPTO_WALLETS["solana"]))
    evm_addr = html.escape(str(wallets.get("evm") or DEFAULT_CRYPTO_WALLETS["evm"]))
    tron_addr = html.escape(str(wallets.get("tron") or DEFAULT_CRYPTO_WALLETS["tron"]))
    btc_addr = html.escape(str(wallets.get("btc") or DEFAULT_CRYPTO_WALLETS["btc"]))
    sol_amt = html.escape(str(monthly_quotes.get("solana") or "30.00 USDC / USDT"))
    rates_json = json.dumps(rates)
    wallets_json = json.dumps(wallets)

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Subscribe to AutoApply Pro ($10/wk · $30/mo · $200/yr · $200 Lifetime Special)</title>
  <script src="https://cdn.paddle.com/paddle/v2/paddle.js"></script>
  <style>
    :root {{
      --bg: #0c0d10;
      --card: #14161b;
      --border: rgba(255, 255, 255, 0.11);
      --text: #f5f6f8;
      --muted: #9ba1ae;
      --accent: #10b981;
      --accent-hover: #059669;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 40px 20px;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 32px;
      box-shadow: 0 20px 50px rgba(0,0,0,0.45);
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      font-size: 12px;
      font-weight: 600;
      margin-bottom: 12px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: -0.02em; }}
    p.sub {{ margin: 0 0 20px; color: var(--muted); font-size: 15px; }}
    .plans-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
      margin-bottom: 20px;
    }}
    .plan-opt {{
      text-align: left;
      padding: 12px 14px;
      border-radius: 11px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.03);
      color: var(--text);
      cursor: pointer;
    }}
    .plan-opt.is-active {{
      border-color: var(--accent);
      background: rgba(16, 185, 129, 0.12);
    }}
    .plan-opt strong {{ display: block; font-size: 16px; }}
    .plan-opt span {{ display: block; font-size: 12px; color: #34d399; font-weight: 600; margin-top: 2px; }}
    .plan-opt small {{ display: block; font-size: 11px; color: var(--muted); margin-top: 3px; }}
    .tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
    .tab {{
      flex: 1;
      padding: 10px 14px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.03);
      color: var(--muted);
      font-weight: 600;
      cursor: pointer;
    }}
    .tab.is-active {{ border-color: var(--accent); color: var(--text); background: rgba(16,185,129,0.12); }}
    .net-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 14px; }}
    .net-btn {{
      padding: 9px 10px;
      border-radius: 9px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.03);
      color: var(--text);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }}
    .net-btn.is-active {{ border-color: var(--accent); background: rgba(16,185,129,0.14); color: #34d399; }}
    .wallet-box {{
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: rgba(0,0,0,0.35);
      margin-bottom: 16px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px;
      word-break: break-all;
    }}
    .field {{ margin-bottom: 16px; }}
    .field label {{ display: block; font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }}
    .field input {{
      width: 100%;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: rgba(0,0,0,0.35);
      color: var(--text);
      font-size: 14px;
    }}
    .btn {{
      width: 100%;
      padding: 14px 20px;
      border-radius: 10px;
      border: none;
      background: var(--accent);
      color: #04130d;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
    }}
    .btn:hover {{ background: var(--accent-hover); color: #fff; }}
    .key-box {{
      margin-top: 22px;
      padding: 18px;
      border-radius: 12px;
      border: 1px solid rgba(16, 185, 129, 0.4);
      background: rgba(16, 185, 129, 0.08);
      display: none;
    }}
    .key-box.is-error {{
      border-color: rgba(239, 68, 68, 0.5);
      background: rgba(239, 68, 68, 0.1);
    }}
    .key-code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 18px;
      font-weight: 700;
      color: #34d399;
      margin: 8px 0;
      word-break: break-all;
    }}
    .meta {{ margin-top: 18px; font-size: 12px; color: var(--muted); text-align: center; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <span class="badge">AutoApply for macOS · 2-Day Free Trial · Pro Plans</span>
      <h1>Choose Your AutoApply Pro Plan</h1>
      <p class="sub">Unlock unlimited automated job applications, tailored 2-page resumes, 1-page cover letters, and ATS browser autofill. License keys are emailed immediately from <strong>info@turboapply.agency</strong>.</p>

      <div class="plans-grid" id="plan-selector">
        <button type="button" class="plan-opt" data-plan="weekly" data-label="Continue with Paddle · $10/week →">
          <strong>$10 / week</strong>
          <span>Flexible Weekly Pass</span>
          <small>7 days full access · Cancel anytime</small>
        </button>
        <button type="button" class="plan-opt is-active" data-plan="monthly" data-label="Continue with Paddle · $30/month →">
          <strong>$30 / month</strong>
          <span>Save 25% ($10/mo off vs. weekly)</span>
          <small>25% cheaper than weekly — save $10/mo</small>
        </button>
        <button type="button" class="plan-opt" data-plan="annual" data-label="Continue with Paddle · $200/year →">
          <strong>$200 / year</strong>
          <span>Save 62% ($320/yr off vs. weekly)</span>
          <small>~$16.67/mo · Save $160/yr vs. monthly</small>
        </button>
        <button type="button" class="plan-opt" data-plan="lifetime" data-label="Continue with Paddle · $200 Lifetime →">
          <strong>$200 Lifetime</strong>
          <span style="color:#f59e0b;">LIMITED-TIME-ONLY SPECIAL</span>
          <small>Pay once, own forever · Same price as 1 year</small>
        </button>
      </div>

      <div class="tabs">
        <button type="button" class="tab is-active" data-tab="card">Card / Apple Pay / PayPal</button>
        <button type="button" class="tab" data-tab="crypto">Crypto (USDC, USDT, SOL, ETH, BTC)</button>
      </div>

      <div class="field">
        <label for="sub-email">Email Address (your license key is sent immediately from info@turboapply.agency)</label>
        <input id="sub-email" type="email" placeholder="you@company.com" value="{email}" required />
      </div>

      <div id="panel-card">
        <button id="paddle-pay-btn" class="btn" type="button">Continue with Paddle · $30/month →</button>
      </div>

      <div id="panel-crypto" style="display:none;">
        <div class="net-grid">
          <button type="button" class="net-btn is-active" data-net="solana" data-addr="{sol_addr}">Solana</button>
          <button type="button" class="net-btn" data-net="evm" data-addr="{evm_addr}">ETH / Base</button>
          <button type="button" class="net-btn" data-net="tron" data-addr="{tron_addr}">TRON (TRC-20)</button>
          <button type="button" class="net-btn" data-net="btc" data-addr="{btc_addr}">Bitcoin (BTC)</button>
        </div>
        <div style="font-size:12px;color:var(--muted);margin-bottom:6px;">
          Send <strong id="crypto-amt" style="color:#34d399;">{sol_amt}</strong> (Rate locked daily UTC: {locked_date})
        </div>
        <div class="wallet-box" id="crypto-addr">{sol_addr}</div>
        <div class="field">
          <label for="sub-txid">Transaction Hash (TXID)</label>
          <input id="sub-txid" type="text" placeholder="Paste your on-chain TXID..." />
        </div>
        <button id="crypto-pay-btn" class="btn" type="button">Verify Transfer &amp; Email License Key →</button>
      </div>

      <div id="key-result" class="key-box">
        <div id="key-kicker" style="font-size: 12px; font-weight: 700; color: #34d399; text-transform: uppercase;">✓ License Active — License Key Issued</div>
        <div id="key-value" class="key-code">AA-PRO-XXXX-XXXX-XXXX</div>
        <div id="key-msg" style="font-size: 13px; color: var(--muted);">
          Paste the key above into <strong>AutoApply → Activate License</strong> (or if you opened checkout from AutoApply, your Mac unlocks automatically).
        </div>
      </div>

      <div class="meta">
        1 Mac seat · Official license delivery from <strong>info@turboapply.agency</strong>
      </div>
    </div>
  </div>

  <script>
    (() => {{
      const cfg = {{
        env: "{paddle_env}",
        token: "{paddle_token}",
        priceId: "{paddle_price}",
        priceIds: {paddle_price_ids_json},
        deviceId: "{device_id}" || "mac_local_device",
        sessionId: "{session_id}",
        plan: "{plan_q}" || "monthly",
        net: "solana",
        rates: {rates_json},
        wallets: {wallets_json}
      }};

      const planBtns = Array.from(document.querySelectorAll(".plan-opt"));
      const tabBtns = Array.from(document.querySelectorAll(".tab"));
      const netBtns = Array.from(document.querySelectorAll(".net-btn"));
      const payBtn = document.getElementById("paddle-pay-btn");
      const amtEl = document.getElementById("crypto-amt");
      const addrEl = document.getElementById("crypto-addr");

      const refreshCryptoQuote = () => {{
        const planQuotes = (cfg.rates.plans && cfg.rates.plans[cfg.plan] && cfg.rates.plans[cfg.plan].display) || {{}};
        if (amtEl && planQuotes[cfg.net]) amtEl.textContent = planQuotes[cfg.net];
        if (addrEl && cfg.wallets[cfg.net]) addrEl.textContent = cfg.wallets[cfg.net];
      }};

      const selectPlan = (planId) => {{
        cfg.plan = planId;
        planBtns.forEach((b) => {{
          const active = b.getAttribute("data-plan") === planId;
          b.classList.toggle("is-active", active);
          if (active && payBtn) payBtn.textContent = b.getAttribute("data-label") || "Continue with Paddle →";
        }});
        refreshCryptoQuote();
      }};

      planBtns.forEach((b) => b.addEventListener("click", () => selectPlan(b.getAttribute("data-plan"))));
      tabBtns.forEach((t) => t.addEventListener("click", () => {{
        const mode = t.getAttribute("data-tab");
        tabBtns.forEach((x) => x.classList.toggle("is-active", x === t));
        document.getElementById("panel-card").style.display = mode === "card" ? "block" : "none";
        document.getElementById("panel-crypto").style.display = mode === "crypto" ? "block" : "none";
      }}));
      netBtns.forEach((n) => n.addEventListener("click", () => {{
        cfg.net = n.getAttribute("data-net");
        netBtns.forEach((x) => x.classList.toggle("is-active", x === n));
        refreshCryptoQuote();
      }}));

      selectPlan(cfg.plan);

      const completeCheckoutOnServer = async (txId, subId, emailVal, method) => {{
        const resp = await fetch("/api/autoapply-license/checkout-complete", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            session_id: cfg.sessionId,
            device_id: cfg.deviceId,
            email: emailVal,
            plan: cfg.plan,
            transaction_id: txId || "",
            subscription_id: subId || "",
            payment_method: method || "crypto"
          }})
        }});
        const data = await resp.json();
        const box = document.getElementById("key-result");
        const kicker = document.getElementById("key-kicker");
        const val = document.getElementById("key-value");
        const msg = document.getElementById("key-msg");
        box.style.display = "block";
        if (!resp.ok || (data && data.ok === false)) {{
          box.classList.add("is-error");
          kicker.style.color = "#f87171";
          kicker.textContent = "Verification Notice";
          val.textContent = "";
          msg.textContent = (data && data.message) || "Unable to verify transaction.";
          return;
        }}
        box.classList.remove("is-error");
        kicker.style.color = "#34d399";
        kicker.textContent = data.resent_email
          ? "✓ Transaction Verified — License Key Resent to Email"
          : "✓ License Active — License Key Issued & Emailed";
        val.textContent = data.license_key || "";
        msg.textContent = data.message || "Your license key has been sent from info@turboapply.agency.";
      }};

      if (window.Paddle && cfg.token) {{
        if (cfg.env === "sandbox") {{
          window.Paddle.Environment.set("sandbox");
        }}
        window.Paddle.Initialize({{
          token: cfg.token,
          eventCallback: async (evt) => {{
            if (evt && evt.name === "checkout.completed") {{
              const d = evt.data || {{}};
              const emailVal = (d.customer && d.customer.email) || document.getElementById("sub-email").value.trim();
              await completeCheckoutOnServer(d.transaction_id || d.id || "", d.subscription_id || "", emailVal, "paddle");
            }}
          }}
        }});
      }}

      if (payBtn) {{
        payBtn.addEventListener("click", () => {{
          const emailVal = document.getElementById("sub-email").value.trim();
          if (!emailVal || !emailVal.includes("@")) {{
            document.getElementById("sub-email").focus();
            return;
          }}
          const activePriceId = (cfg.priceIds && cfg.priceIds[cfg.plan]) || cfg.priceId;
          if (window.Paddle && cfg.token && activePriceId) {{
            window.Paddle.Checkout.open({{
              settings: {{ displayMode: "overlay", theme: "dark", locale: "en" }},
              items: [{{ priceId: activePriceId, quantity: 1 }}],
              customer: {{ email: emailVal }},
              customData: {{
                device_id: cfg.deviceId,
                email: emailVal,
                checkout_session_id: cfg.sessionId,
                plan: cfg.plan,
                product: "autoapply_macos_pro"
              }}
            }});
          }}
        }});
      }}

      document.getElementById("crypto-pay-btn").addEventListener("click", async () => {{
        const emailVal = document.getElementById("sub-email").value.trim();
        const txVal = document.getElementById("sub-txid").value.trim();
        if (!emailVal || !emailVal.includes("@")) {{
          document.getElementById("sub-email").focus();
          return;
        }}
        if (!txVal || txVal.length < 6) {{
          document.getElementById("sub-txid").focus();
          return;
        }}
        await completeCheckoutOnServer(txVal, "", emailVal, "crypto");
      }});
    }})();
  </script>
</body>
</html>"""
    return page.encode("utf-8")
