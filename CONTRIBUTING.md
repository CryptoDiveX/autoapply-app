# Contributing to AutoApply (`CryptoDiveX/autoapply-app`)

## Golden Rules

1. **Never commit secrets or credentials.** API keys (`sk-or-*`, `CAP-*`), OAuth tokens, `.env` files, SQLite databases (`*.db`), and browser profile directories must never be committed.
2. **Preserve host `~/.hermes` isolation.** Never read or write `~/.hermes` from application code or installer/uninstaller scripts. All application data belongs under `~/Library/Application Support/AutoApply`.
3. **Keep front-end interactions instantaneous (`0ms`).** Any SwiftUI toggle, chip selection, or text edit in `apps/macos/AutoApply/Executable/main.swift` must update `@Published` state synchronously on the main thread and dispatch persistence asynchronously via `WorkspaceStore.backgroundBridgeQueue` with `preserveLocalEdits: true`.
4. **Keep [`CryptoDiveX/autoapply-extension`](https://github.com/CryptoDiveX/autoapply-extension) and [`CryptoDiveX/autoapply-handoff`](https://github.com/CryptoDiveX/autoapply-handoff) synchronized.** Any change to `packaging/extensions/` must be mirrored in `CryptoDiveX/autoapply-extension`, and architectural/operational changes must be documented in `CryptoDiveX/autoapply-handoff`.

## Pre-Commit Verification Checklist

Before pushing any change to `main`:

```bash
# 1. Build universal app bundle, pkg, and dmg
bash packaging/build_macos_installer.sh

# 2. Run the full 68-test suite
pytest -q

# 3. Verify no secret patterns are staged
git diff --cached | grep -E "sk-or-v1-|CAP-[A-Za-z0-9]{16,}" && exit 1 || true
```
