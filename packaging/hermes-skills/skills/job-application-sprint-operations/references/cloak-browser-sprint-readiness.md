# Cloak Browser sprint readiness

Use this before resuming a high-volume VB Jobs browser sprint, after CAPTCHA-heavy runs, or after a user asks whether Cloak is up to date.

## Readiness checks

Preserve the user's installed CapSolver extension and enabled state. Do not turn it off as a browser-recovery shortcut. Loading user-controlled development software is distinct from invoking it to solve a website challenge; do not use or outsource CAPTCHA solving in agent-driven applications. If that configuration would automatically solve a challenge, skip the challenged flow or leave it for the user. A current explicit visible-mode request supersedes the headless recipe below. For Dock/app identity repair, load `macos-local-operations` reference `references/macos-branded-browser-launch.md`.

1. Confirm the dedicated endpoint responds: `http://127.0.0.1:9337/json/version`.
2. Confirm the running command uses the VB Jobs profile directory: `~/Library/Application Support/Hermes/VBJobsCloakBrowser`. When asserting there is one browser owner, distinguish the browser-root command from child processes carrying `--type=`. Renderer and utility children can repeat the same profile and debugging arguments, so counting every matching command can falsely report competing browsers. Preserve a healthy root process and repair only the read-only verifier; do not restart or replay application actions to fix that count.
3. Confirm launch flags include the stable fingerprint seed, macOS fingerprint platform, `Asia/Tbilisi` timezone, and `en-CA` language.
4. Confirm tab state is clean before new submissions. Close stale job-board tabs, blocked CAPTCHA frames, and old candidate pages unless they are needed for a specific recovery.
5. Confirm the package version with the profile venv: `python -m pip show cloakbrowser`.
6. Confirm binary and license state with: `CLOAKBROWSER_CACHE_DIR=<profile-cache> python -m cloakbrowser info`.
7. Run `python -m cloakbrowser update` after package upgrades. If it reports the no-key free binary is already up to date, do not claim the newest licensed binary is installed.

## Version interpretation

- The Python wrapper can be latest while the cached browser binary is not the newest available licensed build.
- `License: Free (no key)` means the profile is limited to the free no-key binary available to that install state.
- To use the newest free or paid licensed build, Vasya must provide or authorize a CloakBrowser license key or interactive login. Do not invent a key, do not enter passwords or 2FA, and do not print a key.
- If the free-key GitHub link expires, kill the waiting `cloakbrowser login` process, start it again in a PTY, press Enter once to generate a fresh GitHub URL, and open the new URL in the existing VB Jobs Cloak session. If GitHub reports the key was already emailed, search Gmail for recent `CloakBrowser` messages and extract only the key value into the login flow, Bitwarden, or the cache file. Never print the key.
- Store the VB Jobs key in Bitwarden as `PROFILE_VB_JOBS_CLOAKBROWSER_LICENSE_KEY`. For the dedicated launcher, also keep a protected operational copy at `~/.hermes/profiles/vb-jobs/tools/cloakbrowser-cache/license.key` with mode `0600`, because the CloakBrowser wrapper resolves keys from the cache directory.
- After key installation, run both stable and preview install checks with the profile venv and cache. Preview may fall back to stable on macOS arm64. Verify actual output, not assumptions.
- Building the public CloakBrowser wrapper from GitHub does not compile a fresh patched Chromium binary. The wrapper still calls `ensure_binary()` and downloads an official binary. Verify the actual active binary through `cloakbrowser info` and CDP `/json/version`, not by assuming GitHub `main` equals newest browser.
- On macOS arm64 in the no-key path, do not claim Linux or Windows release numbers as installed. Check the platform map and public release assets for `cloakbrowser-darwin-arm64` before reporting an available binary.
- The VB Jobs launcher should resolve the managed CloakBrowser binary dynamically rather than hard-pinning a stale cached Chromium path.

## Latest-binary update commands

