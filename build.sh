#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Bump version: major.minor.patch → patch += 1
# ---------------------------------------------------------------------------
CURRENT=$(cat VERSION | tr -d '[:space:]')
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"
PATCH=$((PATCH + 1))
NEW_VERSION="$MAJOR.$MINOR.$PATCH"
echo "$NEW_VERSION" > VERSION
echo "==> Version: $CURRENT → $NEW_VERSION"

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
echo "==> Cleaning previous builds..."
rm -rf build dist build_venv

echo "==> Creating build virtualenv..."
python3 -m venv build_venv
source build_venv/bin/activate

echo "==> Installing dependencies..."
pip install -q -r requirements.txt py2app

echo "==> Building FloatingClock.app (v$NEW_VERSION)..."
python setup.py py2app 2>&1 | tail -5

echo "==> Creating zip for distribution..."
cd dist
zip -r -q FloatingClock.zip FloatingClock.app
cd ..

SIZE=$(du -sh dist/FloatingClock.zip | cut -f1)
SHA=$(shasum -a 256 dist/FloatingClock.zip | cut -d ' ' -f 1)

echo ""
echo "Done! Built v$NEW_VERSION:"
echo "  dist/FloatingClock.app   (standalone app)"
echo "  dist/FloatingClock.zip   ($SIZE)"
echo "  SHA-256: $SHA"
echo ""
echo "To test:    open dist/FloatingClock.app"
echo "To release: bash release.sh"
