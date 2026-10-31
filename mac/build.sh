#!/bin/bash
# Builds ~/Applications/Brain.app from mac/main.swift, with Brain's icon. Needs Xcode command line tools.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; BRAIN="$(dirname "$HERE")"
APP="$HOME/Applications/Brain.app"; C="$APP/Contents"
rm -rf "$APP"; mkdir -p "$C/MacOS" "$C/Resources"
swiftc -O "$HERE/main.swift" -o "$C/MacOS/Brain"
echo "$BRAIN/bin/brain" > "$C/Resources/brain-path"
ICON="$(mktemp -d)/Brain.iconset"; mkdir -p "$ICON"
for s in 16 32 128 256 512; do
  sips -z $s $s "$BRAIN/mobile/icon-512.png" --out "$ICON/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$BRAIN/mobile/icon-512.png" --out "$ICON/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICON" -o "$C/Resources/Brain.icns"
cat > "$C/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Brain</string>
  <key>CFBundleIdentifier</key><string>dev.brain.mac</string>
  <key>CFBundleExecutable</key><string>Brain</string>
  <key>CFBundleIconFile</key><string>Brain</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppleEventsUsageDescription</key><string>Brain tiles read things like what Spotify is playing, and room-temp alerts send you a text.</string>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST
codesign -s - --force "$APP" >/dev/null 2>&1 || true
echo "$APP"
