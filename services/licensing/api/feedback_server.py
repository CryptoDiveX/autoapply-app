#!/usr/bin/env python3
from __future__ import annotations

import base64
import datetime as dt
import json
import mimetypes
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import licensing_routes

HOST = os.getenv('AUTOAPPLY_FEEDBACK_HOST', '127.0.0.1')
PORT = int(os.getenv('AUTOAPPLY_FEEDBACK_PORT', '8811'))
STORAGE_DIR = Path(os.getenv('AUTOAPPLY_FEEDBACK_STORAGE_DIR', '/var/lib/autoapply-feedback'))
BOT_TOKEN = os.getenv('AUTOAPPLY_FEEDBACK_BOT_TOKEN', '').strip()
BOT_USERNAME = os.getenv('AUTOAPPLY_FEEDBACK_BOT_USERNAME', 'AutoApplyFeedbackBot').strip().lstrip('@')
DEFAULT_SUBSCRIBERS = [
    part.strip()
    for part in os.getenv('AUTOAPPLY_FEEDBACK_DEFAULT_SUBSCRIBERS', '').replace(';', ',').split(',')
    if part.strip()
]
MAX_BODY_BYTES = int(os.getenv('AUTOAPPLY_FEEDBACK_MAX_BODY_BYTES', str(25 * 1024 * 1024)))
DB_LOCK = threading.Lock()


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sanitize_filename(name: str, fallback: str = 'attachment.bin') -> str:
    cleaned = re.sub(r'[^A-Za-z0-9._ -]+', '_', (name or '').strip())
    cleaned = cleaned.strip(' ._')
    return cleaned[:120] if cleaned else fallback


def get_db() -> sqlite3.Connection:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STORAGE_DIR / 'feedback.db'), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    return conn