Use the profile venv and cache explicitly:

```bash
VENV=~/.hermes/profiles/vb-jobs/tools/cloakbrowser-venv/bin/python
CACHE=~/.hermes/profiles/vb-jobs/tools/cloakbrowser-cache
$VENV -m pip install --upgrade cloakbrowser
CLOAKBROWSER_CACHE_DIR="$CACHE" $VENV -m cloakbrowser install
CLOAKBROWSER_CACHE_DIR="$CACHE" CLOAKBROWSER_RELEASE_CHANNEL=preview $VENV -m cloakbrowser install || true
CLOAKBROWSER_CACHE_DIR="$CACHE" $VENV -m cloakbrowser info
curl -sS --max-time 5 http://127.0.0.1:9337/json/version
```

Restart the dedicated wrapper after installing the new binary and verify the process command shows the expected cached `chromium-...` path.

## CAPTCHA handling

CloakBrowser reduces CAPTCHA triggers by presenting a more realistic browser. It does not solve visible challenges. Avoidance and normal risk-score passage are allowed: headed persistent profile, warm cookies, stable IP and locale, realistic input, clean tabs, latest licensed Cloak binary, and third-party cookie support for embedded flows where available. The Enode Ashby recovery showed that the latest licensed Cloak build could pass an invisible reCAPTCHA flow that the older no-key build had blocked, after the form was refilled and live field values were verified.

Third-party CAPTCHA-solving services and challenge outsourcing exist, but do not integrate or recommend them for job applications because they can violate ATS and job-board rules. Preserve the filled page, use allowed normal-browser interaction, and if a visible challenge cannot be completed safely, pause and ask Vasya to solve it. Continue only after verifying the page state and re-reading every submitted field value.

## Endpoint and visible-launch decision procedure

1. Read `/json/version` and `/json/list`, and inspect process names before saying Cloak is unavailable. Distinguish a stopped process, a temporarily refused endpoint and an empty tab list; none proves an authentication problem or the cause of a shutdown.
2. If the browser is alive, use bounded read-only retry or root-session recovery before considering a restart. An empty list alone is not grounds to quit/relaunch. Never restart during another worker's submit.
3. If Vasya explicitly asks to open Cloak and the process is stopped, launch the confirmed dedicated app with `open -a '~/Applications/VB Jobs Cloak Browser.app'`. Do not substitute another browser or change the persistent profile. This request authorizes the visible launch only; continue later automation in background mode unless full foreground use is separately authorized.
4. Boundedly check `/json/version`, `/json/list` and the branded running process after launch. Use `computer_use(action='capture', app='VB Jobs Cloak Browser', mode='ax')` to verify a real window when claiming it is visibly open. Stop for any permission/password/security prompt instead of clicking through.
5. Re-enumerate target IDs after endpoint recovery. Treat a missing previously tracked automation target as already closed, not evidence that a verified send failed; retry only unfinished logging, never repeat the external send.
6. During routine cleanup, close only dead/completed automation targets. Preserve the browser process, user windows and a neutral page if needed to avoid closing the last window, because recurring work depends on that persistent session. Compare final page inventories by exact target ID and URL, not list order, because activating or navigating a target can reorder CDP enumeration. Recover an order-only assertion with a sorted read-only identity comparison; never repeat an application, invitation, tracker update or cleanup action to make ordering match.

## Headless recovery without taking over the desktop

Use this only when continued application work is authorized, no dedicated Cloak process or live owner is using the profile, and no current instruction prohibits restarting it. A request to continue does not authorize a visible browser launch, and this recipe does not override the immediate stop requirement after a focus-hijacking complaint.

