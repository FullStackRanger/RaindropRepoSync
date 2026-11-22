#!/usr/bin/env bash
# Build "Web Clipper.app" from this Swift package and the repo's Python engine.
#   ./build-app.sh              # release build into macos/WebClipper/dist/
#   ./build-app.sh --install    # also copy it to ~/Applications and register the webclipper:// scheme
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
APP="$HERE/dist/Web Clipper.app"
CONTENTS="$APP/Contents"
VERSION="1.0.0"

cd "$HERE"
swift build -c release --product WebClipper
BIN="$(swift build -c release --show-bin-path)/WebClipper"

rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources/engine"
cp "$BIN" "$CONTENTS/MacOS/WebClipper"
for f in clip_cli.py web_clip.py clip_storage.py clip_bridge.py; do
  cp "$REPO/$f" "$CONTENTS/Resources/engine/"
done

ICONSET="$(mktemp -d)/AppIcon.iconset"
mkdir -p "$ICONSET"
SRC_ICON="$REPO/browser/web-clipper/icons/icon-128.png"
for size in 16 32 128 256 512; do
  sips -z $size $size "$SRC_ICON" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z $double $double "$SRC_ICON" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$CONTENTS/Resources/AppIcon.icns"

cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Web Clipper</string>
  <key>CFBundleDisplayName</key><string>Web Clipper</string>
  <key>CFBundleIdentifier</key><string>local.toolbelt.WebClipper</string>
  <key>CFBundleExecutable</key><string>WebClipper</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSSupportsAutomaticTermination</key><false/>
  <key>CFBundleURLTypes</key>
  <array>
    <dict>
      <key>CFBundleURLName</key><string>local.toolbelt.WebClipper</string>
      <key>CFBundleURLSchemes</key><array><string>webclipper</string></array>
    </dict>
  </array>
</dict>
</plist>
PLIST

codesign --force --deep --sign - "$APP" >/dev/null
echo "Built: $APP"

if [[ "${1:-}" == "--install" ]]; then
  mkdir -p "$HOME/Applications"
  rm -rf "$HOME/Applications/Web Clipper.app"
  cp -R "$APP" "$HOME/Applications/"
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$HOME/Applications/Web Clipper.app"
  echo "Installed: $HOME/Applications/Web Clipper.app"
fi
