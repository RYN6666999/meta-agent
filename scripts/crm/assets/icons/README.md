# Desktop App Icon Redesign

Two redesigned icon concepts are ready:

- app-orbit.svg
- app-lighthouse.svg

## Convert SVG to PNG (1024x1024)

Install Inkscape once if needed:

```bash
brew install --cask inkscape
```

Export:

```bash
cd /Users/ryan/meta-agent/scripts/crm/assets/icons
inkscape app-orbit.svg -o app-orbit-1024.png -w 1024 -h 1024
inkscape app-lighthouse.svg -o app-lighthouse-1024.png -w 1024 -h 1024
```

## Build macOS .icns

```bash
cd /Users/ryan/meta-agent/scripts/crm/assets/icons
mkdir -p app-orbit.iconset app-lighthouse.iconset

for s in 16 32 64 128 256 512; do
  sips -z $s $s app-orbit-1024.png --out app-orbit.iconset/icon_${s}x${s}.png >/dev/null
  sips -z $s $s app-lighthouse-1024.png --out app-lighthouse.iconset/icon_${s}x${s}.png >/dev/null
done

cp app-orbit-1024.png app-orbit.iconset/icon_512x512@2x.png
cp app-lighthouse-1024.png app-lighthouse.iconset/icon_512x512@2x.png

iconutil -c icns app-orbit.iconset
iconutil -c icns app-lighthouse.iconset
```

Output files:

- app-orbit.icns
- app-lighthouse.icns

## Apply to an app bundle

1. Right-click your app -> Show Package Contents.
2. Put the `.icns` file inside `Contents/Resources/`.
3. Edit `Contents/Info.plist` and set `CFBundleIconFile` to icon file name (without `.icns`).
4. Refresh icon cache or restart Finder if the icon does not update immediately.
