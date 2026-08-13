#!/bin/bash
# watchdog_tablet.sh v2.0 — Tailscale Node Monitor for Swiss Tablet (100.100.74.9)
# Cron: */5 * * * * /bin/bash /home/ubuntu/termux-proxy/watchdog_tablet.sh
# Location: /home/ubuntu/termux-proxy/watchdog_tablet.sh

TABLET_IP="100.100.74.9"
LOG_FILE="/home/ubuntu/termux-proxy/tablet_monitor.log"
BOT_TOKEN="8024885984:AAHy-NAiWEfJAGmjIgE95-g_-p3X83-zAuA"
CHAT_ID_FILE="/home/ubuntu/termux-proxy/.watchdog_chat_id"
STATE_FILE="/home/ubuntu/termux-proxy/.watchdog_state"
COUNT_FILE="/home/ubuntu/termux-proxy/.watchdog_count"

MAX_LOG_LINES=500
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# ── Log rotation ──────────────────────────────────────────────────────────────
rotate_log() {
    if [ -f "$LOG_FILE" ]; then
        local lines
        lines=$(wc -l < "$LOG_FILE")
        if [ "$lines" -gt "$MAX_LOG_LINES" ]; then
            tail -n $((MAX_LOG_LINES / 2)) "$LOG_FILE" > "${LOG_FILE}.tmp"
            mv "${LOG_FILE}.tmp" "$LOG_FILE"
        fi
    fi
}

# ── Telegram Alert ─────────────────────────────────────────────────────────────
send_tg_alert() {
    local message="$1"
    local chat_id=""

    if [ -f "$CHAT_ID_FILE" ]; then
        chat_id=$(cat "$CHAT_ID_FILE")
    fi

    if [ -n "$chat_id" ] && [ -n "$BOT_TOKEN" ]; then
        curl -s -X POST \
            "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -d "chat_id=${chat_id}" \
            -d "text=${message}" \
            -d "parse_mode=HTML" \
            --max-time 10 > /dev/null 2>&1
    fi
}

# ── Check Tailscale encrypted tunnel reachability ──────────────────────────────
check_tailscale_ping() {
    # tailscale ping returns 0 if reachability check succeeds
    tailscale ping -c 3 "$TABLET_IP" > /tmp/ts_ping_out.txt 2>&1
    local ret=$?
    if [ $ret -eq 0 ] && grep -qi "pong" /tmp/ts_ping_out.txt; then
        return 0
    else
        return 1
    fi
}

# ── Check swiss-proxy.service status ──────────────────────────────────────────
check_proxy_service() {
    systemctl is-active swiss-proxy.service > /dev/null 2>&1
    return $?
}

# ── Main ──────────────────────────────────────────────────────────────────────
rotate_log

TS_OK=false
if check_tailscale_ping; then
    TS_OK=true
fi

PREV_STATE=""
[ -f "$STATE_FILE" ] && PREV_STATE=$(cat "$STATE_FILE")

if $TS_OK; then
    CURRENT_STATE="OK"
    COUNT=0
    [ -f "$COUNT_FILE" ] && COUNT=$(cat "$COUNT_FILE")
    COUNT=$((COUNT + 1))
    echo "$COUNT" > "$COUNT_FILE"

    if [ "$PREV_STATE" != "OK" ]; then
        echo "[$TIMESTAMP] ✅ RESTORED — Tailscale ping to $TABLET_IP OK" >> "$LOG_FILE"
        send_tg_alert "🟢 <b>Swiss Tablet</b> (${TABLET_IP}) ВІДНОВЛЕНО
✅ Tailscale Tunnel: OK
🕒 ${TIMESTAMP}"
    elif [ $((COUNT % 12)) -eq 0 ]; then
        echo "[$TIMESTAMP] ✅ OK — Tailscale ping to $TABLET_IP OK (heartbeat)" >> "$LOG_FILE"
    fi
else
    CURRENT_STATE="FAIL"
    PING_DETAILS=$(cat /tmp/ts_ping_out.txt 2>/dev/null | head -2 | tr '\n' ' ')
    echo "[$TIMESTAMP] ❌ ALERT — Tailscale ping to $TABLET_IP FAILED: $PING_DETAILS" >> "$LOG_FILE"

    if [ "$PREV_STATE" != "FAIL" ]; then
        send_tg_alert "🔴 <b>Swiss Tablet НЕДОСТУПНИЙ</b> (${TABLET_IP})
❌ Tailscale Tunnel: FAIL
ℹ️ <code>${PING_DETAILS}</code>
🕒 ${TIMESTAMP}"
    fi
fi

echo "$CURRENT_STATE" > "$STATE_FILE"

# Restart swiss-proxy.service if it's not active
if ! check_proxy_service; then
    echo "[$TIMESTAMP] ⚠️ swiss-proxy.service dead — restarting..." >> "$LOG_FILE"
    systemctl restart swiss-proxy.service 2>/dev/null
    sleep 2
    if check_proxy_service; then
        echo "[$TIMESTAMP] ✅ swiss-proxy.service restarted OK" >> "$LOG_FILE"
    else
        echo "[$TIMESTAMP] ❌ swiss-proxy.service restart FAILED" >> "$LOG_FILE"
        send_tg_alert "🔴 <b>Oracle Proxy</b>: swiss-proxy.service FAILED to restart at ${TIMESTAMP}"
    fi
fi

rm -f /tmp/ts_ping_out.txt
exit 0
