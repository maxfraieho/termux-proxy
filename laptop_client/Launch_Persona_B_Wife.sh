#!/usr/bin/env bash
# 🚀 Launch Persona B (Wife) Swiss Survey Browser
# Isolated Profile with Swiss Proxy Channel B (100.66.97.93:1081 / 8889)

PROFILE_DIR="$HOME/.config/survey-profiles/persona_b_wife"
mkdir -p "$PROFILE_DIR"

export TZ="Europe/Zurich"
export LANG="de_CH.UTF-8"

# Detect browser
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

echo "🟢 Launching Persona B (Wife) on Swiss Proxy (100.66.97.93:1081)..."
exec "$CHROME_BIN" \
    --user-data-dir="$PROFILE_DIR" \
    --proxy-server="socks5://100.66.97.93:1081" \
    --lang="de-CH" \
    --force-webrtc-ip-handling-policy=disable_non_proxied_udp \
    --disable-reading-from-canvas \
    --window-size=1536,864 \
    --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36" \
    --no-first-run \
    --no-default-browser-check \
    "https://ipinfo.io/json"
