#!/bin/bash
#
# Floating Clock installer
# Usage: curl -fsSL https://raw.githubusercontent.com/surya-prakash-susarla/OnScreenClock/main/install.sh | bash
#
set -e

REPO="surya-prakash-susarla/OnScreenClock"
APP_NAME="FloatingClock"
INSTALL_DIR="/Applications"
BUNDLE_ID="com.suryaprakash.floatingclock"
LAUNCHAGENT_DIR="$HOME/Library/LaunchAgents"
LAUNCHAGENT_PATH="$LAUNCHAGENT_DIR/$BUNDLE_ID.plist"

echo "==> Downloading $APP_NAME..."
DOWNLOAD_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
    | grep "browser_download_url.*FloatingClock.zip" \
    | head -1 \
    | cut -d '"' -f 4)

if [ -z "$DOWNLOAD_URL" ]; then
    echo "Error: Could not find a release download URL."
    echo "Make sure there is a release at https://github.com/$REPO/releases"
    exit 1
fi

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

curl -fsSL -o "$TMPDIR/$APP_NAME.zip" "$DOWNLOAD_URL"

echo "==> Installing to $INSTALL_DIR..."
# Remove old version if present
if [ -d "$INSTALL_DIR/$APP_NAME.app" ]; then
    echo "    Removing previous installation..."
    rm -rf "$INSTALL_DIR/$APP_NAME.app"
fi

unzip -q "$TMPDIR/$APP_NAME.zip" -d "$INSTALL_DIR"

# Remove quarantine attribute so the app opens without Gatekeeper prompt
xattr -dr com.apple.quarantine "$INSTALL_DIR/$APP_NAME.app" 2>/dev/null || true

echo "==> Installed $APP_NAME.app to $INSTALL_DIR"

# Ask about login item
echo ""
read -r -p "Start $APP_NAME at login? [y/N] " response
if [[ "$response" =~ ^[Yy]$ ]]; then
    mkdir -p "$LAUNCHAGENT_DIR"
    cat > "$LAUNCHAGENT_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$BUNDLE_ID</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/$APP_NAME.app/Contents/MacOS/$APP_NAME</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
PLIST
    echo "    Added to Login Items."
fi

echo "==> Launching $APP_NAME..."
open "$INSTALL_DIR/$APP_NAME.app"

echo ""
echo "Done! $APP_NAME is running."
echo "Look for the clock icon in your menu bar."
