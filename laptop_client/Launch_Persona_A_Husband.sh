#!/usr/bin/env bash
# 🚀 Launch Persona A (Husband) Swiss Survey Browser
# Isolated Profile with Swiss Proxy Channel A (100.66.97.93:1080 / 8888)

PROFILE_DIR="$HOME/.config/survey-profiles/persona_a_husband"
mkdir -p "$PROFILE_DIR"

export TZ="Europe/Zurich"
export LANG="de_CH.UTF-8"

# Detect browser (google-chrome, chromium, or brave)
CHROME_BIN=""
for b in google-chrome google-chrome-stable chromium-browser chromium brave-browser brave; do
    if command -v "$b" >/dev/null 2>&1; then
        CHROME_BIN="$b"
        break
    fi
done

if [ -z "$CHROME_BIN" ]; then
    echo "❌ Chrome/Chromium/Brave not found in PATH."
    exit 1
fi

echo "🟢 Launching Persona A (Husband) on Swiss Proxy (100.66.97.93:1080)..."
exec "$CHROME_BIN" \
    --user-data-dir="$PROFILE_DIR" \
    --proxy-server="socks5://100.66.97.93:1080" \
    --lang="de-CH" \
    --force-webrtc-ip-handling-policy=disable_non_proxied_udp \
    --disable-reading-from-canvas \
    --window-size=1920,1080 \
    --no-first-run \
    --no-default-browser-check \
    "https://ipinfo.io/json"