1. Read the confirmed launcher to verify its extra-argument mechanism, profile path and debug port. Check the endpoint and process list before launching; never start a second process on the same persistent profile. Distinguish a real latest user prohibition from a parent-authored healthy-browser no-restart precaution. Do not turn the latter into a permanent stopped-browser blocker while continued work remains authorized. If repeated ticks are research-only because the dedicated browser has stopped, pause future owner ticks, verify its execution is complete and the profile has no matching process, perform this headless-only recovery, refresh target IDs/authentication and then resume one owner. Never apply this exception to a current explicit stop or focus-hijacking complaint.
2. Start the dedicated wrapper as a tracked background process, without `open`, app activation or GUI shortcuts:

   ```bash
   VB_JOBS_CLOAK_EXTRA_ARGS='--headless=new --no-startup-window' \
   ~/.local/bin/vb-jobs-cloak-browser about:blank
   ```

   Preserve the user's extension state and configuration; do not invoke automated challenge solving. For an explicitly authorized overnight or continuous campaign, start this browser as a tracked background daemon with persist_on_release=true so ending the dispatch session does not intentionally terminate it. This does not survive host shutdown or authorize another profile process. Stop for any permission, password or security prompt; a successful process launch does not establish authenticated ATS or Teal access.
3. Verify `/json/version` responds and the actual process command contains the dedicated profile plus `--headless=new` and `--no-startup-window`. Record the background process handle. Do not claim the browser is visibly open.
4. Enumerate page targets. With no startup window, an empty page list can be expected: inspect root `Target.getTargets` for reusable pages, then create a single needed page through the browser WebSocket using `Target.createTarget` with `background: true`. Use a small request ID and the observed root WebSocket URL, not a guessed target ID.
5. Verify the resulting page and retained authentication, then hand exclusive CDP ownership to the submission worker. Re-enumerate IDs instead of reusing pre-shutdown values. If this route fails, preserve the blocker and continue safe read-only work rather than falling back to a foreground launch.

## Background CDP recovery

Before allocating a new background target, check that its immutable intent/readback filenames are unused. A helper that creates the target before asserting artifact uniqueness can leave a duplicate page when preparation is replayed. On an immutable-file collision, inspect the saved target receipt and current page inventory, recover only the original read-only stage under a new audit prefix, and close only the exact accidentally allocated owned page. Never repeat candidate entry, upload or Submit to repair local evidence.

1. Use small incrementing signed-32-bit request IDs; timestamp-sized IDs can be ignored even when the WebSocket connected. Test `id: 1` before blaming or restarting a responsive browser.
2. Use raw WebSocket CDP with `suppress_origin=True` when Origin rejection or Playwright attachment prevents use of an otherwise responsive persistent session. Enumerate `/json/list` for current target WebSocket URLs. Check installed transports before installing dependencies: the profile Cloak venv may have `websockets` without `websocket-client`. With that package, `from websockets.sync.client import connect` and `connect(observed_url, origin=None, open_timeout=15, max_size=20000000)` provide the same no-Origin background transport. Use a bounded `recv(timeout=35)` and matching small incrementing request IDs. Invoke that venv with `env -u PYTHONPATH -u PYTHONHOME` so Hermes runtime modules do not leak into it; missing `import websocket` alone is not a browser blocker. For an existing read-only audit script that imports both transport packages, first probe its intended interpreter with `python -c 'import websocket, websockets'`. If dependencies are absent and `uv` is available, run `uv run --with websocket-client --with websockets python /absolute/path/to/audit-script.py <arguments>` to provide an isolated, tested dependency environment without altering the shared browser venv. Rerun only the audit against the original external IDs; do not invoke a sender or restart Cloak to repair a Python import.
Run existing local CDP helpers through their intended terminal interpreter rather than importing them into the execute_code sandbox. The sandbox can read the same script files while lacking the terminal-only websocket dependencies, so its ModuleNotFoundError is not evidence of a browser outage. Recover only the unfinished read-only helper under the documented terminal/dependency path, without restarting Cloak or replaying candidate actions.

