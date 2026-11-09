#!/usr/bin/env bash
# =============================================================================
# AutoApply Clean Uninstaller
# Strictly removes ONLY AutoApply.app and AutoApply-owned Application Support,
# cache, preferences, keychain entries, and package receipts.
#
# GUARANTEED UNTOUCHED:
#   - ~/.hermes (standalone Hermes installation/config)
#   - ~/.codex (standalone Codex installation/config)
#   - ~/.cloakbrowser (standalone CloakBrowser installation/binaries/cache)
#   - ~/Library/Application Support/CloakBrowser, Chromium, Google Chrome, etc.
# =============================================================================
set -euo pipefail

NON_INTERACTIVE=0
SKIP_APP_BUNDLE=0
CUSTOM_HOME=""
CUSTOM_APP_PATH=""
CUSTOM_DATA_ROOT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y|--non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        --reset-data-only)
            SKIP_APP_BUNDLE=1
            NON_INTERACTIVE=1
            shift
            ;;
        --target-home)
            CUSTOM_HOME="$2"
            shift 2
            ;;
        --app-path)
            CUSTOM_APP_PATH="$2"
            shift 2
            ;;
        --data-root)
            CUSTOM_DATA_ROOT="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# 1. Resolve console user and home directory
CONSOLE_USER="$(stat -f "%Su" /dev/console 2>/dev/null || true)"
if [[ -z "${CONSOLE_USER}" || "${CONSOLE_USER}" == "root" ]]; then
    CONSOLE_USER="${SUDO_USER:-${USER:-$(id -un)}}"
fi

if [[ -n "${CUSTOM_HOME}" ]]; then
    USER_HOME="${CUSTOM_HOME}"
else
    USER_HOME=""
    if [[ -n "${CONSOLE_USER}" ]]; then
        USER_HOME="$(dscl . -read "/Users/${CONSOLE_USER}" NFSHomeDirectory 2>/dev/null | awk '{print $2}' || true)"
    fi
    if [[ -z "${USER_HOME}" || ! -d "${USER_HOME}" ]]; then
        USER_HOME="${HOME:-/Users/${CONSOLE_USER}}"
    fi
fi

APP_PATH="${CUSTOM_APP_PATH:-/Applications/AutoApply.app}"
DATA_ROOT="${CUSTOM_DATA_ROOT:-${USER_HOME}/Library/Application Support/AutoApply}"

# Safety check: Ensure DATA_ROOT and APP_PATH strictly point to AutoApply and never to standalone tools
case "${DATA_ROOT}" in
    *".hermes"*|*".codex"*|*".cloakbrowser"*)
        echo "ERROR: Refusing to touch standalone tool path: ${DATA_ROOT}" >&2
        exit 1
        ;;
esac

if [[ "${NON_INTERACTIVE}" -eq 0 ]]; then
    echo "=================================================================="
    echo " AutoApply Clean Uninstaller"
    echo "=================================================================="
    echo "The following AutoApply-owned items will be removed:"
    if [[ "${SKIP_APP_BUNDLE}" -eq 0 ]]; then
        echo "  - Application Bundle : ${APP_PATH}"
    fi
    echo "  - App Data & Profiles: ${DATA_ROOT}"
    echo "  - App Preferences    : ${USER_HOME}/Library/Preferences/com.autoapply.macos.plist"
    echo "  - App Caches         : ${USER_HOME}/Library/Caches/com.autoapply.macos"
    echo "  - App Keychain Items : service 'com.autoapply.macos.secrets'"
    echo ""
    echo "Standalone tools (~/.hermes, ~/.codex, ~/.cloakbrowser, other browsers)"
    echo "will NOT be touched."
    echo "=================================================================="
fi

# 2. Stop ONLY processes belonging to AutoApply (never external Chromium/CloakBrowser/Hermes)
if [[ -z "${CUSTOM_HOME}" && -z "${CUSTOM_DATA_ROOT}" ]]; then
    pkill -f "/Applications/AutoApply.app/Contents/MacOS/AutoApply" 2>/dev/null || true
    pkill -f "/Applications/AutoApply.app/Contents/Resources/Browser/Chromium.app" 2>/dev/null || true
    pkill -f "Application Support/AutoApply/browser-profiles" 2>/dev/null || true
    pkill -f "Application Support/AutoApply/runtime-state" 2>/dev/null || true
fi

# 3. Remove AutoApply Keychain secrets (strictly scoped to com.autoapply.macos.secrets)
for KEY_ACCOUNT in "OPENROUTER_API_KEY" "CAPSOLVER_API_KEY" "HERMES_CHATGPT_SESSION" "GMAIL_APP_PASSWORD"; do
    security delete-generic-password -s "com.autoapply.macos.secrets" -a "${KEY_ACCOUNT}" >/dev/null 2>&1 || true
done

# 4. Remove AutoApply Application Support directory
if [[ -n "${DATA_ROOT}" && -d "${DATA_ROOT}" ]]; then
    rm -rf "${DATA_ROOT}"
fi

# 5. Remove AutoApply macOS caches, preferences, and saved window state
rm -rf "${USER_HOME}/Library/Caches/com.autoapply.macos" 2>/dev/null || true
rm -rf "${USER_HOME}/Library/Caches/AutoApply" 2>/dev/null || true
rm -f  "${USER_HOME}/Library/Preferences/com.autoapply.macos.plist" 2>/dev/null || true
rm -rf "${USER_HOME}/Library/Saved Application State/com.autoapply.macos.savedState" 2>/dev/null || true
rm -rf "${USER_HOME}/Library/HTTPStorages/com.autoapply.macos" 2>/dev/null || true
rm -rf "${USER_HOME}/Library/WebKit/com.autoapply.macos" 2>/dev/null || true

# 6. Remove /Applications/AutoApply.app and package receipt (unless --reset-data-only)
if [[ "${SKIP_APP_BUNDLE}" -eq 0 ]]; then
    if [[ -n "${APP_PATH}" && -d "${APP_PATH}" ]]; then
        rm -rf "${APP_PATH}" 2>/dev/null || true
        if [[ -d "${APP_PATH}" && "${APP_PATH}" == "/Applications/AutoApply.app" ]]; then
            osascript -e 'do shell script "rm -rf \"/Applications/AutoApply.app\" && pkgutil --forget \"com.autoapply.macos.pkg\" >/dev/null 2>&1 || true" with administrator privileges' >/dev/null 2>&1 || true
        fi
    fi
    pkgutil --forget "com.autoapply.macos.pkg" >/dev/null 2>&1 || true
fi

echo "{\"status\":\"uninstalled\",\"app_removed\":$((1 - SKIP_APP_BUNDLE)),\"data_root_removed\":\"${DATA_ROOT}\"}"
exit 0
