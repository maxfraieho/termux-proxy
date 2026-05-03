#!/data/data/com.termux/files/usr/bin/bash
# modules/tor.sh — Tor + obfs4 SOCKS5 проксі на порту TOR_PORT (9050)
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

TORRC="$PREFIX/etc/tor/torrc"
SVC_DIR="$PREFIX/var/service/tor"

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
echo " Tor + obfs4  (port $TOR_PORT)"
echo "════════════════════════════════════════"

# ── 1. Пакети ────────────────────────────────────────────────
echo; echo "[1/4] Packages..."

pkgs=()
[ "$HAS_TOR"   = "no" ] && pkgs+=(tor)
[ "$HAS_OBFS4" = "no" ] && pkgs+=(obfs4proxy)

if [ "${#pkgs[@]}" -gt 0 ]; then
    if pkg install -y "${pkgs[@]}"; then
        echo "  ✅  installed: ${pkgs[*]}"
    else
        echo "❌  pkg install failed: ${pkgs[*]}"
        exit 1
    fi
else
    echo "  ✅  tor and obfs4proxy present"
fi

# ── 2. torrc ─────────────────────────────────────────────────
echo; echo "[2/4] torrc..."

mkdir -p "$PREFIX/var/lib/tor" "$PREFIX/var/log/tor"

# Зберігаємо існуючі bridges і робимо бекап перед перезаписом
existing_bridges=""
if [ -f "$TORRC" ]; then
    existing_bridges=$(grep '^Bridge obfs4' "$TORRC" || true)
    cp "$TORRC" "$TORRC.bak"
    echo "  💾  backup: $TORRC.bak"
fi

# Звільнити порт якщо зайнятий
kill "$(lsof -t -i:"$TOR_PORT" 2>/dev/null)" 2>/dev/null || true

# Записуємо базовий конфіг
cat > "$TORRC" << TOREOF
SOCKSPort 127.0.0.1:$TOR_PORT
Log notice file $PREFIX/var/log/tor/notices.log
DataDirectory $PREFIX/var/lib/tor
ExitPolicy reject *:*
UseBridges 1
ClientTransportPlugin obfs4 exec $PREFIX/bin/obfs4proxy

# ⚠️  ДОДАЙТЕ МОСТИ ТУТ:
# https://bridges.torproject.org/  або  @GetBridgesBot → /bridges obfs4
#
# Формат:
# Bridge obfs4 <IP>:<PORT> <FINGERPRINT> cert=<CERT> iat-mode=0
TOREOF

# Відновлюємо збережені bridges — не стираємо те, що вже є
if [ -n "$existing_bridges" ]; then
    printf '%s\n' "$existing_bridges" >> "$TORRC"
    bridge_count=$(printf '%s\n' "$existing_bridges" | wc -l | tr -d ' ')
    echo "  ✅  torrc written, $bridge_count bridge(s) preserved"
else
    echo "  ✅  torrc written (port $TOR_PORT)"
    echo "  ⚠️   No bridges — add via: deploy.sh → [5]"
fi

# ── 3. Сервіс ────────────────────────────────────────────────
echo; echo "[3/4] Service..."

_ensure_sv

if [ -d "$SVC_DIR" ]; then
    sv down "$SVC_DIR" 2>/dev/null || true
fi

mkdir -p "$SVC_DIR/log"

cat > "$SVC_DIR/run" << RUNEOF
#!/data/data/com.termux/files/usr/bin/sh
exec tor -f $TORRC 2>&1
RUNEOF
chmod +x "$SVC_DIR/run"

sv-enable tor 2>/dev/null || true
sv up "$SVC_DIR" 2>/dev/null || true
sleep 3

if sv status "$SVC_DIR" 2>/dev/null | grep -q '^run:'; then
    echo "  ✅  tor running"
else
    echo "  ⚠️   Tor likely waiting for bridges — add them then restart"
    echo "       sv down $SVC_DIR && sv up $SVC_DIR"
fi

# ── 4. Boot script ───────────────────────────────────────────
echo; echo "[4/4] Boot script..."

BOOT="$HOME_DIR/.termux/boot/start-services.sh"
if [ -f "$BOOT" ]; then
    if ! grep -q 'var/service/tor' "$BOOT"; then
        printf 'sv up "%s"\n' "$SVC_DIR" >> "$BOOT"
        echo "  ✅  added to boot script"
    else
        echo "  ✅  already in boot script"
    fi
else
    echo "  ⚠️   boot script not found — run modules/boot.sh first"
fi

# ── Підсумок ─────────────────────────────────────────────────
echo
echo "════════════════════════════════════════"
echo " Tor ready  (after adding bridges)"
echo "  SOCKS5:  127.0.0.1:$TOR_PORT"
echo "  Bridges: ./deploy.sh → [5] Update Tor bridges"
echo "  Logs:    tail -f $PREFIX/var/log/tor/notices.log"
echo "════════════════════════════════════════"