def init_db() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    (STORAGE_DIR / 'submissions').mkdir(parents=True, exist_ok=True)
    with DB_LOCK, get_db() as conn:
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS feedback_submissions (
                feedback_id TEXT PRIMARY KEY,
                classification TEXT NOT NULL,
                classification_label TEXT NOT NULL,
                comment TEXT NOT NULL,
                app_section TEXT NOT NULL DEFAULT '',
                browser_url TEXT NOT NULL DEFAULT '',
                browser_title TEXT NOT NULL DEFAULT '',
                app_version TEXT NOT NULL DEFAULT '',
                device_id TEXT NOT NULL DEFAULT '',
                macos_version TEXT NOT NULL DEFAULT '',
                submitted_at TEXT NOT NULL,
                received_at TEXT NOT NULL,
                client_ip TEXT NOT NULL DEFAULT '',
                attachments_count INTEGER NOT NULL DEFAULT 0,
                attachments_json TEXT NOT NULL DEFAULT '[]',
                payload_json TEXT NOT NULL DEFAULT '{}',
                notified_subscribers_count INTEGER NOT NULL DEFAULT 0,
                delivery_log_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id TEXT PRIMARY KEY,
                chat_type TEXT NOT NULL DEFAULT 'private',
                username TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                subscribed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_delivered_feedback_id TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            '''
        )
        now = utc_now_iso()
        for chat_id in DEFAULT_SUBSCRIBERS:
            conn.execute(
                '''
                INSERT INTO subscribers (chat_id, chat_type, active, subscribed_at, updated_at)
                VALUES (?, 'private', 1, ?, ?)
                ON CONFLICT(chat_id) DO NOTHING
                ''',
                (str(chat_id), now, now),
            )
        licensing_routes.init_licensing_tables(conn)
        conn.commit()


def broadcast_text_to_subscribers(text: str) -> None:
    with DB_LOCK, get_db() as conn:
        rows = conn.execute("SELECT chat_id FROM subscribers WHERE active = 1").fetchall()
    for r in rows:
        telegram_api_json("sendMessage", {"chat_id": str(r["chat_id"]), "text": text, "disable_web_page_preview": True})


def telegram_api_json(method: str, payload: dict[str, Any], timeout: float = 25.0) -> dict[str, Any]:
    if not BOT_TOKEN:
        return {'ok': False, 'error': 'bot_token_missing'}
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/{method}'
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json; charset=utf-8'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode('utf-8', errors='ignore')
            err_json = json.loads(err_body)
            return {'ok': False, 'status': exc.code, 'description': err_json.get('description', err_body[:200])}
        except Exception:
            return {'ok': False, 'status': exc.code}
    except Exception as exc:
        return {'ok': False, 'error': type(exc).__name__}


def telegram_send_document(chat_id: str, file_path: Path, caption: str = '') -> dict[str, Any]:
    if not BOT_TOKEN or not file_path.is_file():
        return {'ok': False, 'error': 'missing_token_or_file'}
    boundary = f'----AutoApplyBoundary{uuid.uuid4().hex}'
    mime_type = mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
    file_bytes = file_path.read_bytes()

    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(f'--{boundary}\r\n'.encode('utf-8'))
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode('utf-8'))
        parts.append(f'{value}\r\n'.encode('utf-8'))

    add_field('chat_id', str(chat_id))
    if caption:
        add_field('caption', caption[:1000])

    parts.append(f'--{boundary}\r\n'.encode('utf-8'))
    parts.append(
        f'Content-Disposition: form-data; name="document"; filename="{file_path.name}"\r\n'.encode('utf-8')
    )
    parts.append(f'Content-Type: {mime_type}\r\n\r\n'.encode('utf-8'))
    parts.append(file_bytes)
    parts.append(b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode('utf-8'))
    body = b''.join(parts)

    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendDocument'
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Content-Length': str(len(body)),
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=45.0) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode('utf-8', errors='ignore')
            return {'ok': False, 'status': exc.code, 'description': err_body[:200]}
        except Exception:
            return {'ok': False, 'status': exc.code}
    except Exception as exc:
        return {'ok': False, 'error': type(exc).__name__}


def format_feedback_telegram_message(record: dict[str, Any]) -> str:
    cls = str(record.get('classification') or 'bug').lower()
    icon = '💡' if cls == 'improvement' else '🐞'
    label = 'Improvement Idea' if cls == 'improvement' else 'Bug Report'
    fb_id = record.get('feedback_id') or record.get('id') or 'unknown'
    section = record.get('app_section') or 'General'
    submitted_at = record.get('submitted_at') or record.get('received_at') or utc_now_iso()
    browser_url = record.get('browser_url') or ''
    browser_title = record.get('browser_title') or ''
    app_version = record.get('app_version') or ''
    comment = (record.get('comment') or '').strip() or '(No text comment provided)'
    att_count = int(record.get('attachments_count') or 0)

    lines = [
        f'{icon} AutoApply {label}',
        f'ID: #{fb_id}',
        f'Section: {section}',
        f'Submitted: {submitted_at}',
    ]
    if app_version:
        lines.append(f'App Version: {app_version}')
    if browser_title:
        lines.append(f'Page Title: {browser_title}')
    if browser_url:
        lines.append(f'Page URL: {browser_url}')
    lines.append(f'Attachments: {att_count}')
    lines.append('')
    lines.append('Comment:')
    lines.append(comment[:3200])
    return '\n'.join(lines)


def deliver_feedback_to_chat(chat_id: str, record: dict[str, Any], saved_files: list[dict[str, Any]]) -> dict[str, Any]:
    text = format_feedback_telegram_message(record)
    msg_res = telegram_api_json(
        'sendMessage',
        {
            'chat_id': str(chat_id),
            'text': text,
            'disable_web_page_preview': True,
        },
    )
    if not msg_res.get('ok'):
        return {'chat_id': str(chat_id), 'ok': False, 'error': msg_res.get('description') or msg_res.get('error') or 'send_failed'}

    docs_sent = 0
    for item in saved_files:
        p = Path(str(item.get('disk_path') or ''))
        if p.is_file():
            caption = f"#{record.get('feedback_id')} — {item.get('name') or p.name}"
            doc_res = telegram_send_document(str(chat_id), p, caption=caption)
            if doc_res.get('ok'):
                docs_sent += 1

    with DB_LOCK, get_db() as conn:
        conn.execute(
            'UPDATE subscribers SET last_delivered_feedback_id = ?, updated_at = ? WHERE chat_id = ?',
            (str(record.get('feedback_id') or ''), utc_now_iso(), str(chat_id)),
        )
        conn.commit()
    return {'chat_id': str(chat_id), 'ok': True, 'documents_sent': docs_sent}


def broadcast_feedback(record: dict[str, Any], saved_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with DB_LOCK, get_db() as conn:
        rows = conn.execute('SELECT chat_id FROM subscribers WHERE active = 1').fetchall()
    chat_ids = [str(r['chat_id']) for r in rows]
    results: list[dict[str, Any]] = []
    for cid in chat_ids:
        results.append(deliver_feedback_to_chat(cid, record, saved_files))
    notified_ok = sum(1 for r in results if r.get('ok'))
    with DB_LOCK, get_db() as conn:
        conn.execute(
            '''
            UPDATE feedback_submissions
            SET notified_subscribers_count = ?, delivery_log_json = ?
            WHERE feedback_id = ?
            ''',
            (notified_ok, json.dumps(results, ensure_ascii=False), str(record.get('feedback_id'))),
        )
        conn.commit()
    return results


def get_stats_summary() -> dict[str, Any]:
    with DB_LOCK, get_db() as conn:
        total = conn.execute('SELECT COUNT(*) AS c FROM feedback_submissions').fetchone()['c']
        bugs = conn.execute("SELECT COUNT(*) AS c FROM feedback_submissions WHERE classification = 'bug'").fetchone()['c']
        improvements = conn.execute("SELECT COUNT(*) AS c FROM feedback_submissions WHERE classification = 'improvement'").fetchone()['c']
        subs = conn.execute('SELECT COUNT(*) AS c FROM subscribers WHERE active = 1').fetchone()['c']
        recent_rows = conn.execute(
            '''
            SELECT feedback_id, classification, app_section, comment, attachments_count, received_at
            FROM feedback_submissions
            ORDER BY received_at DESC
            LIMIT 5
            '''
        ).fetchall()
    recent = [dict(r) for r in recent_rows]
    return {
        'total_feedback': int(total),
        'bugs_count': int(bugs),
        'improvements_count': int(improvements),
        'active_subscribers': int(subs),
        'recent': recent,
    }


def handle_bot_command(message: dict[str, Any]) -> None:
    chat = message.get('chat') or {}
    chat_id = str(chat.get('id') or '').strip()
    if not chat_id:
        return
    text = str(message.get('text') or '').strip()
    if not text:
        return
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split('@')[0]
    arg = parts[1].strip() if len(parts) > 1 else ''

    now = utc_now_iso()
    chat_type = str(chat.get('type') or 'private')
    username = str(chat.get('username') or (message.get('from') or {}).get('username') or '')
    first_name = str(chat.get('first_name') or (message.get('from') or {}).get('first_name') or '')
    last_name = str(chat.get('last_name') or (message.get('from') or {}).get('last_name') or '')
    title = str(chat.get('title') or '')

    if cmd in ('/start', '/subscribe'):
        with DB_LOCK, get_db() as conn:
            existing = conn.execute(
                'SELECT last_delivered_feedback_id FROM subscribers WHERE chat_id = ?',
                (chat_id,),
            ).fetchone()
            last_delivered = str(existing['last_delivered_feedback_id']) if existing else ''
            conn.execute(
                '''
                INSERT INTO subscribers (chat_id, chat_type, username, first_name, last_name, title, active, subscribed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    chat_type = excluded.chat_type,
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    title = excluded.title,
                    active = 1,
                    updated_at = excluded.updated_at
                ''',
                (chat_id, chat_type, username, first_name, last_name, title, now, now),
            )
            conn.commit()
        stats = get_stats_summary()
        reply = (
            '✅ Subscribed to AutoApply Feedback Issues (@AutoApplyFeedbackBot)\n\n'
            f'• Chat ID: {chat_id}\n'
            f'• Stored Feedback Issues: {stats["total_feedback"]} '
            f'({stats["bugs_count"]} bugs, {stats["improvements_count"]} improvements)\n\n'
            'Whenever a user submits feedback from the AutoApply app, the server stores it and '
            'immediately sends the issue report + full-resolution screenshots/attachments here.\n\n'
            'Commands:\n'
            '/status — Feedback statistics & recent issues\n'
            '/latest — View the 5 most recent issues\n'
            '/issue <id> — Fetch full details & attachments for an issue\n'
            '/unsubscribe — Pause notifications for this chat'
        )
        telegram_api_json('sendMessage', {'chat_id': chat_id, 'text': reply})

        if not last_delivered and stats['recent']:
            latest_id = stats['recent'][0]['feedback_id']
            send_stored_issue_to_chat(chat_id, latest_id)
        return

    if cmd in ('/unsubscribe', '/stop'):
        with DB_LOCK, get_db() as conn:
            conn.execute('UPDATE subscribers SET active = 0, updated_at = ? WHERE chat_id = ?', (now, chat_id))
            conn.commit()
        telegram_api_json(
            'sendMessage',
            {
                'chat_id': chat_id,
                'text': '🔕 Unsubscribed from AutoApply feedback notifications. Send /subscribe at any time to resume.',
            },
        )
        return

    if cmd in ('/status', '/stats'):
        stats = get_stats_summary()
        with DB_LOCK, get_db() as conn:
            sub_row = conn.execute('SELECT active FROM subscribers WHERE chat_id = ?', (chat_id,)).fetchone()
        is_sub = bool(sub_row and sub_row['active'] == 1)
        lines = [
            '📊 AutoApply Feedback Server Status',
            f'Subscription: {"✅ Active" if is_sub else "🔕 Inactive (send /subscribe)"}',
            f'Total Stored Feedback: {stats["total_feedback"]}',
            f'• Bugs: {stats["bugs_count"]}',
            f'• Improvements: {stats["improvements_count"]}',
            f'Active Subscribers: {stats["active_subscribers"]}',
        ]
        if stats['recent']:
            lines.append('\nRecent Submissions:')
            for item in stats['recent']:
                icon = '💡' if item['classification'] == 'improvement' else '🐞'
                snippet = (item['comment'] or '').replace('\n', ' ')[:70]
                lines.append(f"{icon} #{item['feedback_id']} [{item['app_section']}] — {snippet}")
        telegram_api_json('sendMessage', {'chat_id': chat_id, 'text': '\n'.join(lines)})
        return

    if cmd in ('/latest', '/list'):
        stats = get_stats_summary()
        if not stats['recent']:
            telegram_api_json('sendMessage', {'chat_id': chat_id, 'text': 'No feedback submissions stored yet.'})
            return
        lines = ['🗂 Latest AutoApply Feedback Issues:']
        for item in stats['recent']:
            icon = '💡' if item['classification'] == 'improvement' else '🐞'
            snippet = (item['comment'] or '').replace('\n', ' ')[:120]
            lines.append(
                f"\n{icon} #{item['feedback_id']} ({item['received_at']})\n"
                f"Section: {item['app_section']} | Attachments: {item['attachments_count']}\n"
                f"{snippet}\n"
                f"View files: /issue {item['feedback_id']}"
            )
        telegram_api_json('sendMessage', {'chat_id': chat_id, 'text': '\n'.join(lines)})
        return

    if cmd == '/issue':
        target_id = arg.lstrip('#').strip()
        if not target_id:
            telegram_api_json('sendMessage', {'chat_id': chat_id, 'text': 'Usage: /issue <feedback_id>'})
            return
        if not send_stored_issue_to_chat(chat_id, target_id):
            telegram_api_json('sendMessage', {'chat_id': chat_id, 'text': f'Issue #{target_id} not found.'})
        return


def send_stored_issue_to_chat(chat_id: str, feedback_id: str) -> bool:
    with DB_LOCK, get_db() as conn:
        row = conn.execute(
            'SELECT * FROM feedback_submissions WHERE feedback_id = ?',
            (feedback_id,),
        ).fetchone()
    if not row:
        return False
    record = dict(row)
    try:
        saved_files = json.loads(record.get('attachments_json') or '[]')
    except Exception:
        saved_files = []
    deliver_feedback_to_chat(chat_id, record, saved_files)
    return True


def configure_bot_commands() -> None:
    if not BOT_TOKEN:
        return
    telegram_api_json(
        'setMyCommands',
        {
            'commands': [
                {'command': 'subscribe', 'description': 'Subscribe to live AutoApply feedback issues'},
                {'command': 'status', 'description': 'Show feedback statistics & subscription status'},
                {'command': 'latest', 'description': 'List the 5 most recent feedback issues'},
                {'command': 'unsubscribe', 'description': 'Unsubscribe from live notifications'},
            ]
        },
    )


def telegram_poller_loop() -> None:
    if not BOT_TOKEN:
        return
    configure_bot_commands()
    with DB_LOCK, get_db() as conn:
        row = conn.execute("SELECT value FROM bot_state WHERE key = 'last_update_id'").fetchone()
        offset = int(row['value']) + 1 if row else 0

    while True:
        try:
            res = telegram_api_json(
                'getUpdates',
                {
                    'offset': offset,
                    'timeout': 20,
                    'allowed_updates': ['message'],
                },
                timeout=30.0,
            )
            if res.get('ok') and isinstance(res.get('result'), list):
                for upd in res['result']:
                    upd_id = int(upd.get('update_id') or 0)
                    if upd_id >= offset:
                        offset = upd_id + 1
                    msg = upd.get('message')
                    if isinstance(msg, dict):
                        try:
                            handle_bot_command(msg)
                        except Exception:
                            pass
                    with DB_LOCK, get_db() as conn:
                        conn.execute(
                            '''
                            INSERT INTO bot_state (key, value) VALUES ('last_update_id', ?)
                            ON CONFLICT(key) DO UPDATE SET value = excluded.value
                            ''',
                            (str(upd_id),),
                        )
                        conn.commit()
            else:
                time.sleep(3.0)
        except Exception:
            time.sleep(3.0)


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-AutoApply-Client, Paddle-Signature')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class FeedbackRequestHandler(BaseHTTPRequestHandler):
    server_version = 'AutoApplyFeedbackServer/1.0'

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        send_json(self, 200, {'ok': True})

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ('/autoapply-subscribe', '/autoapply-subscribe/'):
            query = urllib.parse.parse_qs(parsed.query)
            cfg = licensing_routes.load_paddle_runtime_config(STORAGE_DIR)
            html_bytes = licensing_routes.render_standalone_subscribe_html(cfg, query)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)
            return
        if parsed.path in ('/api/autoapply-license/brand-mark.png', '/api/autoapply-license/brand-mark.png/'):
            png_bytes = licensing_routes.BRAND_MARK_PNG_BYTES
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            self.send_header('Content-Length', str(len(png_bytes)))
            self.end_headers()
            self.wfile.write(png_bytes)
            return
        if parsed.path in ('/api/autoapply-license/config', '/api/autoapply-license/config/'):
            query = urllib.parse.parse_qs(parsed.query)
            cfg = licensing_routes.load_paddle_runtime_config(STORAGE_DIR)
            dev_id = (query.get('device_id') or [''])[0].strip()
            sup_code = (query.get('support_code') or [''])[0].strip()
            email = (query.get('email') or [''])[0].strip()
            key_q = (query.get('key') or [''])[0].strip()
            if dev_id or sup_code or email or key_q:
                with get_db() as conn:
                    sess = licensing_routes.create_checkout_session(
                        conn, DB_LOCK, device_id=dev_id, support_code=sup_code, customer_email=email
                    )
                    existing_sub = licensing_routes.find_existing_subscription_for_customer(
                        conn, DB_LOCK, email=email, license_key=key_q, device_id=dev_id
                    )
                    if existing_sub is None and dev_id and email:
                        licensing_routes.register_or_update_trial(
                            conn, DB_LOCK, device_id=dev_id, customer_email=email
                        )
                cfg['checkout_session_id'] = sess['session_id']
                if existing_sub is not None:
                    cfg['active_subscription'] = existing_sub
            send_json(self, 200, {'ok': True, **cfg})
            return
        if parsed.path in ('/api/autoapply-license/crypto-rates', '/api/autoapply-license/crypto-rates/'):
            rates = licensing_routes.get_daily_locked_crypto_rates(STORAGE_DIR)
            wallets = licensing_routes.load_crypto_wallets(STORAGE_DIR)
            send_json(self, 200, {'ok': True, 'crypto_wallets': wallets, 'crypto_rates': rates})
            return
        if parsed.path in ('/api/autoapply-license/device-status', '/api/autoapply-license/status'):
            query = urllib.parse.parse_qs(parsed.query)
            dev_id = (query.get('device_id') or ['mac_local_device'])[0].strip()
            sup_code = (query.get('support_code') or [''])[0].strip()
            sess_id = (query.get('session_id') or [''])[0].strip()
            email = (query.get('email') or [''])[0].strip()
            with get_db() as conn:
                res = licensing_routes.query_device_subscription_status(
                    conn, DB_LOCK, device_id=dev_id, support_code=sup_code, session_id=sess_id, email=email
                )
            send_json(self, 200, res)
            return
        if parsed.path in ('/api/autoapply-license/paddle-webhook', '/api/autoapply-license/health'):
            cfg = licensing_routes.load_paddle_runtime_config(STORAGE_DIR)
            send_json(self, 200, {
                'ok': True,
                'service': 'autoapply-license-server',
                'paddle_environment': cfg['paddle_environment'],
                'paddle_overlay_ready': cfg['paddle_overlay_ready'],
                'price_usd_monthly': cfg['price_usd_monthly'],
            })
            return
        if parsed.path in ('/appcast.json', '/api/autoapply-updates/appcast.json', '/api/autoapply-feedback/appcast.json'):
            appcast_file = STORAGE_DIR / 'appcast.json'
            if appcast_file.is_file():
                try:
                    data = json.loads(appcast_file.read_text(encoding='utf-8'))
                    send_json(self, 200, data)
                    return
                except Exception:
                    pass
            send_json(
                self,
                200,
                {
                    'channel': 'stable',
                    'latest_version': '0.1.0',
                    'minimum_required_version': '0.1.0',
                    'required': False,
                    'force_update': False,
                    'check_interval_hours': 24,
                    'download_url': 'https://turboapply.agency/job-searcher/download/AutoApply-latest.dmg',
                    'release_notes': 'AutoApply v0.1.0 — Universal macOS release.',
                },
            )
            return
        if parsed.path in ('/health', '/api/autoapply-feedback/health', '/api/autoapply-feedback'):
            stats = get_stats_summary()
            send_json(
                self,
                200,
                {
                    'ok': True,
                    'service': 'autoapply-feedback-server',
                    'bot_username': BOT_USERNAME,
                    'subscribe_url': f'https://t.me/{BOT_USERNAME}',
                    'total_feedback': stats['total_feedback'],
                    'bugs_count': stats['bugs_count'],
                    'improvements_count': stats['improvements_count'],
                    'active_subscribers': stats['active_subscribers'],
                },
            )
            return
        send_json(self, 404, {'ok': False, 'error': 'not_found'})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith('/api/autoapply-license/'):
            try:
                length = int(self.headers.get('Content-Length') or '0')
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_BODY_BYTES:
                send_json(self, 413, {'ok': False, 'error': 'invalid_content_length'})
                return
            raw_bytes = self.rfile.read(length)
            try:
                payload = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                send_json(self, 400, {'ok': False, 'error': 'invalid_json'})
                return
            if not isinstance(payload, dict):
                send_json(self, 400, {'ok': False, 'error': 'payload_must_be_object'})
                return

            if parsed.path == '/api/autoapply-license/create-session':
                with get_db() as conn:
                    res = licensing_routes.create_checkout_session(
                        conn,
                        DB_LOCK,
                        device_id=str(payload.get('device_id') or 'mac_local_device').strip(),
                        support_code=str(payload.get('support_code') or '').strip(),
                        customer_email=str(payload.get('email') or payload.get('customer_email') or '').strip(),
                    )
                send_json(self, 200, res)
                return

            if parsed.path == '/api/autoapply-license/paddle-webhook':
                sig_hdr = str(self.headers.get('Paddle-Signature') or self.headers.get('paddle-signature') or '')
                with get_db() as conn:
                    code, res = licensing_routes.handle_paddle_webhook(
                        conn,
                        DB_LOCK,
                        raw_body=raw_bytes,
                        signature_header=sig_hdr,
                        payload=payload,
                        send_telegram_fn=broadcast_text_to_subscribers,
                        storage_dir=STORAGE_DIR,
                    )
                send_json(self, code, res)
                return

            if parsed.path in ('/api/autoapply-license/checkout-complete', '/api/autoapply-license/register-checkout'):
                email_val = str(payload.get('email') or payload.get('customer_email') or '').strip()
                sup_code = str(payload.get('support_code') or '').strip()
                dev_id = str(payload.get('device_id') or 'mac_local_device').strip()
                sess_id = str(payload.get('session_id') or '').strip()
                tx_id = str(payload.get('transaction_id') or payload.get('reference') or '').strip()
                sub_id = str(payload.get('subscription_id') or '').strip()
                provider = str(payload.get('payment_method') or payload.get('payment_provider') or 'crypto').strip().lower()
                plan_val = str(payload.get('plan') or 'monthly').strip().lower()
                explicit_key = str(payload.get('license_key') or '').strip().upper()
                mode_val = str(payload.get('mode') or '').strip().lower()
                with get_db() as conn:
                    code, res = licensing_routes.process_checkout_claim(
                        conn,
                        DB_LOCK,
                        customer_email=email_val,
                        transaction_id=tx_id,
                        subscription_id=sub_id,
                        payment_provider=provider,
                        plan_id=plan_val,
                        device_id=dev_id,
                        support_code=sup_code,
                        session_id=sess_id,
                        explicit_key=explicit_key,
                        mode=mode_val,
                        storage_dir=STORAGE_DIR,
                        send_telegram_fn=broadcast_text_to_subscribers,
                    )
                send_json(self, code, res)
                return

            if parsed.path == '/api/autoapply-license/activate':
                with get_db() as conn:
                    code, res = licensing_routes.activate_license_on_server(
                        conn,
                        DB_LOCK,
                        license_key=str(payload.get('license_key') or ''),
                        device_id=str(payload.get('device_id') or 'mac_local_device').strip(),
                        support_code=str(payload.get('support_code') or '').strip(),
                        transfer_seat=bool(payload.get('transfer_seat', True)),
                    )
                send_json(self, code, res)
                return

            if parsed.path in (
                '/api/autoapply-license/pause-or-cancel',
                '/api/autoapply-license/pause',
                '/api/autoapply-license/cancel',
            ):
                default_act = 'cancel' if parsed.path.endswith('/cancel') else 'pause'
                act_val = str(payload.get('action') or default_act).strip().lower()
                try:
                    months_val = int(payload.get('pause_months') or 1)
                except (ValueError, TypeError):
                    months_val = 1
                with get_db() as conn:
                    code, res = licensing_routes.pause_or_cancel_subscription(
                        conn,
                        DB_LOCK,
                        action=act_val,
                        pause_months=months_val,
                        reason=str(payload.get('reason') or '').strip(),
                        customer_email=str(payload.get('email') or payload.get('customer_email') or '').strip(),
                        license_key=str(payload.get('license_key') or payload.get('key') or '').strip(),
                        subscription_id=str(payload.get('subscription_id') or payload.get('sub_id') or '').strip(),
                        device_id=str(payload.get('device_id') or 'mac_local_device').strip(),
                        plan_id=str(payload.get('plan') or '').strip().lower(),
                        storage_dir=STORAGE_DIR,
                        send_telegram_fn=broadcast_text_to_subscribers,
                    )
                send_json(self, code, res)
                return

            if parsed.path == '/api/autoapply-license/register-trial':
                with get_db() as conn:
                    res = licensing_routes.register_or_update_trial(
                        conn,
                        DB_LOCK,
                        device_id=str(payload.get('device_id') or '').strip(),
                        customer_email=str(payload.get('email') or payload.get('customer_email') or '').strip(),
                        trial_started_at=str(payload.get('trial_started_at') or '').strip(),
                        trial_expires_at=str(payload.get('trial_expires_at') or '').strip(),
                    )
                send_json(self, 200, res)
                return

            if parsed.path == '/api/autoapply-license/trigger-lifecycle-email':
                tpl = str(payload.get('template_type') or '').strip().lower()
                with get_db() as conn:
                    if tpl == 'run_scheduled':
                        res = licensing_routes.run_scheduled_lifecycle_emails(conn, DB_LOCK)
                    else:
                        res = licensing_routes.send_lifecycle_email(
                            template_type=tpl or 'purchase_thank_you',
                            recipient_email=str(payload.get('email') or payload.get('recipient_email') or '').strip(),
                            license_key=str(payload.get('license_key') or '').strip(),
                            plan_id=str(payload.get('plan') or 'monthly').strip().lower(),
                            payment_provider=str(payload.get('payment_provider') or 'paddle').strip().lower(),
                            transaction_id=str(payload.get('transaction_id') or '').strip(),
                            expires_at=str(payload.get('expires_at') or '').strip(),
                            pause_months=int(payload.get('pause_months') or 1),
                            pause_until_label=str(payload.get('pause_until_label') or '').strip(),
                            gateway_receipt_id=str(payload.get('gateway_receipt_id') or '').strip(),
                            gateway_provider=str(payload.get('gateway_provider') or '').strip(),
                            gateway_status=str(payload.get('gateway_status') or '').strip(),
                            free_cycle_added=bool(payload.get('free_cycle_added', False)),
                            force_send=bool(payload.get('force_send', False)),
                            conn=conn,
                            db_lock=DB_LOCK,
                        )
                send_json(self, 200, res)
                return

            send_json(self, 404, {'ok': False, 'error': 'unknown_license_endpoint'})
            return
        if parsed.path not in ('/api/autoapply-feedback', '/submit', '/'):
            send_json(self, 404, {'ok': False, 'error': 'not_found'})
            return

        try:
            length = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            send_json(self, 413, {'ok': False, 'error': 'invalid_content_length'})
            return

        try:
            raw_bytes = self.rfile.read(length)
            payload = json.loads(raw_bytes.decode('utf-8'))
        except Exception:
            send_json(self, 400, {'ok': False, 'error': 'invalid_json'})
            return

        if not isinstance(payload, dict):
            send_json(self, 400, {'ok': False, 'error': 'payload_must_be_object'})
            return

        raw_cls = str(payload.get('classification') or 'bug').strip().lower()
        classification = 'improvement' if 'improv' in raw_cls else 'bug'
        classification_label = 'Improvement' if classification == 'improvement' else 'Bug'
        comment = str(payload.get('comment') or payload.get('message') or '').strip()
        app_section = str(payload.get('app_section') or 'General').strip()[:120]
        browser_url = str(payload.get('browser_url') or '').strip()[:1000]
        browser_title = str(payload.get('browser_title') or '').strip()[:500]
        app_version = str(payload.get('app_version') or '').strip()[:80]
        device_id = str(payload.get('device_id') or '').strip()[:120]
        macos_version = str(payload.get('macos_version') or '').strip()[:80]
        submitted_at = str(payload.get('submitted_at') or payload.get('created_at') or utc_now_iso()).strip()[:80]
        received_at = utc_now_iso()

        raw_fb_id = str(payload.get('feedback_id') or payload.get('id') or '').strip()
        if raw_fb_id and re.fullmatch(r'[A-Za-z0-9_.-]{4,80}', raw_fb_id):
            feedback_id = raw_fb_id
        else:
            feedback_id = f"fb_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        raw_attachments = payload.get('attachments')
        if not isinstance(raw_attachments, list):
            raw_attachments = []

        if not comment and not raw_attachments:
            send_json(self, 400, {'ok': False, 'error': 'comment_or_attachment_required'})
            return

        sub_dir = STORAGE_DIR / 'submissions' / feedback_id
        att_dir = sub_dir / 'attachments'
        att_dir.mkdir(parents=True, exist_ok=True)

        saved_files: list[dict[str, Any]] = []
        for idx, item in enumerate(raw_attachments[:12], start=1):
            if not isinstance(item, dict):
                continue
            b64_data = str(item.get('data_base64') or item.get('base64') or '').strip()
            orig_name = str(item.get('filename') or item.get('name') or f'attachment_{idx}.bin').strip()
            safe_name = f'{idx:02d}_{sanitize_filename(orig_name)}'
            disk_path = att_dir / safe_name
            size_bytes = int(item.get('size_bytes') or 0)
            if b64_data:
                try:
                    decoded = base64.b64decode(b64_data, validate=False)
                    disk_path.write_bytes(decoded)
                    size_bytes = len(decoded)
                except Exception:
                    pass
            saved_files.append(
                {
                    'index': idx,
                    'name': str(item.get('name') or orig_name),
                    'filename': safe_name,
                    'kind': str(item.get('kind') or 'file'),
                    'media_type': str(item.get('media_type') or 'file'),
                    'size_bytes': size_bytes,
                    'disk_path': str(disk_path) if disk_path.is_file() else '',
                }
            )

        client_ip = str(self.headers.get('X-Real-IP') or self.client_address[0] or '')
        record = {
            'feedback_id': feedback_id,
            'classification': classification,
            'classification_label': classification_label,
            'comment': comment,
            'app_section': app_section,
            'browser_url': browser_url,
            'browser_title': browser_title,
            'app_version': app_version,
            'device_id': device_id,
            'macos_version': macos_version,
            'submitted_at': submitted_at,
            'received_at': received_at,
            'client_ip': client_ip,
            'attachments_count': len(saved_files),
            'attachments': saved_files,
        }

        (sub_dir / 'submission.json').write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )
        with (STORAGE_DIR / 'submissions.jsonl').open('a', encoding='utf-8') as ledger:
            ledger.write(json.dumps(record, ensure_ascii=False) + '\n')

        with DB_LOCK, get_db() as conn:
            conn.execute(
                '''
                INSERT OR REPLACE INTO feedback_submissions (
                    feedback_id, classification, classification_label, comment,
                    app_section, browser_url, browser_title, app_version,
                    device_id, macos_version, submitted_at, received_at,
                    client_ip, attachments_count, attachments_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    feedback_id,
                    classification,
                    classification_label,
                    comment,
                    app_section,
                    browser_url,
                    browser_title,
                    app_version,
                    device_id,
                    macos_version,
                    submitted_at,
                    received_at,
                    client_ip,
                    len(saved_files),
                    json.dumps(saved_files, ensure_ascii=False),
                    json.dumps(record, ensure_ascii=False),
                ),
            )
            conn.commit()

        delivery_results = broadcast_feedback(record, saved_files)
        notified_count = sum(1 for r in delivery_results if r.get('ok'))

        send_json(
            self,
            200,
            {
                'ok': True,
                'feedback_id': feedback_id,
                'stored': True,
                'attachments_stored': sum(1 for f in saved_files if f.get('disk_path')),
                'notified_subscribers': notified_count,
                'bot_username': BOT_USERNAME,
                'subscribe_url': f'https://t.me/{BOT_USERNAME}',
            },
        )


def lifecycle_email_scheduler_loop() -> None:
    while True:
        try:
            with get_db() as conn:
                licensing_routes.run_scheduled_lifecycle_emails(conn, DB_LOCK)
        except Exception:
            pass
        time.sleep(1800.0)


def main() -> None:
    init_db()
    poller = threading.Thread(target=telegram_poller_loop, name='telegram-poller', daemon=True)
    poller.start()
    lifecycle_sched = threading.Thread(target=lifecycle_email_scheduler_loop, name='lifecycle-emails', daemon=True)
    lifecycle_sched.start()
    server = ThreadingHTTPServer((HOST, PORT), FeedbackRequestHandler)
    server.serve_forever()


if __name__ == '__main__':
    main()
