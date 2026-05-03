#!/data/data/com.termux/files/usr/bin/bash
# modules/bridges.sh — управління obfs4 мостами для Tor
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

TORRC="$PREFIX/etc/tor/torrc"

echo
echo "════════════════════════════════════════"
echo " Tor Bridges Manager"
echo "════════════════════════════════════════"

# ── 1. Перевірки ─────────────────────────────────────────────
echo; echo "[1/5] Prerequisites..."

if [ ! -f "$TORRC" ]; then
    echo "❌ torrc not found. Run: deploy.sh → [3] Tor proxy"
    exit 1
fi

if ! command -v obfs4proxy &>/dev/null; then
    echo "⚠️  obfs4proxy not found — install with: pkg install obfs4proxy"
fi

# ── 2. Поточні мости ─────────────────────────────────────────
echo; echo "[2/5] Current bridges..."

# grep -c повертає exit 1 якщо 0 збігів → || true обов'язково
existing_count=$(grep -c '^Bridge obfs4' "$TORRC" || true)
mode="replace"

if [ "$existing_count" -gt 0 ]; then
    echo "  Found $existing_count bridge(s):"
    grep '^Bridge obfs4' "$TORRC" || true
    echo
    printf "  [R]eplace / [A]dd more / [K]eep and exit: "
    read -r _choice
    case "${_choice,,}" in
        r) mode="replace" ;;
        a) mode="add"     ;;
        k) echo "  Keeping bridges. Exiting."; exit 0 ;;
        *) echo "  Invalid. Exiting."; exit 1 ;;
    esac
else
    echo "  No bridges configured."
    mode="replace"
fi

# ── 3. Отримати мости від користувача ────────────────────────
echo; echo "[3/5] Paste bridges..."
echo "  ════════════════════════════════════"
echo "  Get bridges from:"
echo "    https://bridges.torproject.org/"
echo "    Telegram: @GetBridgesBot → /bridges obfs4"
echo
echo "  Paste lines (each starts with 'Bridge obfs4')."
echo "  Press Ctrl+D when done."
echo "  ════════════════════════════════════"

# Читаємо до EOF (Ctrl+D), не перериваємо на порожніх рядках
new_bridges=()
while IFS= read -r line || [ -n "$line" ]; do
    [ -z "$line" ] && continue
    if [[ "$line" != Bridge\ obfs4* ]]; then
        echo "  ⚠️  Unexpected format (including anyway): ${line:0:60}"
    fi
    new_bridges+=("$line")
done

if [ "${#new_bridges[@]}" -eq 0 ]; then
    echo "❌ No bridges provided. No changes made."
    exit 1
fi

# ── 4. Оновити torrc ─────────────────────────────────────────
echo; echo "[4/5] Updating torrc..."

cp "$TORRC" "$TORRC.bak"
echo "  💾  backup: $TORRC.bak"

if [ "$mode" = "replace" ]; then
    sed -i '/^Bridge obfs4/d' "$TORRC"
    echo "  🗑  removed old bridges"
fi

# Дедуплікація: додаємо лише відсутні рядки
# Використовуємо printf >> (не sed /a\ з multiline змінною)
added=0
for bridge in "${new_bridges[@]}"; do
    if grep -qxF "$bridge" "$TORRC" 2>/dev/null; then
        echo "  ⏩  duplicate, skipping: ${bridge:0:55}..."
    else
        printf '%s\n' "$bridge" >> "$TORRC"
        echo "  ➕  added: ${bridge:0:55}..."
        (( added++ )) || true
    fi
done

echo "  ✅  $added bridge(s) added"

# ── 5. Перезапустити Tor ─────────────────────────────────────
echo; echo "[5/5] Restarting Tor..."

SVC_DIR="$PREFIX/var/service/tor"
if command -v sv &>/dev/null && [ -d "$SVC_DIR" ]; then
    sv down "$SVC_DIR" 2>/dev/null || true
    sleep 1
    sv up "$SVC_DIR" 2>/dev/null || true
    sleep 3
    if sv status "$SVC_DIR" 2>/dev/null | grep -q '^run:'; then
        echo "  ✅  Tor restarted"
    else
        echo "  ⚠️   check: sv status $SVC_DIR"
    fi
else
    echo "  ⚠️   sv not found — restart manually: tor -f $TORRC &"
fi

# Опціональний тест
if [ "$HAS_CURL" = "yes" ]; then
    printf "\n  Test proxy now? (y/N): "
    read -r _t
    if [[ "${_t,,}" == "y" ]]; then
        resp=$(curl --socks5-hostname "127.0.0.1:$TOR_PORT" \
               -s --max-time 20 https://check.torproject.org/api/ip 2>&1 || true)
        if echo "$resp" | grep -q '"IsTor":true'; then
            echo "  ✅  Proxy working — IsTor:true"
        else
            echo "  ❌  Test failed: $resp"
            echo "     Check: tail -20 $PREFIX/var/log/tor/notices.log"
        fi
    fi
fi

echo
echo "════════════════════════════════════════"
echo " Done. $added bridge(s) added."
echo "  torrc:  $TORRC"
echo "  backup: $TORRC.bak"
echo "  logs:   tail -f $PREFIX/var/log/tor/notices.log"
echo "════════════════════════════════════════"
