#!/usr/bin/env python3
"""Notify Telegram when new submitted hh.ru rows appear.

Uses the local bulk-with-cover-results JSONL as source. It sends a short
Telegram message for each newly seen submitted row and records state locally.
"""
import json
import os
import pathlib
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path.home() / ('Hermes/job-applications')
RESULTS = ROOT / 'hh-ru-bulk-20261011' / 'bulk-with-cover-results.jsonl'
STATE = ROOT / 'outreach-database' / 'telegram-submission-notifier-state.json'
DB = ROOT / 'outreach-database' / 'outreach.sqlite3'
CHAT_ID = '402189509'


def load_token():
    for name in ('TELEGRAM_BOT_TOKEN', 'PROFILE_VB_JOBS_TELEGRAM_BOT_TOKEN'):
        if os.environ.get(name):
            return os.environ[name]
    envp = pathlib.Path.home() / ('.hermes/profiles/vb-jobs/.env')
    if envp.exists():
        for line in envp.read_text(errors='ignore').splitlines():
            if line.startswith('TELEGRAM_BOT_TOKEN='):
                return line.split('=', 1)[1].strip().strip('"\'')
    return None


def rows():
    out = []
    if not RESULTS.exists():
        return out
    for line in RESULTS.read_text(encoding='utf-8', errors='ignore').splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get('type') == 'submitted':
            out.append(r)
    return out


def key_for(r):
    return '|'.join(str(r.get(k) or '') for k in ('company', 'title', 'url', 'applied_at'))


def send(token, text):
    data = urllib.parse.urlencode({
        'chat_id': CHAT_ID,
        'text': text,
        'disable_web_page_preview': 'true',
    }).encode()
    req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=data, method='POST')
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def main():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {'seen': []}
    seen = set(state.get('seen') or [])
    token = load_token()
    sent = []
    errors = []
    for r in rows():
        k = key_for(r)
        if k in seen:
            continue
        company = r.get('company') or 'Unknown company'
        title = r.get('title') or 'Unknown role'
        platform = 'hh.ru'
        follow = []
        chat = r.get('chat_status')
        if chat == 'sent_clicked':
            follow.append('hh.ru follow-up sent')
        elif chat:
            follow.append(f'hh.ru follow-up attempted: {chat}')
        else:
            follow.append('follow-up pending')
        text = f"Applied: {title} at {company} via {platform}. Follow-up: {', '.join(follow)}."
        if token:
            try:
                send(token, text)
                sent.append(text)
            except Exception as e:
                errors.append({'text': text, 'error': repr(e)})
        else:
            errors.append({'text': text, 'error': 'missing Telegram bot token'})
        seen.add(k)
        time.sleep(0.4)
    state['seen'] = sorted(seen)
    state['last_run_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    state['last_sent'] = sent[-20:]
    state['last_errors'] = errors[-20:]
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'new_notifications': len(sent), 'errors': errors, 'state': str(STATE)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
