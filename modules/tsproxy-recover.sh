#!/data/data/com.termux/files/usr/bin/bash
# modules/tsproxy-recover.sh — жорстке відновлення ts-proxy з перевіркою SOCKS5
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

SVC_DIR="$PREFIX/var/service/ts-proxy"
HOST="$TS_IP"
PORT="$TSPROXY_PORT"
RECOVERY_CYCLES="${RECOVERY_CYCLES:-3}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-2}"

if [ -z "$HOST" ] || [ "$HOST" = "unknown" ]; then
    echo "❌ TS_IP is empty in $CONFIG"
    exit 1
fi

if [ ! -d "$SVC_DIR" ]; then
    echo "❌ Service not configured: $SVC_DIR"
    exit 1
fi

socksv5_ping() {
    local hex
    hex=$(
        bash -lc '
            exec 3<>/dev/tcp/'"$HOST"'/'"$PORT"' || exit 1
            printf "\x05\x01\x00" >&3
            dd bs=1 count=2 <&3 2>/dev/null | od -An -t x1
        ' 2>/dev/null | tr -d '[:space:]'
    ) || return 1

    [ "$hex" = "0500" ]
}

echo "════════════════════════════════════════"
echo " ts-proxy recovery"
echo " Host: $HOST"
echo " Port: $PORT"
echo " Cycles: $RECOVERY_CYCLES"
echo "════════════════════════════════════════"

for cycle in $(seq 1 "$RECOVERY_CYCLES"); do
    echo "[cycle $cycle/$RECOVERY_CYCLES] Restarting service..."
    sv down "$SVC_DIR" 2>/dev/null || true
    sleep 1
    pkill -f "microsocks -i $HOST -p $PORT" 2>/dev/null || true
    sleep 1
    sv up "$SVC_DIR"

    echo "[cycle $cycle/$RECOVERY_CYCLES] Verifying SOCKS5..."
    for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
        if socksv5_ping; then
            echo "✅ SOCKS5 OK on $HOST:$PORT"
            exit 0
        fi

        echo "  cycle $cycle attempt $attempt/$MAX_ATTEMPTS failed"
        sleep "$SLEEP_BETWEEN"
    done
done

echo "❌ SOCKS5 did not recover on $HOST:$PORT after $RECOVERY_CYCLES cycles"
exit 1
