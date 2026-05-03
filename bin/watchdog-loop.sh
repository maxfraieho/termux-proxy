#!/data/data/com.termux/files/usr/bin/bash
# watchdog-loop.sh — monitors ts-proxy (microsocks) and sshd, auto-restarts
# Runit service: local-watchdog
# NOTE: microsocks binds to 100.100.74.9:9888 (Tailscale IP), NOT 127.0.0.1

PREFIX="/data/data/com.termux/files/usr"
HOME_DIR="/data/data/com.termux/files/home"
PROXY_HOST="100.100.74.9"    # Tailscale IP — microsocks binds here
PROXY_PORT="9888"
CHECK_INTERVAL=30
COOLDOWN=300
FLAG_FILE="$PREFIX/tmp/watchdog_proxy_down.flag"
LAST_ALERT_FILE="$PREFIX/tmp/watchdog_last_alert"
LOG="$HOME_DIR/logs/watchdog-loop.log"

mkdir -p "$HOME_DIR/logs"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $1" | tee -a "$LOG"; }

notify() {
    local msg="$1"
    if [ -f "$LAST_ALERT_FILE" ]; then
        local last now diff
        last=$(cat "$LAST_ALERT_FILE")
        now=$(date +%s)
        diff=$(( now - last ))
        if [ "$diff" -lt "$COOLDOWN" ]; then
            log "Cooldown active (${diff}s < ${COOLDOWN}s), skipping notify"
            return
        fi
    fi
    date +%s > "$LAST_ALERT_FILE"
    "$HOME_DIR/bin/tg-notify.sh" "$msg" &
}

check_port() {
    # microsocks binds to Tailscale IP, not localhost
    bash -c "echo > /dev/tcp/$PROXY_HOST/$PROXY_PORT" 2>/dev/null
}

check_sshd() {
    sv status "$PREFIX/var/service/sshd" 2>/dev/null | grep -q '^run:'
}

log "=== watchdog-loop started (interval=${CHECK_INTERVAL}s, cooldown=${COOLDOWN}s) ==="
log "Monitoring: $PROXY_HOST:$PROXY_PORT (ts-proxy/microsocks)"

while true; do
    # --- ts-proxy check ---
    if check_port; then
        if [ -f "$FLAG_FILE" ]; then
            rm -f "$FLAG_FILE"
            log "ts-proxy RECOVERED on $PROXY_HOST:$PROXY_PORT"
            notify "✅ [tab-s8-ultra] ts-proxy RECOVERED on port $PROXY_PORT"
        fi
    else
        if [ ! -f "$FLAG_FILE" ]; then
            touch "$FLAG_FILE"
            log "ts-proxy DOWN on $PROXY_HOST:$PROXY_PORT — restarting..."
            notify "⚠️ [tab-s8-ultra] ts-proxy DOWN — auto-restarting..."

            "$HOME_DIR/bin/restart-proxy.sh" >> "$LOG" 2>&1

            sleep 5

            if check_port; then
                rm -f "$FLAG_FILE"
                log "ts-proxy restarted successfully"
                notify "✅ [tab-s8-ultra] ts-proxy restarted OK"
            else
                log "ts-proxy STILL down after restart"
                notify "❌ [tab-s8-ultra] ts-proxy STILL DOWN after restart — manual intervention needed"
            fi
        else
            log "ts-proxy still down (flag exists, restart already attempted)"
        fi
    fi

    # --- sshd check (always, independent) ---
    if ! check_sshd; then
        log "sshd DOWN — restarting via sv..."
        sv up "$PREFIX/var/service/sshd" >> "$LOG" 2>&1 || true
        sleep 3
        if check_sshd; then
            log "sshd restarted OK"
            notify "⚠️ [tab-s8-ultra] sshd was down — auto-restarted OK"
        else
            log "sshd STILL down after restart"
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
