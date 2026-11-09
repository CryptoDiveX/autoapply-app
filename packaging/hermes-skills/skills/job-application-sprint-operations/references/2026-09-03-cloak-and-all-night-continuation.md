# 2026-09-03 Cloak and all-night continuation notes

Session-specific reference for future VB Jobs sprint operators.

## Cloak update outcome

1. The VB Jobs Cloak profile was moved from the no-key macOS build to the latest key-enabled CloakBrowser build.
2. The key was retrieved from a CloakBrowser email without printing it, validated, stored in Bitwarden as `PROFILE_VB_JOBS_CLOAKBROWSER_LICENSE_KEY`, and copied to the profile Cloak cache as `license.key` with protected permissions.
3. The verified running endpoint reported `Chrome/151.0.7922.108` on `http://127.0.0.1:9337`.
4. The launcher was hardened to resolve the managed CloakBrowser binary dynamically, load the cache key, and pass third-party cookie support where available.
5. Do not claim a package update means the browser binary changed. Verify both `cloakbrowser info` and CDP `/json/version`.

## CAPTCHA handling lesson

1. Cloak is a prevention and risk-score passage layer, not a visible challenge solver.
2. Latest licensed Cloak with the persistent profile passed the Enode Ashby invisible reCAPTCHA flow after the form was refilled and live field values were verified.
3. Do not use third-party CAPTCHA solving or challenge outsourcing for job applications.
4. If a visible challenge appears, preserve the filled page, ask Vasya to complete it, then re-read all field values before submit.

## Enode recovery lesson

1. After upgrading Cloak, Enode Product Lead - Experience was retried in latest Cloak and submitted successfully.
2. Verification required all three: Ashby success page, Gmail confirmation, and Teal readback as Applied.
3. After success, the old blocker in `applications-log.md` and Teal needed to be replaced with the submitted outcome.
4. Completed application tabs were closed after Teal verification.

## EU wording correction

Use this wording class for EU-focused remote roles:

- Alex works EU-compatible hours from Georgia.
- Alex can travel to the EU visa-free for short business visits as a Canadian citizen.
- If physical work in the EU is needed, sponsorship or relevant work authorization would be needed.
- Do not claim he is currently EU-based.
- Do not claim current EU work authorization.
- For required binary questions asking whether he is currently located in the EU and has right to work in the EU, the truthful radio answer is `No`; proceed only if that is safe, and put the nuance in an available cover letter or free-text field.

## All-night run pattern

1. For `apply all night`, create a bounded recurring cron with local delivery, such as every 30 minutes for the night, then run one tick immediately.
2. Put all hard rules in the cron prompt: Sonnet 5 copywriting, no em dashes, no candidate-facing gap language, latest Cloak only, live field-value validation before submit, Teal readback, and safe CAPTCHA handling.
3. Each tick should produce either one submitted application or one real blocker. Avoid broad low-quality bulk applying.
4. If an old sprint cron has completed, create a new cron instead of attempting to update it back to active.
5. Keep Telegram delivery quiet unless Vasya asks for status updates.
