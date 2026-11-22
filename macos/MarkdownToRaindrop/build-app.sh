#!/usr/bin/env bash
# Build "Markdown to Raindrop.app" from this Swift package.
#   ./build-app.sh            # release build into macos/MarkdownToRaindrop/dist/
#   ./build-app.sh --install  # also copy it to ~/Applications
#   ./build-app.sh --test     # run the unit tests instead
#
# Works with full Xcode or with just the Command Line Tools: on macOS 26+ SDKs SwiftUI's
# @State/@Observable macros ship only inside Xcode.app, so their plugin directory is passed
# explicitly when the active developer directory is the Command Line Tools.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HERE/dist/Markdown to Raindrop.app"
CONTENTS="$APP/Contents"
VERSION="1.0.0"

FLAGS=()
XCODE_PLUGINS="${XCODE_APP:-/Applications/Xcode.app}/Contents/Developer/Platforms/MacOSX.platform/Developer/usr/lib/swift/host/plugins"
if [[ "$(xcode-select -p)" == *CommandLineTools* && -d "$XCODE_PLUGINS" ]]; then
  FLAGS+=(-Xswiftc -plugin-path -Xswiftc "$XCODE_PLUGINS")
  CLT_TESTING="$(xcode-select -p)/usr/lib/swift/host/plugins/testing"
  [[ -d "$CLT_TESTING" ]] && FLAGS+=(-Xswiftc -plugin-path -Xswiftc "$CLT_TESTING")
fi

cd "$HERE"
if [[ "${1:-}" == "--test" ]]; then
  exec swift test "${FLAGS[@]+"${FLAGS[@]}"}"
fi

swift build -c release --product MarkdownToRaindrop "${FLAGS[@]+"${FLAGS[@]}"}"
BIN="$(swift build -c release --show-bin-path)/MarkdownToRaindrop"

rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources"
cp "$BIN" "$CONTENTS/MacOS/MarkdownToRaindrop"
# SwiftPM records the deployment target as the SDK version, which makes AppKit run the app in
# compatibility mode (no Liquid Glass). Stamp the real SDK version instead.
xcrun vtool -set-build-version macos 14.0 "$(xcrun --show-sdk-version)" -replace \
  -output "$CONTENTS/MacOS/MarkdownToRaindrop" "$CONTENTS/MacOS/MarkdownToRaindrop"

cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Markdown to Raindrop</string>
  <key>CFBundleDisplayName</key><string>Markdown to Raindrop</string>
  <key>CFBundleIdentifier</key><string>com.fullstackranger.MarkdownToRaindrop</string>
  <key>CFBundleExecutable</key><string>MarkdownToRaindrop</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# Ad-hoc signature: enough to run locally; Keychain access is tied to this signature.
codesign --force --sign - "$APP" >/dev/null
echo "Built: $APP"

if [[ "${1:-}" == "--install" ]]; then
  mkdir -p "$HOME/Applications"
  rm -rf "$HOME/Applications/Markdown to Raindrop.app"
  cp -R "$APP" "$HOME/Applications/"
  echo "Installed: $HOME/Applications/Markdown to Raindrop.app"
fi
