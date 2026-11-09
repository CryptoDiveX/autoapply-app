#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/dist"
APP_NAME="AutoApply"
APP_VERSION="1.0.0"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
PKG_WORK="${DIST_DIR}/pkg-staging"
PKG_PATH="${DIST_DIR}/${APP_NAME}-${APP_VERSION}-universal.pkg"
DMG_STAGING="${DIST_DIR}/dmg-staging"
DMG_PATH="${DIST_DIR}/${APP_NAME}-${APP_VERSION}-universal.dmg"
DETECTED_APP_SIGN_ID="$(security find-identity -v -p codesigning 2>/dev/null | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' | head -n 1 || true)"
DETECTED_PKG_SIGN_ID="$(security find-identity -v 2>/dev/null | sed -n 's/.*"\(Developer ID Installer:[^"]*\)".*/\1/p' | head -n 1 || true)"
CODESIGN_ID="${APPLE_DEVELOPER_ID:-${DETECTED_APP_SIGN_ID:--}}"
INSTALLER_SIGN_ID="${APPLE_INSTALLER_ID:-${DETECTED_PKG_SIGN_ID:-}}"
NOTARY_PROFILE="${APPLE_NOTARY_PROFILE:-}"

echo "==> [1/7] Building Universal (arm64 + x86_64) Release Mach-O Binary..."
cd "${ROOT_DIR}"
mkdir -p "${DIST_DIR}"
touch "${DIST_DIR}/.gitkeep"
chmod +x "${ROOT_DIR}/packaging/pkg-scripts/postinstall"
swift build -c release --arch arm64 --arch x86_64 --product AutoApply
BIN_DIR="$(swift build -c release --arch arm64 --arch x86_64 --product AutoApply --show-bin-path)"
UNIVERSAL_BIN="${BIN_DIR}/AutoApply"

if [[ ! -f "${UNIVERSAL_BIN}" ]]; then
    echo "ERROR: Universal binary not found at ${UNIVERSAL_BIN}" >&2
    exit 1
fi
echo "    Verified architectures: $(lipo -archs "${UNIVERSAL_BIN}")"

echo "==> [2/7] Assembling ${APP_BUNDLE} bundle structure..."
if ! rm -rf "${APP_BUNDLE}" "${PKG_WORK}" "${PKG_PATH}" "${DMG_STAGING}" "${DMG_PATH}" 2>/dev/null; then
    mv "${DIST_DIR}" "${HOME}/.Trash/autoapply_dist_old_$(date +%s)"
    mkdir -p "${DIST_DIR}"
    touch "${DIST_DIR}/.gitkeep"
fi
mkdir -p "${APP_BUNDLE}/Contents/MacOS"
mkdir -p "${APP_BUNDLE}/Contents/Resources/runtime"
mkdir -p "${APP_BUNDLE}/Contents/Resources/schemas"
mkdir -p "${APP_BUNDLE}/Contents/Resources/packaging"
mkdir -p "${APP_BUNDLE}/Contents/Resources/docs/release"

cp "${UNIVERSAL_BIN}" "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"
chmod +x "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"

cat > "${APP_BUNDLE}/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.autoapply.macos</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>AutoApply</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${APP_VERSION}</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>AutoApply uses your microphone only when you explicitly start an optional voice profile interview.</string>
    <key>NSSpeechRecognitionUsageDescription</key>
    <string>AutoApply transcribes your voice answers locally into your Knowledge Base when you record a voice interview.</string>
</dict>
</plist>
EOF

echo "==> [3/8] Generating macOS AppIcon.icns & matching BrowserIcon.icns..."
ICONSET_DIR="${DIST_DIR}/AppIcon.iconset"
BROWSER_ICONSET_DIR="${DIST_DIR}/BrowserIcon.iconset"
rm -rf "${ICONSET_DIR}" "${BROWSER_ICONSET_DIR}"
mkdir -p "${ICONSET_DIR}" "${BROWSER_ICONSET_DIR}"

python3 - "${ICONSET_DIR}/icon_512x512@2x.png" "${BROWSER_ICONSET_DIR}/icon_512x512@2x.png" <<'PY'
import math, struct, sys, zlib

def write_png(path: str, rows: list[bytes], width: int = 1024, height: int = 1024) -> None:
    raw = b"".join(rows)
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)

def squircle_alpha(x: int, y: int, width: int = 1024, height: int = 1024) -> int:
    # Apple HIG macOS squircle: 824x824 rounded rect inside 1024x1024 (inset=100, corner radius=185)
    cx, cy = width / 2.0, height / 2.0
    half_box = 412.0
    radius = 185.0
    dx = max(abs(x - cx) - (half_box - radius), 0.0)
    dy = max(abs(y - cy) - (half_box - radius), 0.0)
    d = math.hypot(dx, dy) - radius
    if d >= 0.75:
        return 0
    if d <= -0.75:
        return 255
    return int(255.0 * (0.75 - d) / 1.5)

def make_app_png(path: str, width: int = 1024, height: int = 1024) -> None:
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            a = squircle_alpha(x, y, width, height)
            if a == 0:
                row.extend((0, 0, 0, 0))
                continue
            r = int(24 + (x / width) * 30)
            g = int(58 + (y / height) * 110)
            b = int(165 + ((x + y) / (width + height)) * 75)
            if 280 <= x <= 744 and (320 <= y <= 400 or 480 <= y <= 560 or 640 <= y <= 720):
                r, g, b = 245, 248, 255
            row.extend((r, g, b, a))
        rows.append(bytes(row))
    write_png(path, rows, width, height)

def make_browser_png(path: str, width: int = 1024, height: int = 1024) -> None:
    cx, cy = width / 2.0, height / 2.0
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            a = squircle_alpha(x, y, width, height)
            if a == 0:
                row.extend((0, 0, 0, 0))
                continue
            r = int(16 + (x / width) * 28)
            g = int(85 + (y / height) * 125)
            b = int(185 + ((x + y) / (width + height)) * 65)
            dist = math.hypot(x - cx, y - cy)
            if 320 <= dist <= 362:
                r, g, b = 125, 240, 255
            elif 335 <= x <= 689 and (365 <= y <= 420 or 484 <= y <= 540 or 604 <= y <= 659):
                r, g, b = 245, 250, 255
            row.extend((r, g, b, a))
        rows.append(bytes(row))
    write_png(path, rows, width, height)

make_app_png(sys.argv[1])
make_browser_png(sys.argv[2])
PY

for size in 16 32 128 256 512; do
    sips -z "${size}" "${size}" "${ICONSET_DIR}/icon_512x512@2x.png" --out "${ICONSET_DIR}/icon_${size}x${size}.png" >/dev/null
    sips -z "${size}" "${size}" "${BROWSER_ICONSET_DIR}/icon_512x512@2x.png" --out "${BROWSER_ICONSET_DIR}/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "${double}" "${double}" "${ICONSET_DIR}/icon_512x512@2x.png" --out "${ICONSET_DIR}/icon_${size}x${size}@2x.png" >/dev/null
    sips -z "${double}" "${double}" "${BROWSER_ICONSET_DIR}/icon_512x512@2x.png" --out "${BROWSER_ICONSET_DIR}/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "${ICONSET_DIR}" -o "${APP_BUNDLE}/Contents/Resources/AppIcon.icns"
iconutil -c icns "${BROWSER_ICONSET_DIR}" -o "${APP_BUNDLE}/Contents/Resources/BrowserIcon.icns"
cp "${BROWSER_ICONSET_DIR}/icon_256x256.png" "${APP_BUNDLE}/Contents/Resources/BrowserIcon.png"
rm -rf "${ICONSET_DIR}" "${BROWSER_ICONSET_DIR}"

echo "==> [4/8] Bundling isolated Python runtime, Browser, CapSolver extension, and app resources..."
cp -R "${ROOT_DIR}/runtime/autoapply" "${APP_BUNDLE}/Contents/Resources/runtime/"
find "${APP_BUNDLE}/Contents/Resources/runtime" -name "__pycache__" -prune -exec rm -rf {} +
cp "${ROOT_DIR}"/schemas/*.json "${APP_BUNDLE}/Contents/Resources/schemas/"
cp "${ROOT_DIR}/packaging/runtime-manifest.json" "${APP_BUNDLE}/Contents/Resources/packaging/"
chmod +x "${ROOT_DIR}/packaging/uninstall_autoapply.sh"
chmod +x "${ROOT_DIR}/packaging/uninstall-pkg-scripts/postinstall"
cp "${ROOT_DIR}/packaging/uninstall_autoapply.sh" "${APP_BUNDLE}/Contents/Resources/packaging/uninstall_autoapply.sh"
chmod +x "${APP_BUNDLE}/Contents/Resources/packaging/uninstall_autoapply.sh"
cp "${ROOT_DIR}/docs/release/gates.json" "${APP_BUNDLE}/Contents/Resources/docs/release/"

if [[ -d "${ROOT_DIR}/packaging/extensions/capsolver" ]]; then
    mkdir -p "${APP_BUNDLE}/Contents/Resources/extensions"
    cp -R "${ROOT_DIR}/packaging/extensions/capsolver" "${APP_BUNDLE}/Contents/Resources/extensions/"
fi
if [[ -d "${ROOT_DIR}/packaging/extensions/autoapply_companion" ]]; then
    mkdir -p "${APP_BUNDLE}/Contents/Resources/extensions"
    cp -R "${ROOT_DIR}/packaging/extensions/autoapply_companion" "${APP_BUNDLE}/Contents/Resources/extensions/"
fi
if [[ -d "${ROOT_DIR}/packaging/interview_audio" ]]; then
    mkdir -p "${APP_BUNDLE}/Contents/Resources/interview_audio"
    mkdir -p "${APP_BUNDLE}/Contents/Resources/packaging/interview_audio"
    cp "${ROOT_DIR}"/packaging/interview_audio/*.mp3 "${APP_BUNDLE}/Contents/Resources/interview_audio/" 2>/dev/null || true
    cp "${ROOT_DIR}"/packaging/interview_audio/*.mp3 "${APP_BUNDLE}/Contents/Resources/packaging/interview_audio/" 2>/dev/null || true
fi
if [[ -d "${ROOT_DIR}/packaging/hermes-skills" ]]; then
    mkdir -p "${APP_BUNDLE}/Contents/Resources/hermes-skills"
    cp -R "${ROOT_DIR}/packaging/hermes-skills/"* "${APP_BUNDLE}/Contents/Resources/hermes-skills/"
fi
if [[ -d "${ROOT_DIR}/packaging/board_logos" ]]; then
    mkdir -p "${APP_BUNDLE}/Contents/Resources/board_logos"
    mkdir -p "${APP_BUNDLE}/Contents/Resources/packaging/board_logos"
    cp "${ROOT_DIR}"/packaging/board_logos/*.png "${APP_BUNDLE}/Contents/Resources/board_logos/" 2>/dev/null || true
    cp "${ROOT_DIR}"/packaging/board_logos/*.png "${APP_BUNDLE}/Contents/Resources/packaging/board_logos/" 2>/dev/null || true
fi

mkdir -p "${APP_BUNDLE}/Contents/Resources/bin"
for TOOL_BIN in sops age age-keygen; do
    for PREFIX in /opt/homebrew/bin /usr/local/bin; do
        if [[ -x "${PREFIX}/${TOOL_BIN}" ]]; then
            cp "${PREFIX}/${TOOL_BIN}" "${APP_BUNDLE}/Contents/Resources/bin/${TOOL_BIN}"
            chmod +x "${APP_BUNDLE}/Contents/Resources/bin/${TOOL_BIN}"
            codesign --force --sign "${CODESIGN_ID}" "${APP_BUNDLE}/Contents/Resources/bin/${TOOL_BIN}"
            break
        fi
    done
done

mkdir -p "${APP_BUNDLE}/Contents/Resources/python-env/bin"
cat > "${APP_BUNDLE}/Contents/Resources/python-env/bin/python3" <<'EOF'
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
for CANDIDATE in \
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3" \
    "/usr/local/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/bin/python3"; do
    if [ -x "${CANDIDATE}" ]; then
        exec "${CANDIDATE}" -B "$@"
    fi
done
echo "ERROR: python3 runtime not found" >&2
exit 1
EOF
chmod +x "${APP_BUNDLE}/Contents/Resources/python-env/bin/python3"

echo "==> [5/8] Embedding bundled AutoApply Browser with matching icon and codesigning ${APP_BUNDLE}..."
CLOAK_SRC=""
for CANDIDATE_APP in "${HOME}"/.cloakbrowser/chromium-*/Chromium.app; do
    if [[ -d "${CANDIDATE_APP}" ]]; then
        CLOAK_SRC="${CANDIDATE_APP}"
    fi
done

if [[ -n "${CLOAK_SRC}" && -d "${CLOAK_SRC}" ]]; then
    mkdir -p "${APP_BUNDLE}/Contents/Resources/Browser"
    BUNDLED_BROWSER="${APP_BUNDLE}/Contents/Resources/Browser/AutoApply Browser.app"
    ditto "${CLOAK_SRC}" "${BUNDLED_BROWSER}"
    cp "${APP_BUNDLE}/Contents/Resources/BrowserIcon.icns" "${BUNDLED_BROWSER}/Contents/Resources/app.icns"
    rm -f "${BUNDLED_BROWSER}/Contents/Resources/Assets.car"
    cp "${BUNDLED_BROWSER}/Contents/MacOS/Chromium" "${BUNDLED_BROWSER}/Contents/MacOS/AutoApply Browser"
    chmod +x "${BUNDLED_BROWSER}/Contents/MacOS/AutoApply Browser"
    /usr/libexec/PlistBuddy -c "Set :CFBundleExecutable 'AutoApply Browser'" "${BUNDLED_BROWSER}/Contents/Info.plist" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :CFBundleName 'AutoApply Browser'" "${BUNDLED_BROWSER}/Contents/Info.plist" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName 'AutoApply Browser'" "${BUNDLED_BROWSER}/Contents/Info.plist" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :CFBundleIconFile 'app.icns'" "${BUNDLED_BROWSER}/Contents/Info.plist" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "${BUNDLED_BROWSER}/Contents/Info.plist" 2>/dev/null || true
    echo "branded_v4" > "${BUNDLED_BROWSER}/Contents/Resources/.autoapply_branded_v4"
    touch "${BUNDLED_BROWSER}"
    xattr -cr "${BUNDLED_BROWSER}" 2>/dev/null || true
    # Sign top-level AutoApply Browser.app WITHOUT --deep so inner helper apps keep their JIT entitlements and identifiers
    codesign --force --sign "${CODESIGN_ID}" --identifier org.chromium.Chromium "${BUNDLED_BROWSER}"
    "${BUNDLED_BROWSER}/Contents/MacOS/AutoApply Browser" --headless=new --dump-dom "about:blank" >/dev/null 2>&1 || true
fi

if [[ "${CODESIGN_ID}" != "-" ]]; then
    CODESIGN_FLAGS=(--force --options runtime --timestamp --entitlements "${ROOT_DIR}/packaging/entitlements.plist" --sign "${CODESIGN_ID}")
else
    CODESIGN_FLAGS=(--force --sign "${CODESIGN_ID}")
fi
codesign "${CODESIGN_FLAGS[@]}" "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}"
codesign "${CODESIGN_FLAGS[@]}" "${APP_BUNDLE}"
codesign --verify --verbose=2 "${APP_BUNDLE}"

echo "==> [6/8] Building guided Apple Installer package ${PKG_PATH}..."
mkdir -p "${PKG_WORK}/root" "${PKG_WORK}/resources"
ditto "${APP_BUNDLE}" "${PKG_WORK}/root/${APP_NAME}.app"

cat > "${PKG_WORK}/resources/welcome.html" <<'EOF'
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; font-size: 13px; line-height: 1.5; color: #1d1d1f; }
h2 { font-size: 18px; margin-bottom: 8px; }
ul { padding-left: 20px; }
li { margin-bottom: 6px; }
</style></head>
<body>
<h2>Welcome to the AutoApply Installer</h2>
<p>This installer sets up <strong>AutoApply</strong> in <code>/Applications/AutoApply.app</code> along with all embedded packages, dependencies, and isolated runtime environments:</p>
<ul>
  <li><strong>Native Universal macOS Application</strong> (Apple Silicon + Intel)</li>
  <li><strong>Bundled AutoApply Browser</strong> with the <strong>AutoApply Companion Side-Panel Extension</strong> and <strong>Capcha Solver Extension</strong> pre-installed, enabled, and pinned</li>
  <li><strong>Natural Voice Interview Studio</strong> with spoken questions and voice answer recording</li>
  <li><strong>Local Encrypted Credentials Vault</strong> and unified browser session</li>
  <li><strong>Synchronized Split Markdown Knowledge Base &amp; Tailored Resume Engine</strong></li>
</ul>
</body>
</html>
EOF

cat > "${PKG_WORK}/resources/conclusion.html" <<'EOF'
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; font-size: 13px; line-height: 1.5; color: #1d1d1f; }
h2 { font-size: 18px; color: #0a7d32; margin-bottom: 8px; }
</style></head>
<body>
<h2>AutoApply is Installed and Ready</h2>
<p>All components, browser profiles, CapSolver extension settings, and your local Knowledge Base workspace have been configured automatically.</p>
<p>Launch <strong>AutoApply</strong> from <code>/Applications</code> or Spotlight to get started.</p>
</body>
</html>
EOF

pkgbuild --analyze --root "${PKG_WORK}/root" "${PKG_WORK}/component.plist"
/usr/libexec/PlistBuddy -c "Set :0:BundleIsRelocatable false" "${PKG_WORK}/component.plist" 2>/dev/null || true

pkgbuild \
    --root "${PKG_WORK}/root" \
    --component-plist "${PKG_WORK}/component.plist" \
    --install-location "/Applications" \
    --scripts "${ROOT_DIR}/packaging/pkg-scripts" \
    --identifier "com.autoapply.macos.pkg" \
    --version "${APP_VERSION}" \
    "${PKG_WORK}/AutoApply-component.pkg"

cat > "${PKG_WORK}/Distribution.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>AutoApply ${APP_VERSION}</title>
    <welcome file="welcome.html" mime-type="text/html"/>
    <conclusion file="conclusion.html" mime-type="text/html"/>
    <options customize="never" require-scripts="false" hostArchitectures="arm64,x86_64"/>
    <domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>
    <choices-outline>
        <line choice="default">
            <line choice="com.autoapply.macos.pkg"/>
        </line>
    </choices-outline>
    <choice id="default"/>
    <choice id="com.autoapply.macos.pkg" visible="false">
        <pkg-ref id="com.autoapply.macos.pkg"/>
    </choice>
    <pkg-ref id="com.autoapply.macos.pkg" version="${APP_VERSION}" onConclusion="none">AutoApply-component.pkg</pkg-ref>
</installer-gui-script>
EOF

if [[ -n "${INSTALLER_SIGN_ID}" ]]; then
    echo "    Signing PKG with Developer ID Installer (${INSTALLER_SIGN_ID})..."
    productbuild \
        --distribution "${PKG_WORK}/Distribution.xml" \
        --resources "${PKG_WORK}/resources" \
        --package-path "${PKG_WORK}" \
        --sign "${INSTALLER_SIGN_ID}" \
        "${PKG_PATH}"
    if [[ -n "${NOTARY_PROFILE}" ]]; then
        echo "    Submitting ${PKG_PATH} to Apple Notary Service (profile: ${NOTARY_PROFILE})..."
        xcrun notarytool submit "${PKG_PATH}" --keychain-profile "${NOTARY_PROFILE}" --wait
        xcrun stapler staple "${PKG_PATH}"
    fi
else
    productbuild \
        --distribution "${PKG_WORK}/Distribution.xml" \
        --resources "${PKG_WORK}/resources" \
        --package-path "${PKG_WORK}" \
        "${PKG_PATH}"
fi

rm -rf "${PKG_WORK}"

UNINSTALL_APP="${DIST_DIR}/Uninstall AutoApply.app"
UNINSTALL_PKG="${DIST_DIR}/${APP_NAME}-Uninstaller-${APP_VERSION}.pkg"
UNINSTALL_WORK="${DIST_DIR}/uninstall-pkg-staging"

echo "==> [7/8] Building Clean Uninstaller (${UNINSTALL_APP})..."
rm -rf "${UNINSTALL_APP}" "${UNINSTALL_PKG}" "${UNINSTALL_WORK}"
mkdir -p "${UNINSTALL_APP}/Contents/MacOS" "${UNINSTALL_APP}/Contents/Resources"
cp "${APP_BUNDLE}/Contents/Resources/AppIcon.icns" "${UNINSTALL_APP}/Contents/Resources/AppIcon.icns"
cp "${ROOT_DIR}/packaging/uninstall_autoapply.sh" "${UNINSTALL_APP}/Contents/Resources/uninstall_autoapply.sh"
chmod +x "${UNINSTALL_APP}/Contents/Resources/uninstall_autoapply.sh"

cat > "${UNINSTALL_APP}/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>UninstallAutoApply</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.autoapply.macos.uninstaller</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Uninstall AutoApply</string>
    <key>CFBundleDisplayName</key>
    <string>Uninstall AutoApply</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${APP_VERSION}</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

cat > "${UNINSTALL_APP}/Contents/MacOS/UninstallAutoApply" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
UNINSTALL_SH="${SCRIPT_DIR}/uninstall_autoapply.sh"

for arg in "$@"; do
    if [[ "$arg" == "--yes" || "$arg" == "-y" || "$arg" == "--non-interactive" || "$arg" == "--reset-data-only" ]]; then
        exec "${UNINSTALL_SH}" "$@"
    fi
done

CONFIRM="$(osascript -e 'display dialog "Cleanly uninstall AutoApply?\n\nThis removes ONLY AutoApply:\n• /Applications/AutoApply.app\n• ~/Library/Application Support/AutoApply\n• AutoApply Keychain credentials & caches\n\nAny standalone Hermes (~/.hermes), standalone browser (~/.cloakbrowser), or other system tools on your Mac will remain 100% untouched." buttons {"Cancel", "Uninstall AutoApply"} default button "Uninstall AutoApply" with title "Uninstall AutoApply" with icon caution' 2>/dev/null || true)"

if [[ "${CONFIRM}" == *"Uninstall AutoApply"* ]]; then
    "${UNINSTALL_SH}" --yes
    osascript -e 'display dialog "AutoApply and its local workspace data have been completely removed.\n\nAll standalone tools on your Mac were left intact." buttons {"OK"} default button "OK" with title "Uninstall Complete"' >/dev/null 2>&1 || true
fi
EOF
chmod +x "${UNINSTALL_APP}/Contents/MacOS/UninstallAutoApply"
codesign --deep "${CODESIGN_FLAGS[@]}" "${UNINSTALL_APP}"

echo "==> [8/8] Building installable disk image ${DMG_PATH} (with Installer, Uninstaller, and App Bundle)..."
mkdir -p "${DMG_STAGING}"
ditto "${APP_BUNDLE}" "${DMG_STAGING}/${APP_NAME}.app"
ditto "${UNINSTALL_APP}" "${DMG_STAGING}/Uninstall AutoApply.app"
cp "${PKG_PATH}" "${DMG_STAGING}/Install AutoApply.pkg"
ln -s /Applications "${DMG_STAGING}/Applications"
hdiutil create -volname "AutoApply Installer" -srcfolder "${DMG_STAGING}" -ov -format UDZO "${DMG_PATH}"
rm -rf "${DMG_STAGING}"

echo "==> Packaging complete:"
echo "    App Bundle      : ${APP_BUNDLE}"
echo "    PKG Installer   : ${PKG_PATH}"
echo "    Uninstaller App : ${UNINSTALL_APP}"
echo "    DMG Image       : ${DMG_PATH}"