Treat dependency folders under the profile's cache/scratch as disposable. Old helpers can retain a sys.path entry for ws-deps after idle cleanup has removed that directory. Check its existence and test imports before initialization; when absent, use the isolated uv dependency recipe above rather than assuming the saved path still works or diagnosing a browser failure. Do not invoke an app-bundled Hermes interpreter as bare Python without its required runtime environment. Preserve an initialization failure and recover only the unexecuted helper stage under a new evidence prefix when needed.

3. If page transport stalls, test `Browser.getVersion` on the browser-root socket, then `Target.attachToTarget` with `flatten: true`; send page requests with the returned `sessionId`. If an empty `/json/list` accompanies a stalled create request, inspect `Target.getTargets` for an idle unattached page and attach/navigate it before creating more targets.
4. Keep `DOM.getDocument`, `DOM.querySelector` and `DOM.setFileInputFiles` on the same live session because frontend node IDs are session-scoped. Before adapting a saved CDP helper, inspect its actual method names and signatures: local wrappers may expose `cmd` rather than `call`. If a rendering check fails after a verified Teal Notes append, recover only read-only navigation and paragraph verification under new immutable evidence filenames. Never replay the successful append or candidate action to repair a helper-method mismatch.
5. In an already headless session, use `Emulation.setFocusEmulationEnabled` before native typing if DOM focus stalls. Select the exact field contents with `setSelectionRange`, then use `Input.insertText` and read back; do not assume Meta+A selected the field or allow concatenated answers. Email inputs reject `setSelectionRange` with InvalidStateError: require a freshly verified empty email field before inserting, or use a separately verified native select-all/clear path for a nonempty value. Do not rerun an entire staging or sender script to repair one failed field.
6. Before trusting Ashby React `memoizedProps`, resolve the current fiber branch through the root's `stateNode.current` and use its alternate if needed. Compare current `fieldEntry.fieldValue`, normalized country and upload storage/filename against exact approved answers and DOM; never mutate React internals to suppress validation.
7. If a textarea visibly contains the answer while validation still says required, commit the answer through native Backspace and `Input.insertText` in one persistent background session, then recheck all fields before one bounded normal submit retry. A storage upload or reachable confirmation URL alone is not submission proof.
8. On Lever, let resume parsing finish before final field QA because it can overwrite normalized current location from the approved Canada-first PDF. Inspect the live location widget listener before recovery: an input event alone may show an empty dropdown while its search is debounced from keydown. Use the normal observed location suggestion and its selection event, then compare visible location and hidden selectedLocation together. Current selectedLocation can contain only name and opaque ID instead of an address/country object; validate the observed exact suggestion rather than assuming a schema or fabricating a country payload.
9. Before treating a CAPTCHA iframe as a visible challenge, inspect computed visibility and ancestors or use checkVisibility with checkVisibilityCSS and checkOpacity. Invisible fixed-size hCaptcha enclave frames can occupy the entire viewport while visibility is hidden. Do not click or interact with an actual visible challenge. Continue only through the normal submit path when the challenge remains invisible, and verify the resulting native response and confirmation.
10. Require ancestor-aware visibility and an unobstructed hit test before candidate entry on animated full-page loaders. A Next.js application can expose all real form controls and its submit handler while a progress overlay covers them. Bound the same-target wait and save the screenshot. Only when current user authorization explicitly permits visible application-tab activation, activate that exact retained target and recheck normal loader completion. Never remove the overlay, enter covered controls, restart the browser or infer foreground permission from DOM readiness. After success collapses a long form, scroll that same target to the actual confirmation before its screenshot, because the retained lower scroll position can show only the footer. Recover only readback, never Submit.

## After restart verification

1. Restart the wrapper only after preserving or intentionally closing needed tabs.
2. Verify `/json/version` returns the expected browser.
3. Verify `/json/list` shows a clean or intentionally retained tab set.
4. Verify `cloakbrowser info` has required optional modules available where relevant, including Playwright and any installed helper modules.
5. Record the result in the sprint outcome if the sprint depends on Cloak state.
