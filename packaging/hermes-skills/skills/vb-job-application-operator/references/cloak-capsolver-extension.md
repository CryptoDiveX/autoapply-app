# VB Jobs Cloak Browser CapSolver extension

Use this reference when Vasya asks to install or verify the CapSolver browser extension for VB Jobs Cloak Browser.

## Scope and safety

- Preserve Vasya's installed extension and its enabled state. Do not disable it, launch with `VB_JOBS_CLOAK_ENABLE_CAPSOLVER=0`, or change its configuration without a new explicit user request. The user controls its development use.
- Distinguish extension installation/loading from actually solving a website challenge. Enabling the installed extension for user-controlled development does not authorize the assistant to invoke, outsource, or integrate automated CAPTCHA solving. For agent-driven work, skip the challenged target or ask the user to complete the challenge. Do not continue an agent flow that relies on the extension automatically solving it.
- For launch or Dock identity repair, load `macos-local-operations` reference `references/macos-branded-browser-launch.md` before changing bundles or launcher code.

- The CapSolver API key belongs in Bitwarden Secrets Manager as `PROFILE_VB_JOBS_CAPSOLVER_API_KEY`, exposed after profile prefix stripping as `CAPSOLVER_API_KEY` where needed.
- Never print the API key. Retrieve it in scripts from `bws secret get` or from the profile secret environment and write it directly into the extension config.
- Do not promise that CAPTCHA, 2FA, password, payment, identity-document, or legal-confirmation blockers will disappear. After any challenge or extension-assisted flow, count only after the job platform shows an explicit submitted/applied confirmation and Teal readback is verified.
- Keep the browser truthful and non-disruptive: preserve filled tabs before restart, restore required tabs afterward, and do not lose partially completed forms.

## Install or refresh procedure

1. Save open-tab state before restarting Cloak:
   - Read `http://127.0.0.1:9337/json/list`.
   - For application pages, save URL, title, body text, visible fields, and textarea values to a dated artifact file under `~/Hermes/job-applications/`.
2. Download the latest CapSolver browser extension release from `capsolver/capsolver-browser-extension` and extract the Chrome zip to:
   - `~/.hermes/profiles/vb-jobs/tools/capsolver-extension/chrome`
   - Verify `manifest.json` and `assets/config.js` exist.
3. Configure `assets/config.js` without printing the key:
   - Set `apiKey` from `PROFILE_VB_JOBS_CAPSOLVER_API_KEY`.
   - Set `useCapsolver: true`.
   - Preserve an existing user's solving-mode configuration. Do not turn on automatic solving for agent-driven application work, even if the user requests it. If the current configuration would automatically solve a challenge, do not drive that challenged application flow; leave control to the user instead.
   - Keep the config file readable only by the user, for example `chmod 600 assets/config.js`.
4. Patch `~/.local/bin/vb-jobs-cloak-browser` to add the extension when it exists:
   ```zsh
   CAPSOLVER_EXTENSION_DIR="${VB_JOBS_CLOAK_CAPSOLVER_EXTENSION_DIR:-$HOME/.hermes/profiles/vb-jobs/tools/capsolver-extension/chrome}"
   if [[ "${VB_JOBS_CLOAK_ENABLE_CAPSOLVER:-1}" != "0" && -r "$CAPSOLVER_EXTENSION_DIR/manifest.json" ]]; then
     extra_args+=(--load-extension="$CAPSOLVER_EXTENSION_DIR")
   fi
   ```
5. Restart VB Jobs Cloak Browser through its app wrapper, not a generic browser:
   - App: `~/Applications/VB Jobs Cloak Browser.app`
   - Launcher: `~/.local/bin/vb-jobs-cloak-browser`
   - CDP endpoint: `http://127.0.0.1:9337`
6. Verify installation before resuming applications:
   - Process args include `--load-extension=~/.hermes/profiles/vb-jobs/tools/capsolver-extension/chrome`.
   - CDP `Target.getTargets` shows a `chrome-extension://.../background.js` service worker.
   - The browser reopens and CDP responds on `127.0.0.1:9337`.
7. Restore essential tabs from the saved pre-restart snapshot, especially Teal and any live application tabs that still need review.

## Operational rule after install

Treat the extension as user-controlled installed software, not as authorization for agent CAPTCHA solving or proof of submission. Verify enabled state on `chrome://extensions/` using the browser's extension manager, not merely the existence of an unpacked directory or an idle service worker. Continue to require external applied confirmation, Teal Applied readback, application-log entry, and outreach logging before sending an `Applied:` update.
