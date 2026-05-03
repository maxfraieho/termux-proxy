#!/data/data/com.termux/files/usr/bin/bash
# restart-proxy.sh — restarts ts-proxy (microsocks via runit)
# Called by: local watchdog, n8n SSH node, manual

LOCK_FILE="/data/data/com.termux/files/usr/tmp/restart-proxy.lock"
exec 200>"$LOCK_FILE"
flock -n 200 || { echo "[SKIP] restart-proxy already running"; exit 0; }
PREFIX="/data/data/com.termux/files/usr"
HOME_DIR="/data/data/com.termux/files/home"
SVC="$PREFIX/var/service/ts-proxy"
LOG="$HOME_DIR/logs/restart-proxy.log"
mkdir -p "$HOME_DIR/logs"

# Fix for runit 'unable to open current directory' — sv needs valid CWD
cd "$HOME_DIR" || cd /

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts)] === restart-proxy.sh triggered ===" >> "$LOG"

# 1. Stop runit supervision first
echo "[$(ts)] Stopping runit supervision..." >> "$LOG"
sv down "$SVC" >> "$LOG" 2>&1 || true

# 2. Force-kill ALL microsocks processes (handles zombies and duplicates)
echo "[$(ts)] Killing all microsocks processes..." >> "$LOG"
pkill -x microsocks >> "$LOG" 2>&1 || true
sleep 1
pkill -9 -x microsocks >> "$LOG" 2>&1 || true

# 3. Wait until no microsocks remains
waited=0
while pgrep -x microsocks > /dev/null 2>&1; do
    sleep 1
    waited=$((waited + 1))
    if [ "$waited" -ge 5 ]; then
        echo "[$(ts)] WARNING: microsocks still alive after ${waited}s kill" >> "$LOG"
        break
    fi
done
echo "[$(ts)] microsocks cleared after ${waited}s" >> "$LOG"

# 4. Restart via runit
echo "[$(ts)] Starting ts-proxy via runit..." >> "$LOG"
sv up "$SVC" >> "$LOG" 2>&1 || true

# 5. Wait for port to actually open (up to 15s)
PROXY_HOST="100.100.74.9"
PROXY_PORT="9888"
waited=0
while [ "$waited" -lt 15 ]; do
    if bash -c "exec 3<>/dev/tcp/$PROXY_HOST/$PROXY_PORT" 2>/dev/null; then
        break
    fi
    sleep 1
    waited=$((waited + 1))
done

# 6. Verify
if bash -c "exec 3<>/dev/tcp/$PROXY_HOST/$PROXY_PORT" 2>/dev/null; then
    echo "[$(ts)] ts-proxy UP on $PROXY_HOST:$PROXY_PORT (after ${waited}s)" >> "$LOG"
    echo "OK: ts-proxy running"
else
    echo "[$(ts)] FAIL: ts-proxy not responding on $PROXY_HOST:$PROXY_PORT" >> "$LOG"
    echo "FAIL: ts-proxy not running"
fi

# 7. Restart sshd if down
if ! sv status "$PREFIX/var/service/sshd" 2>/dev/null | grep -q '^run:'; then
    echo "[$(ts)] sshd is down — restarting..." >> "$LOG"
    sv up "$PREFIX/var/service/sshd" >> "$LOG" 2>&1 || true
    sleep 2
    echo "[$(ts)] sshd restart attempted" >> "$LOG"
fi

echo "[$(ts)] === done ===" >> "$LOG"
