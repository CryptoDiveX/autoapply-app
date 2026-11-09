#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Staged Dev -> Production Release Promotion Pipeline for AutoApply
#
# Everyday development uses `make build-dev` (updates local /Applications/AutoApply.app
# only, without touching production website installers).
#
# Run `make promote-production` (this script) ONLY after testing and bundling
# fixes that are ready to be published to production downloads.
# ==============================================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
APP_VERSION="1.0.0"
DMG_NAME="AutoApply-${APP_VERSION}-universal.dmg"
PKG_NAME="AutoApply-${APP_VERSION}-universal.pkg"
WEBSITE_REPO="${TURBOAPPLY_WEBSITE_REPO:-${HOME}/Hermes/projects/turboapply-agency-job-searcher}"
WEBSITE_DOWNLOADS_DIR="${WEBSITE_REPO}/public/downloads"

echo "==> [1/5] Running Open-Source Privacy & Security Audit..."
python3 "${ROOT_DIR}/packaging/audit_opensource_privacy.py"

echo "==> [2/5] Running Python & Swift Verification Suites..."
cd "${ROOT_DIR}"
PYTHONPATH=runtime:. pytest tests/unit tests/contract tests/security tests/coexistence tests/integration -q
swift run AutoApplyNativeTestRunner

echo "==> [3/5] Building Universal Production Installers (.dmg + .pkg + .app)..."
"${ROOT_DIR}/packaging/build_macos_installer.sh"

echo "==> [4/5] Re-auditing Built Application Bundle for Zero Personal PII..."
python3 "${ROOT_DIR}/packaging/audit_opensource_privacy.py" --check-bundle

echo "==> [5/5] Staging Downloadable Production Installers & Release Manifest..."
mkdir -p "${DIST_DIR}/production-release"
cp "${DIST_DIR}/${DMG_NAME}" "${DIST_DIR}/production-release/${DMG_NAME}"
cp "${DIST_DIR}/${PKG_NAME}" "${DIST_DIR}/production-release/${PKG_NAME}"

DMG_SHA256="$(shasum -a 256 "${DIST_DIR}/${DMG_NAME}" | awk '{print $1}')"
PKG_SHA256="$(shasum -a 256 "${DIST_DIR}/${PKG_NAME}" | awk '{print $1}')"
DMG_BYTES="$(stat -f%z "${DIST_DIR}/${DMG_NAME}")"
PKG_BYTES="$(stat -f%z "${DIST_DIR}/${PKG_NAME}")"
RELEASED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat > "${DIST_DIR}/production-release/release-manifest.json" <<EOF
{
  "product": "AutoApply for macOS",
  "version": "${APP_VERSION}",
  "channel": "production",
  "released_at": "${RELEASED_AT}",
  "architectures": ["arm64", "x86_64"],
  "minimum_macos": "13.0",
  "trial_mode_grace_active": true,
  "licensing_limits_enforced": false,
  "open_source_repo": "https://github.com/CryptoDiveX/autoapply-app",
  "dmg_url": "/public/downloads/${DMG_NAME}",
  "dmg_sha256": "${DMG_SHA256}",
  "dmg_size_bytes": ${DMG_BYTES},
  "pkg_url": "/public/downloads/${PKG_NAME}",
  "pkg_sha256": "${PKG_SHA256}",
  "pkg_size_bytes": ${PKG_BYTES}
}
EOF

if [[ -d "${WEBSITE_REPO}" ]]; then
    mkdir -p "${WEBSITE_DOWNLOADS_DIR}"
    cp "${DIST_DIR}/${DMG_NAME}" "${WEBSITE_DOWNLOADS_DIR}/${DMG_NAME}"
    cp "${DIST_DIR}/${PKG_NAME}" "${WEBSITE_DOWNLOADS_DIR}/${PKG_NAME}"
    cp "${DIST_DIR}/production-release/release-manifest.json" "${WEBSITE_DOWNLOADS_DIR}/release-manifest.json"
    echo "    Synced production installers to ${WEBSITE_DOWNLOADS_DIR}"
fi

echo "==> Production Release v${APP_VERSION} Promoted Successfully:"
echo "    DMG (${DMG_BYTES} bytes, SHA-256: ${DMG_SHA256})"
echo "    PKG (${PKG_BYTES} bytes, SHA-256: ${PKG_SHA256})"
echo "    Manifest: ${DIST_DIR}/production-release/release-manifest.json"
