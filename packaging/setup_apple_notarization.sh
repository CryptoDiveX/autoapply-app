#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# AutoApply macOS — Apple Developer ID & Notarization Setup Helper
#
# Subcommands:
#   1. ./packaging/setup_apple_notarization.sh generate-csr
#      Generates private key in login Keychain + ~/Desktop/AutoApply-DeveloperID.certSigningRequest
#       ready to upload to https://developer.apple.com/account/resources/certificates/add
#
#   2. ./packaging/setup_apple_notarization.sh import-and-notarize <apple-id> <team-id> <app-specific-password>
#      Imports downloaded developerID_application.cer + developerID_installer.cer from ~/Downloads,
#      stores the notarytool profile "autoapply-notary" in Keychain, and builds + signs + notarizes
#      + staples AutoApply-1.0.0-universal.pkg.
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-generate-csr}"

if [[ "${MODE}" == "generate-csr" ]]; then
    CSR_PATH="${HOME}/Desktop/AutoApply-DeveloperID.certSigningRequest"
    KEY_PATH="${HOME}/.autoapply-devid-private.key"
    if [[ ! -f "${KEY_PATH}" ]]; then
        openssl genrsa -out "${KEY_PATH}" 2048
        chmod 600 "${KEY_PATH}"
        security import "${KEY_PATH}" -k "${HOME}/Library/Keychains/login.keychain-db" -T /usr/bin/codesign -T /usr/bin/productbuild -T /usr/bin/productsign || true
    fi
    CSR_EMAIL="${APPLE_CSR_EMAIL:-info@turboapply.agency}"
    openssl req -new -key "${KEY_PATH}" -out "${CSR_PATH}" -subj "/emailAddress=${CSR_EMAIL}/CN=TurboApply AutoApply Release/C=CA"
    echo "==> Generated CSR at: ${CSR_PATH}"
    echo "    Next steps at https://developer.apple.com/account/resources/certificates/add :"
    echo "    1. Create 'Developer ID Application' certificate using ${CSR_PATH} and download to ~/Downloads"
    echo "    2. Create 'Developer ID Installer' certificate using ${CSR_PATH} and download to ~/Downloads"
elif [[ "${MODE}" == "import-and-notarize" ]]; then
    APPLE_ID="${2:?Usage: $0 import-and-notarize <apple-id> <team-id> <app-specific-password>}"
    TEAM_ID="${3:?Usage: $0 import-and-notarize <apple-id> <team-id> <app-specific-password>}"
    APP_PW="${4:?Usage: $0 import-and-notarize <apple-id> <team-id> <app-specific-password>}"

    for cer in "${HOME}"/Downloads/*.cer; do
        if [[ -f "${cer}" ]]; then
            echo "==> Importing ${cer} into login Keychain..."
            security import "${cer}" -k "${HOME}/Library/Keychains/login.keychain-db" -T /usr/bin/codesign -T /usr/bin/productbuild -T /usr/bin/productsign || true
        fi
    done

    echo "==> Storing Apple Notary credentials in Keychain profile 'autoapply-notary'..."
    xcrun notarytool store-credentials "autoapply-notary" \
        --apple-id "${APPLE_ID}" \
        --team-id "${TEAM_ID}" \
        --password "${APP_PW}"

    echo "==> Running signed + notarized production build..."
    APPLE_NOTARY_PROFILE="autoapply-notary" "${ROOT_DIR}/packaging/promote_production_release.sh"
fi
