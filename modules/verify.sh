#!/data/data/com.termux/files/usr/bin/bash
# modules/verify.sh — перевірка всіх сервісів системи
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

echo
echo "════════════════════════════════════════"
echo " Service Verification"
echo "════════════════════════════════════════"
echo

_ok()   { printf "  ✅  %-28s %s\n" "$1" "$2"; }
_warn() { printf "  ⚠️   %-28s %s\n" "$1" "$2"; }
_fail() { printf "  ❌  %-28s %s\n" "$1" "$2"; }

_svc_check() {
    local name="$1" port="$2" has_pkg="$3"

    if [ "$has_pkg" = "no" ]; then
        _fail "$name" "package not installed"
        return
    fi

    local svc_path="$PREFIX/var/service/$name"
    if [ ! -d "$svc_path" ]; then
        _fail "$name" "service not configured (run deploy.sh)"
        return
    fi

    local status
    status=$(sv status "$svc_path" 2>/dev/null | grep -oE '^(run|down)' || echo "unknown")

    if [ "$status" = "run" ]; then
        _ok "$name" "running  port $port"
    else
        _fail "$name" "not running ($status)"
    fi
}

# ── Сервіси ──────────────────────────────────────────────────
_svc_check "sshd"     "$SSH_PORT"     "$HAS_SSH"
_svc_check "tor"      "$TOR_PORT"     "$HAS_TOR"
_svc_check "ts-proxy" "$TSPROXY_PORT" "$HAS_TSPROXY"

echo

# ── Tor bridges ──────────────────────────────────────────────
if [ "$BRIDGES_COUNT" -gt 0 ]; then
    _ok "Tor bridges" "$BRIDGES_COUNT configured"
else
    _warn "Tor bridges" "none — Tor may not connect outside CH"
fi

# ── Termux:Boot ──────────────────────────────────────────────
if [ "$BOOT_SCRIPT" = "yes" ]; then
    _ok "Termux:Boot script" "present"
else
    _warn "Termux:Boot script" "missing — services won't auto-start"
fi

# ── Tailscale ────────────────────────────────────────────────
if [ "$TS_IP" != "unknown" ] && [ -n "$TS_IP" ]; then
    _ok "Tailscale" "$TS_IP"
else
    _warn "Tailscale" "IP not detected"
fi

echo

# ── Опціональний тест проксі ─────────────────────────────────
if [ "$HAS_CURL" = "yes" ]; then
    echo "  Test which proxy?"
    echo "  [1] ts-proxy (port $TSPROXY_PORT)"
    echo "  [2] Tor      (port $TOR_PORT)"
    echo "  [3] Skip"
    printf "  Choice: "
    read -r _t

    _run_test() {
        local target="$1" label="$2"
        echo "  Testing $label via $target ..."
        local resp
        resp=$(curl --socks5-hostname "$target" \
               -s --max-time 15 https://check.torproject.org/api/ip 2>&1 || true)
        if echo "$resp" | grep -q '"IsTor":true'; then
            _ok "$label test" "IsTor:true — working"
        elif echo "$resp" | grep -q '"IP"'; then
            _ok "$label test" "connected (not via Tor exit)"
            echo "      Response: $resp"
        else
            _fail "$label test" "no response: $resp"
        fi
    }

    case "$_t" in
        1) _run_test "$TS_IP:$TSPROXY_PORT" "ts-proxy" ;;
        2) _run_test "127.0.0.1:$TOR_PORT"  "Tor" ;;
        *) echo "  Skipped." ;;
    esac
fi

echo
echo "  SSH access:  ssh -p $SSH_PORT $TERMUX_USER@$TS_IP"
echo "  ts-proxy:    socks5://$TS_IP:$TSPROXY_PORT  (PinchTab/Chrome)"
echo "  Tor:         socks5://127.0.0.1:$TOR_PORT"
echo "  Logs:        tail -f $PREFIX/var/log/tor/notices.log"
echo
