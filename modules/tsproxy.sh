#!/data/data/com.termux/files/usr/bin/bash
# modules/tsproxy.sh — стабільний SOCKS5 через Tailscale для PinchTab/Chrome
# Порт: TSPROXY_PORT (9888) — окремий від Tor (9050), немає конфлікту
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

SVC_DIR="$PREFIX/var/service/ts-proxy"
LOG_DIR="$PREFIX/var/log/sv/ts-proxy"

# ── Ensure termux-services ────────────────────────────────────
_ensure_sv() {
    if ! command -v sv >/dev/null 2>&1; then
        echo "  Installing termux-services..."
        if ! pkg install -y termux-services; then
            echo "❌  Failed to install termux-services"
            exit 1
        fi
        echo "  ✅  termux-services installed"
    fi
    if ! pgrep runsvdir >/dev/null 2>&1; then
        nohup runsvdir "$PREFIX/var/service" >/dev/null 2>&1 &
        sleep 1
    fi
}

echo
echo "════════════════════════════════════════"
echo " ts-proxy — SOCKS5 via Tailscale"
echo " Port: $TSPROXY_PORT  (Chrome/PinchTab)"
echo "════════════════════════════════════════"

# ── 1. Перевірки ─────────────────────────────────────────────
echo; echo "[1/5] Prerequisites..."

if [ "$TS_IP" = "unknown" ] || [ -z "$TS_IP" ]; then
    echo "❌ Tailscale IP not detected. Is Tailscale running?"
    exit 1
fi
echo "  ✅  Tailscale IP: $TS_IP"

# ── 2. Залежності ────────────────────────────────────────────
echo; echo "[2/5] Dependencies..."

if ! command -v microsocks >/dev/null 2>&1; then
    if pkg install -y microsocks; then
        echo "  ✅  installed: microsocks"
    else
        echo "❌  pkg install failed: microsocks"
        exit 1
    fi
else
    echo "  ✅  microsocks present"
fi

# ── 3. Бекенд ────────────────────────────────────────────────
echo; echo "[3/5] Backend..."
echo "  Using microsocks bound to Tailscale IP only"

# ── 4. Сервіс ────────────────────────────────────────────────
echo; echo "[4/5] Configuring service..."

_ensure_sv

if [ -d "$SVC_DIR" ]; then
    sv down "$SVC_DIR" 2>/dev/null || true
    sleep 1
fi

mkdir -p "$SVC_DIR/log" "$LOG_DIR"

cat > "$SVC_DIR/run" <<'RUNEOF'
#!/data/data/com.termux/files/usr/bin/sh
pkill -x microsocks 2>/dev/null || true
pkill -9 -x microsocks 2>/dev/null || true
i=0
while [ $i -lt 10 ]; do
    bash -c "exec 3<>/dev/tcp/TSPROXY_IP/TSPROXY_PORT_PLACEHOLDER" 2>/dev/null || break
    sleep 1
    i=$((i+1))
done
exec microsocks -i TSPROXY_IP -p TSPROXY_PORT_PLACEHOLDER 2>&1
RUNEOF
chmod +x "$SVC_DIR/run"
sed -i "s/TSPROXY_IP/$TS_IP/g; s/TSPROXY_PORT_PLACEHOLDER/$TSPROXY_PORT/g" "$SVC_DIR/run"

cat > "$SVC_DIR/finish" <<'FINEOF'
#!/data/data/com.termux/files/usr/bin/sh
echo "$(date +%Y-%m-%dT%H:%M:%S) ts-proxy EXIT code=$1 signal=$2" \
  >> /data/data/com.termux/files/home/logs/ts-proxy-exit.log
FINEOF
chmod +x "$SVC_DIR/finish"

cat > "$SVC_DIR/log/run" <<LOGEOF
#!/data/data/com.termux/files/usr/bin/sh
exec svlogd -tt $LOG_DIR
LOGEOF
chmod +x "$SVC_DIR/log/run"

sv-enable ts-proxy 2>/dev/null || true
rm -f "$SVC_DIR/down" 2>/dev/null || true  # sv-enable has -u/-z bug
sv up "$SVC_DIR" 2>/dev/null || true
sleep 2

if sv status "$SVC_DIR" 2>/dev/null | grep -q '^run:'; then
    echo "  ✅  ts-proxy running on $TS_IP:$TSPROXY_PORT"
else
    echo "  ⚠️   check: sv status $SVC_DIR"
fi

# ── 5. Boot script ───────────────────────────────────────────
echo; echo "[5/5] Boot script..."

BOOT="$HOME_DIR/.termux/boot/start-services.sh"
if [ -f "$BOOT" ]; then
    if ! grep -q 'ts-proxy' "$BOOT"; then
        printf 'sv up "%s"\n' "$SVC_DIR" >> "$BOOT"
        echo "  ✅  added to boot script"
    else
        echo "  ✅  already in boot script"
    fi
else
    echo "  ⚠️   boot script not found — run modules/boot.sh first"
fi

echo
echo "════════════════════════════════════════"
echo " ts-proxy ready"
echo
echo "  Remote:   $TS_IP:$TSPROXY_PORT   (від MacBook через Tailscale)"
echo
echo "  Chrome / PinchTab flags:"
echo "  --proxy-server=\"socks5://$TS_IP:$TSPROXY_PORT\""
echo "  --host-resolver-rules=\"MAP * ~NOTFOUND, EXCLUDE localhost\""
echo
echo "  Logs: tail -f $LOG_DIR/current"
echo "  Test: curl --socks5-hostname $TS_IP:$TSPROXY_PORT https://ipinfo.io"
echo "════════════════════════════════════════"
