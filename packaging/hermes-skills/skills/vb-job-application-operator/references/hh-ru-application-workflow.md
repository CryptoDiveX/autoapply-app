# hh.ru application workflow

Use this reference when Vasya asks to apply on hh.ru or says `Откликаться`.

## Procedure

1. Pause active autonomous application cron lanes before asking the user to log into hh.ru or LinkedIn. Resume only after the login-dependent task is complete or after the user explicitly asks to continue the overnight lanes.
2. Open hh.ru in the VB Jobs Cloak Browser and let Vasya log in. Never type the password or any verification code.
3. Verify the session by reading a logged-in page state, such as `Resume and profile`, `Applications`, the candidate name, or the resume/profile page. Do not rely on the user message alone if browser readback is available.
4. Inspect the hh.ru resume card before applying. If hh.ru blocks applications because the selected resume is not visible, ask before changing visibility. Once Vasya authorizes visibility, verify the resume page says `Видно всем работодателям, зарегистрированным на hh.ru` before continuing.
5. Search for suitable remote product, project, AI, automation, platform, or technical product roles. Apply company-deduping across the existing application log and hh.ru batch artifacts.
6. For each target, save an artifact folder with the vacancy URL, search card, pre-submit readback, submitted answers, and post-submit readback.
7. Use the existing hh.ru resume/profile unless hh.ru explicitly asks for another document upload. Do not upload identity documents or verification selfies.
8. Match response language to the posting language. Russian posting gets Russian cover or intro text. English posting gets English cover or intro text. If the posting is mixed, use the employer's question language for each answer. Always submit a short cover or intro message when hh.ru exposes a cover-letter textarea or any free-text response field. Do not skip the cover text on fast отклики.
9. After a verified hh.ru отклик, message the employer through hh.ru chat or the negotiations page when a writable chat box is available. If hh.ru opens the chat but does not expose a writable box yet, save that as the employer-message blocker and continue.
10. Answer salary in the unit requested. If hh.ru asks after-tax salary expectations, answer a net figure and mark flexibility, for example a concise net monthly expectation. Do not convert into unrelated periods.
10. For portfolio/project questions, prefer public links that are already canon-supported, such as TurboApply Agency and LinkedIn, plus a concise true example of AI workflow work. Do not invent GitHub repos or public demos.
11. Submit only when the page accepts the filled values and no password, 2FA, payment, prohibited CAPTCHA bypass, identity-document, or unsupported legal claim is required.
12. Verify success from the post-submit vacancy page or response state, such as `You applied`, `Вы откликнулись`, or equivalent. Count only after this readback and after logging a submitted section in the applications log.

## Browser/CDP fallback

When Playwright `connect_over_cdp` hangs after the WebSocket connects, raw CDP is a reliable fallback for hh.ru because the logged-in session is already in the Cloak profile.

Minimal pattern:

```python
import json, urllib.request, websocket, itertools
arr = json.load(urllib.request.urlopen('http://127.0.0.1:9337/json/list'))
page = next(t for t in arr if t.get('type') == 'page' and 'hh.ru' in t.get('url', ''))
ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=10, suppress_origin=True)
ctr = itertools.count(1)
def cdp(method, params=None):
    i = next(ctr)
    ws.send(json.dumps({'id': i, 'method': method, 'params': params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get('id') == i:
            return msg
```

Use `Runtime.evaluate` for readbacks and form fills. Use the native textarea value setter plus `InputEvent` and `change` events, then re-read the values before clicking submit. If the first fill appears in the DOM value but the visible page still shows `Type here`, re-fill with the prototype setter and verify the visible character count or post-click state before concluding failure.

## Pitfalls

- Do not treat hh.ru resume visibility as a harmless setting. Changing it exposes the resume to registered employers, so ask before changing it.
- Do not count a response from the button click alone. hh.ru can keep the user on the response page after a failed or blocked click; count only after the vacancy page or response state says the user applied.
- Audit cover delivery independently of the applied state. If saved submission evidence says `already_applied` before cover entry and the employer message says `chat_open_no_box`, a local cover file does not prove delivery. Mark `hh_cover_repair_needed`, remove clean campaign credit, and preserve the real external response history. Before attempting repair, recheck the live vacancy and employer outcome; archive an out-of-scope hybrid target or a rejected response instead of reapplying or sending unwanted repair outreach.
- If a post-click hh.ru response page still shows `Send application` plus resume-visibility text such as `Чтобы откликнуться на эту вакансию, поменяйте видимость резюме`, classify it as a resume-visibility blocker, stop that target, and add the vacancy/company to the same-run no-retry list instead of treating it as generic clicked-unverified.
- Do not force English cover text into Russian postings. Russian job posters should receive Russian intro/cover text, because mismatched language weakens the response and violates Vasya's stated preference.
- Do not make raw CDP failures into a permanent browser-blocker rule. If Playwright stalls, use raw WebSocket CDP with `suppress_origin=True`; this avoids Chromium origin rejection and preserves the logged-in session.