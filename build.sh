#!/usr/bin/env bash
# build.sh — one-command build: PyInstaller → .app → .dmg
#
# Usage:
#   chmod +x build.sh
#   ./build.sh
#
# Prerequisites:
#   • Python venv at ./venv with requirements.txt installed
#   • PyInstaller installed in the venv  (pip install pyinstaller==6.5.0)
#   • create-dmg installed via Homebrew   (brew install create-dmg)
#   • assets/icon.icns and assets/dmg-background.png present
#
# Outputs:
#   dist/VoxTerm.app       — the runnable macOS app bundle
#   dist/voxterm-<ver>.dmg — the installer DMG ready for GitHub Releases

set -euo pipefail

# ---------------------------------------------------------------------------
# Config — bump VERSION to match voxterm.spec before each release
# ---------------------------------------------------------------------------
VERSION="1.0.0"
APP_NAME="voxterm"
DMG_NAME="${APP_NAME}-${VERSION}.dmg"
DIST_DIR="dist"
BUILD_DIR="build"
VENV_DIR="venv"

# Resolve the repo root (directory containing this script).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { echo "[build] $*"; }
success() { echo "[build] ✓ $*"; }
die()     { echo "[build] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
info "Checking prerequisites…"

[[ -d "${REPO_ROOT}/${VENV_DIR}" ]] \
    || die "venv not found at ${VENV_DIR}/. Run: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt pyinstaller==6.5.0"

# Activate the venv for the rest of the script.
# shellcheck source=/dev/null
source "${REPO_ROOT}/${VENV_DIR}/bin/activate"

command -v pyinstaller &>/dev/null \
    || die "pyinstaller not found in venv. Run: pip install pyinstaller==6.5.0"

command -v create-dmg &>/dev/null \
    || die "create-dmg not found. Run: brew install create-dmg"

[[ -f "${REPO_ROOT}/assets/icon.icns" ]] \
    || die "assets/icon.icns missing. Run: python make_assets.py"

[[ -f "${REPO_ROOT}/assets/dmg-background.png" ]] \
    || die "assets/dmg-background.png missing. Run: python make_assets.py"

# ---------------------------------------------------------------------------
# Clean previous build artefacts
# ---------------------------------------------------------------------------
info "Cleaning previous build artefacts…"
rm -rf "${REPO_ROOT:?}/${DIST_DIR}" "${REPO_ROOT:?}/${BUILD_DIR}"

# ---------------------------------------------------------------------------
# Step 1: PyInstaller — bundle .app
# ---------------------------------------------------------------------------
info "Running PyInstaller…"
cd "${REPO_ROOT}"
pyinstaller voxterm.spec \
    --distpath "${DIST_DIR}" \
    --workpath "${BUILD_DIR}" \
    --noconfirm \
    --clean

APP_PATH="${DIST_DIR}/VoxTerm.app"
[[ -d "${APP_PATH}" ]] || die "PyInstaller finished but ${APP_PATH} was not created."
success "App bundle created: ${APP_PATH}"

# ---------------------------------------------------------------------------
# Step 2: create-dmg — wrap .app into an installer DMG
# ---------------------------------------------------------------------------
info "Creating DMG…"

DMG_PATH="${DIST_DIR}/${DMG_NAME}"

create-dmg \
    --volname         "VoxTerm ${VERSION}" \
    --volicon         "assets/icon.icns" \
    --background      "assets/dmg-background.png" \
    --window-pos      200 200 \
    --window-size     660 400 \
    --icon-size       128 \
    --icon            "${APP_NAME}.app" 180 170 \
    --hide-extension  "${APP_NAME}.app" \
    --app-drop-link   480 170 \
    --no-internet-enable \
    "${DMG_PATH}" \
    "${APP_PATH}"

[[ -f "${DMG_PATH}" ]] || die "create-dmg finished but ${DMG_PATH} was not created."
success "DMG created: ${DMG_PATH}"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "──────────────────────────────────────────────────"
echo "  Build complete"
echo ""
echo "  App bundle : ${DIST_DIR}/${APP_NAME}.app"
echo "  Installer  : ${DIST_DIR}/${DMG_NAME}"
echo ""
echo "  Next steps:"
echo "    1. Test the app:  open ${DIST_DIR}/${APP_NAME}.app"
echo "    2. Upload ${DMG_NAME} to GitHub Releases"
echo "    3. Update the download URL in website/src/components/Download.tsx"
echo ""
echo "  Note: macOS will show 'unidentified developer' on first launch."
echo "  Fix: right-click the app → Open → Open."
echo "  Document this on the landing page."
echo "──────────────────────────────────────────────────"
