#!/bin/bash

#═══════════════════════════════════════════════════════════════════
#  TAILSCALE VPN/PROXY WATCHDOG FOR DEBIAN
#  Моніторинг Termux SOCKS5 Proxy через Tailscale мережу
#═══════════════════════════════════════════════════════════════════

# ============== LOCKFILE (flock) ==============
LOCK_FILE="/var/lock/watchdog-proxy.lock"
exec 200>"$LOCK_FILE" || { echo "$(date -Is) watchdog: cannot open lock file" >> /opt/watchdog/logs/watchdog.log; exit 1; }
flock -n 200 || { echo "$(date -Is) watchdog: already running, exit" >> /opt/watchdog/logs/watchdog.log; exit 0; }

# ============== КОНФІГУРАЦІЯ ==============

BASE_DIR="/opt/watchdog"
LOG_DIR="${BASE_DIR}/logs"

# Підтягуємо .env якщо існує (для REMINDER_EVERY_ERRORS та інших override)
[ -f "${BASE_DIR}/.env" ] && source "${BASE_DIR}/.env"

PROXY_HOST="${PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${PROXY_PORT:-1080}"
PROXY_TYPE="${PROXY_TYPE:-socks5}"
PROXY_URL="socks5://${PROXY_HOST}:${PROXY_PORT}"

WORKER_URL="${WORKER_URL:-https://watchdog-notifier.maxfraieho.workers.dev/}"
TELEGRAM_TOKEN="${TELEGRAM_TOKEN:-8508516661:AAEQBWvlBk3v62nd5ut3ei70TPFJTkV9LMs}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-6412868393}"
N8N_WEBHOOK_URL="${N8N_WEBHOOK_URL:-https://n8n.exodus.pp.ua/webhook/proxy-watchdog}"
MACRODROID_WEBHOOK_URL="${MACRODROID_WEBHOOK_URL:-https://trigger.macrodroid.com/YOUR_DEVICE_ID/wake_tailscale}"

CHECK_TIMEOUT="${CHECK_TIMEOUT:-10}"
MAX_RETRIES="${MAX_RETRIES:-3}"
RETRY_DELAY="${RETRY_DELAY:-5}"
TEST_URL="${TEST_URL:-http://checkip.amazonaws.com/}"
REMINDER_EVERY_ERRORS="${REMINDER_EVERY_ERRORS:-60}"
PRIMARY_EXIT_NODE_IP="${PRIMARY_EXIT_NODE_IP:-${EXPECTED_EXIT_NODE_IP:-100.87.198.99}}"
FALLBACK_EXIT_NODES="${FALLBACK_EXIT_NODES:-100.100.74.9}"
ENABLE_DIRECT_FALLBACK="${ENABLE_DIRECT_FALLBACK:-false}"
EXPECTED_EXIT_NODE_IP="$PRIMARY_EXIT_NODE_IP"

# Dual Persona Proxy Channels
PROXY_PORT_A="${PROXY_PORT_A:-1080}"
PROXY_PORT_B="${PROXY_PORT_B:-1081}"

LOG_FILE="${LOG_DIR}/watchdog.log"
METRICS_FILE="${LOG_DIR}/metrics.json"

# State files — proxy
PROXY_STATE_FILE="${LOG_DIR}/proxy.state"
PROXY_STATE_TS_FILE="${LOG_DIR}/proxy.state.timestamp"
PROXY_ERROR_COUNT_FILE="${LOG_DIR}/proxy_error_count.txt"

# State files — tailscale
TS_STATE_FILE="${LOG_DIR}/tailscale.state"
TS_STATE_TS_FILE="${LOG_DIR}/tailscale.state.timestamp"
TS_ERROR_COUNT_FILE="${LOG_DIR}/ts_error_count.txt"

# State files — exit-node (Swiss routing)
EXIT_STATE_FILE="${LOG_DIR}/exitnode.state"
EXIT_STATE_TS_FILE="${LOG_DIR}/exitnode.state.timestamp"
EXIT_ERROR_COUNT_FILE="${LOG_DIR}/exitnode_error_count.txt"

mkdir -p "$LOG_DIR"

# Міграція: якщо є старі state-файли, конвертуємо
if [ -f "${LOG_DIR}/watchdog.state" ] && [ ! -f "$PROXY_STATE_FILE" ]; then
    cp "${LOG_DIR}/watchdog.state" "$PROXY_STATE_FILE"
    [ -f "${LOG_DIR}/watchdog.state.timestamp" ] && cp "${LOG_DIR}/watchdog.state.timestamp" "$PROXY_STATE_TS_FILE"
    [ -f "${LOG_DIR}/error_count.txt" ] && cp "${LOG_DIR}/error_count.txt" "$PROXY_ERROR_COUNT_FILE"
fi

# ============== ФУНКЦІЇ ==============

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local color=$NC

    case $level in
        ERROR)   color=$RED ;;
        WARN)    color=$YELLOW ;;
        INFO)    color=$GREEN ;;
        DEBUG)   color=$BLUE ;;
    esac

    echo -e "${color}[$timestamp] [$level]${NC} $message" | tee -a "$LOG_FILE"
}

# --- State helpers (generic, parametrised by file paths) ---

_get_state() { [ -f "$1" ] && cat "$1" || echo "unknown"; }
_save_state() {
    echo "$2" > "$1"       # state file
    printf '%s\n%s\n' "$2" "$(date '+%s')" > "$3"  # timestamp file
}
_get_error_count()  { [ -f "$1" ] && cat "$1" || echo "0"; }
_inc_error_count()  { echo $(( $(_get_error_count "$1") + 1 )) > "$1"; }
_reset_error_count(){ echo "0" > "$1"; }

# Convenience wrappers
get_proxy_state()       { _get_state "$PROXY_STATE_FILE"; }
save_proxy_state()      { _save_state "$PROXY_STATE_FILE" "$1" "$PROXY_STATE_TS_FILE"; }
get_proxy_errors()      { _get_error_count "$PROXY_ERROR_COUNT_FILE"; }
inc_proxy_errors()      { _inc_error_count "$PROXY_ERROR_COUNT_FILE"; }
reset_proxy_errors()    { _reset_error_count "$PROXY_ERROR_COUNT_FILE"; }

get_ts_state()          { _get_state "$TS_STATE_FILE"; }
save_ts_state()         { _save_state "$TS_STATE_FILE" "$1" "$TS_STATE_TS_FILE"; }
get_ts_errors()         { _get_error_count "$TS_ERROR_COUNT_FILE"; }
inc_ts_errors()         { _inc_error_count "$TS_ERROR_COUNT_FILE"; }
reset_ts_errors()       { _reset_error_count "$TS_ERROR_COUNT_FILE"; }

get_exit_state()        { _get_state "$EXIT_STATE_FILE"; }
save_exit_state()       { _save_state "$EXIT_STATE_FILE" "$1" "$EXIT_STATE_TS_FILE"; }
get_exit_errors()       { _get_error_count "$EXIT_ERROR_COUNT_FILE"; }
inc_exit_errors()       { _inc_error_count "$EXIT_ERROR_COUNT_FILE"; }
reset_exit_errors()     { _reset_error_count "$EXIT_ERROR_COUNT_FILE"; }

get_downtime_duration_from() {
    local ts_file="$1"
    if [ ! -f "$ts_file" ]; then
        echo "невідомо"
        return
    fi
    local down_time
    down_time=$(tail -n 1 "$ts_file")
    local current_time
    current_time=$(date '+%s')
    local duration=$((current_time - down_time))

    local hours=$((duration / 3600))
    local minutes=$(((duration % 3600) / 60))
    local seconds=$((duration % 60))

    if [ $hours -gt 0 ]; then
        echo "${hours}г ${minutes}хв ${seconds}с"
    elif [ $minutes -gt 0 ]; then
        echo "${minutes}хв ${seconds}с"
    else
        echo "${seconds}с"
    fi
}

# --- Tailscale check ---
# Returns 0=up, 1=down.  Sets global TS_DOWN_REASON on failure.
check_tailscale() {
    log "DEBUG" "Перевірка Tailscale з'єднання..."
    TS_DOWN_REASON=""

    # Is tailscaled running?
    if ! pgrep -x tailscaled &>/dev/null; then
        TS_DOWN_REASON="tailscaled process not running"
        log "ERROR" "Tailscale: $TS_DOWN_REASON"
        return 1
    fi

    # Can we talk to the daemon?
    local ts_output ts_exit
    ts_output=$(tailscale status --json 2>&1)
    ts_exit=$?
    if [ $ts_exit -ne 0 ]; then
        TS_DOWN_REASON="tailscale status exited $ts_exit"
        log "ERROR" "Tailscale: $TS_DOWN_REASON"
        return 1
    fi

    # Parse backend state
    local backend_state
    backend_state=$(echo "$ts_output" | jq -r '.BackendState // empty' 2>/dev/null)
    case "$backend_state" in
        Running)
            ;;
        NeedsLogin|NeedsMachineAuth)
            TS_DOWN_REASON="needs login ($backend_state)"
            log "ERROR" "Tailscale: $TS_DOWN_REASON"
            return 1
            ;;
        Stopped)
            TS_DOWN_REASON="stopped"
            log "ERROR" "Tailscale: $TS_DOWN_REASON"
            return 1
            ;;
        *)
            TS_DOWN_REASON="unexpected state: $backend_state"
            log "WARN" "Tailscale: $TS_DOWN_REASON"
            return 1
            ;;
    esac

    log "DEBUG" "Tailscale з'єднання активне (BackendState=Running)"
    return 0
}

# --- Exit-node identity check (Strict Swiss Routing & Anti-Flapping) ---
is_peer_online() {
    local target_ip="$1"
    local status_json="$2"
    [ -z "$target_ip" ] && return 1

    local is_self
    is_self=$(echo "$status_json" | jq -r --arg ip "$target_ip" ".Self.TailscaleIPs[]? | select(. == \$ip)" 2>/dev/null)
    [ -n "$is_self" ] && return 1

    local is_online
    is_online=$(echo "$status_json" | jq -r --arg ip "$target_ip" "[.Peer[]? | select(.TailscaleIPs[]? == \$ip) | .Online][0] // false" 2>/dev/null)
    [ "$is_online" = "true" ]
}

test_internet_access() {
    for attempt in 1 2 3; do
        if timeout 3 nslookup google.com 1.1.1.1 &>/dev/null || \
           curl -s --max-time 3 http://checkip.amazonaws.com/ &>/dev/null; then
            return 0
        fi
        [ $attempt -lt 3 ] && sleep 1
    done
    return 1
}

check_exit_node() {
    log "DEBUG" "Перевірка Swiss exit-node ($PRIMARY_EXIT_NODE_IP)..."
    EXIT_DOWN_REASON=""

    local ts_json
    ts_json=$(tailscale status --json 2>/dev/null)
    if [ -z "$ts_json" ]; then
        EXIT_DOWN_REASON="Не вдалося отримати статус Tailscale"
        log "ERROR" "Exit-node: $EXIT_DOWN_REASON"
        return 1
    fi

    local current_ip current_online
    current_ip=$(echo "$ts_json" | jq -r ".ExitNodeStatus.TailscaleIPs[0] // empty" 2>/dev/null | cut -d/ -f1)
    current_online=$(echo "$ts_json" | jq -r ".ExitNodeStatus.Online // false" 2>/dev/null)

    # 1. Якщо поточний вузол є основним Swiss вузлом (100.87.198.99)
    if [ "$current_ip" = "$PRIMARY_EXIT_NODE_IP" ] && [ "$current_online" = "true" ]; then
        if test_internet_access; then
            log "DEBUG" "Swiss Exit-node $PRIMARY_EXIT_NODE_IP працює стабільно"
            return 0
        else
            log "WARN" "Swiss Exit-node $PRIMARY_EXIT_NODE_IP не пройшов тест доступності (3 спроби)"
        fi
    fi

    # 2. Переконатися, що увімкнено саме Swiss Exit-node (100.87.198.99)
    if [ "$current_ip" != "$PRIMARY_EXIT_NODE_IP" ]; then
        if is_peer_online "$PRIMARY_EXIT_NODE_IP" "$ts_json"; then
            log "INFO" "Активація основного Swiss Exit-node ($PRIMARY_EXIT_NODE_IP)..."
            sudo tailscale set --exit-node="$PRIMARY_EXIT_NODE_IP" --exit-node-allow-lan-access=true >/dev/null 2>&1
            sleep 2
            if test_internet_access; then
                log "INFO" "Swiss Exit-node $PRIMARY_EXIT_NODE_IP успішно активовано"
                return 0
            fi
        else
            log "WARN" "Основний Swiss Exit-node $PRIMARY_EXIT_NODE_IP зараз Offline у Tailscale"
        fi
    fi

    # 3. Перевірка тільки вказаних користувачем резервних вузлів (якщо дозволено)
    if [ -n "$FALLBACK_EXIT_NODES" ]; then
        for cand in $FALLBACK_EXIT_NODES; do
            [ "$cand" = "$PRIMARY_EXIT_NODE_IP" ] && continue
            if is_peer_online "$cand" "$ts_json"; then
                log "INFO" "Тестування резервного Exit-node: $cand..."
                sudo tailscale set --exit-node="$cand" --exit-node-allow-lan-access=true >/dev/null 2>&1
                sleep 2
                if test_internet_access; then
                    log "INFO" "Переключено на резервний Exit-node: $cand"
                    return 0
                fi
            fi
        done
    fi

    # 4. Аварійний прямий інтернет (ТІЛЬКИ якщо явно ввімкнено ENABLE_DIRECT_FALLBACK=true у .env)
    if [ "$ENABLE_DIRECT_FALLBACK" = "true" ]; then
        log "WARN" "Swiss Exit-node недоступний. Перехід на ПРЯМИЙ інтернет (ENABLE_DIRECT_FALLBACK=true)..."
        sudo tailscale set --exit-node="" >/dev/null 2>&1
        sleep 1
        if test_internet_access; then
            log "INFO" "Пряме з'єднання з інтернетом відновлено"
            return 0
        fi
    fi

    EXIT_DOWN_REASON="Swiss Exit-node $PRIMARY_EXIT_NODE_IP недоступний"
    log "ERROR" "Exit-node: $EXIT_DOWN_REASON"
    return 1
}


# --- SOCKS5 proxy check ---
check_socks_proxy() {
    local attempt=$1
    log "DEBUG" "SOCKS5 Proxy перевірка (спроба $attempt)..."

    local start_check end_check check_time proxy_test curl_exit
    start_check=$(date +%s.%N)
    proxy_test=$(curl -s -o /dev/null -w "%{http_code}" \
        --socks5 "${PROXY_HOST}:${PROXY_PORT}" \
        --connect-timeout "$CHECK_TIMEOUT" \
        --max-time $((CHECK_TIMEOUT + 5)) \
        "$TEST_URL" 2>&1)
    curl_exit=$?
    end_check=$(date +%s.%N)
    check_time=$(echo "$end_check - $start_check" | bc)

    if [ $curl_exit -eq 0 ] && [ "$proxy_test" != "000" ] && [ "$proxy_test" -ge 200 ] 2>/dev/null && [ "$proxy_test" -lt 400 ] 2>/dev/null; then
        log "INFO" "SOCKS5 Proxy OK (HTTP $proxy_test, ${check_time}s)"
        return 0
    else
        if [ "$proxy_test" = "000" ]; then
            log "ERROR" "SOCKS5 Proxy fail (HTTP 000 — no response)"
        else
            log "ERROR" "SOCKS5 Proxy fail (exit=$curl_exit, HTTP=$proxy_test)"
        fi
        return 1
    fi
}

check_proxy() {
    local retry_count=0
    while [ $retry_count -lt $MAX_RETRIES ]; do
        log "INFO" "Перевірка SOCKS5 $PROXY_HOST:$PROXY_PORT (спроба $((retry_count + 1))/$MAX_RETRIES)..."
        if check_socks_proxy $((retry_count + 1)); then
            return 0
        fi
        retry_count=$((retry_count + 1))
        if [ $retry_count -lt $MAX_RETRIES ]; then
            log "INFO" "Очікування $RETRY_DELAY сек перед наступною спробою..."
            sleep $RETRY_DELAY
        fi
    done
    log "ERROR" "SOCKS5 Proxy недоступний після $MAX_RETRIES спроб"
    return 1
}

trigger_macrodroid() {
    if [ -n "$MACRODROID_WEBHOOK_URL" ] && [[ "$MACRODROID_WEBHOOK_URL" != *"YOUR_DEVICE_ID"* ]]; then
        log "INFO" "Відправка FCM Push на MacroDroid ($MACRODROID_WEBHOOK_URL)..."
        curl -s -X GET "$MACRODROID_WEBHOOK_URL" --max-time 10 || true
    fi
}

send_notification() {
    local message="$1"
    log "INFO" "Відправка сповіщення в Telegram..."

    local extra_args=()
    if [ -n "$MACRODROID_WEBHOOK_URL" ] && [[ "$MACRODROID_WEBHOOK_URL" != *"YOUR_DEVICE_ID"* ]]; then
        local keyboard
        keyboard=$(jq -n -c --arg url "$MACRODROID_WEBHOOK_URL" \
            '{inline_keyboard: [[{text: "⚡ Підняти Tailscale (Push)", url: $url}]]}')
        extra_args+=(-d "reply_markup=$keyboard")
    fi

    local response
    response=$(curl -s -x "" -X POST \
        "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${message}" \
        "${extra_args[@]}" \
        --max-time 15 2>&1)

    if echo "$response" | grep -q 'ok":true'; then
        log "INFO" "Сповіщення відправлено"
        return 0
    else
        log "ERROR" "Помилка відправки: $response"
        return 1
    fi
}

send_n8n_webhook() {
    local event="$1"
    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    log "INFO" "Відправка n8n webhook: event=$event"
    curl -s -X POST "$N8N_WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"event\":\"$event\",\"host\":\"$PROXY_HOST\",\"port\":$PROXY_PORT,\"timestamp\":\"$timestamp\",\"source\":\"watchdog\"}" \
        --max-time 25 || true
}

save_metrics() {
    local status=$1
    local response_time=${2:-0}
    local ts_status=${3:-unknown}
    local timestamp datetime metric
    timestamp=$(date '+%s')
    datetime=$(date '+%Y-%m-%d %H:%M:%S')

    metric=$(jq -n \
        --argjson timestamp "$timestamp" \
        --arg datetime "$datetime" \
        --arg status "$status" \
        --argjson response_time "$response_time" \
        --arg proxy_host "$PROXY_HOST" \
        --argjson proxy_port "$PROXY_PORT" \
        --arg tailscale "$ts_status" \
        '{timestamp: $timestamp, datetime: $datetime, status: $status, response_time: $response_time, proxy_host: $proxy_host, proxy_port: $proxy_port, tailscale: $tailscale}')

    if [ -f "$METRICS_FILE" ]; then
        jq ". += [$metric]" "$METRICS_FILE" > "${METRICS_FILE}.tmp" && mv "${METRICS_FILE}.tmp" "$METRICS_FILE"
    else
        echo "[$metric]" > "$METRICS_FILE"
    fi
    # Тримаємо останні 1000
    if [ -f "$METRICS_FILE" ]; then
        jq '.[-1000:]' "$METRICS_FILE" > "${METRICS_FILE}.tmp" && mv "${METRICS_FILE}.tmp" "$METRICS_FILE"
    fi
}

calculate_uptime() {
    if [ ! -f "$METRICS_FILE" ]; then echo "N/A"; return; fi
    local total up
    total=$(jq 'length' "$METRICS_FILE")
    up=$(jq '[.[] | select(.status == "up")] | length' "$METRICS_FILE")
    if [ "$total" -gt 0 ]; then
        echo "scale=2; ($up / $total) * 100" | bc
    else
        echo "N/A"
    fi
}

get_system_info() {
    local hostname tailscale_ip up_info
    hostname=$(hostname)
    tailscale_ip=$(tailscale ip -4 2>/dev/null | head -n1)
    up_info=$(uptime -p)
    printf "🖥 Хост: %s\n🌐 Tailscale IP: %s\n⏱ Uptime: %s" "$hostname" "$tailscale_ip" "$up_info"
}

# ============== ГОЛОВНА ЛОГІКА ==============

main() {
    log "INFO" "=========================================="
    log "INFO" "   WATCHDOG START"
    log "INFO" "=========================================="
    log "INFO" "Проксі: socks5://$PROXY_HOST:$PROXY_PORT"
    log "INFO" "Reminder every: $REMINDER_EVERY_ERRORS errors"

    if [[ "$TELEGRAM_TOKEN" == *"ВАШ_ТОКЕН"* ]] || [[ "$WORKER_URL" == *"YOUR_SUBDOMAIN"* ]]; then
        log "ERROR" "Конфігурація не завершена! Заповніть TELEGRAM_TOKEN та WORKER_URL"
        exit 1
    fi

    for cmd in curl jq tailscale bc; do
        if ! command -v $cmd &>/dev/null; then
            log "ERROR" "Команда '$cmd' не знайдена. Встановіть: sudo apt install $cmd"
            exit 1
        fi
    done

    local current_time
    current_time=$(date '+%Y-%m-%d %H:%M:%S')

    # ─── Phase 1: Tailscale health ───
    local last_ts_state
    last_ts_state=$(get_ts_state)

    if ! check_tailscale; then
        # Tailscale DOWN
        inc_ts_errors
        local ts_errors
        ts_errors=$(get_ts_errors)

        save_metrics "down" "0" "down"

        if [ "$last_ts_state" != "down" ]; then
            log "ERROR" "TAILSCALE OFFLINE ($TS_DOWN_REASON)"
            local message
            message=$(printf "🔴 *TAILSCALE OFFLINE*\n\n🕐 Час: %s\n❌ Причина: %s\n📊 Proxy check: skipped\n\n%s" \
                "$current_time" "$TS_DOWN_REASON" "$(get_system_info)")
            send_notification "$message"
        else
            log "WARN" "Tailscale досі offline (помилок: $ts_errors, причина: $TS_DOWN_REASON)"
            if [ "$ts_errors" -gt 0 ] && [ $((ts_errors % REMINDER_EVERY_ERRORS)) -eq 0 ]; then
                local downtime
                downtime=$(get_downtime_duration_from "$TS_STATE_TS_FILE")
                local message
                message=$(printf "⚠️ *TAILSCALE STILL OFFLINE*\n\n🕐 Час: %s\n❌ Причина: %s\n📈 Послідовних помилок: %s\n⏱ Час простою: %s" \
                    "$current_time" "$TS_DOWN_REASON" "$ts_errors" "$downtime")
                send_notification "$message"
            fi
        fi

        save_ts_state "down"
        # Proxy check не має сенсу без tailscale
        log "INFO" "Proxy check skipped: tailscale down"
        log "INFO" "=========================================="
        log "INFO" "   WATCHDOG END"
        log "INFO" "=========================================="
        return
    fi

    # Tailscale UP
    if [ "$last_ts_state" = "down" ]; then
        local downtime
        downtime=$(get_downtime_duration_from "$TS_STATE_TS_FILE")
        log "INFO" "TAILSCALE RECOVERED (був offline $downtime)"
        local message
        message=$(printf "✅ *TAILSCALE RECOVERED*\n\n🕐 Час: %s\n⏱ Був offline: %s\n📊 Далі перевіряємо proxy...\n\n%s" \
            "$current_time" "$downtime" "$(get_system_info)")
        send_notification "$message"
        reset_ts_errors
    fi
    save_ts_state "up"

    # ─── Phase 1.5: Exit-node identity (Swiss routing) ───
    local last_exit_state exit_errors
    last_exit_state=$(get_exit_state)

    if ! check_exit_node; then
        inc_exit_errors
        exit_errors=$(get_exit_errors)

        if [ "$last_exit_state" != "down" ]; then
            log "ERROR" "EXIT-NODE WRONG/MISSING ($EXIT_DOWN_REASON)"
            local message
            message=$(printf "🇨🇭➡️🌍 *EXIT-NODE НЕ ШВЕЙЦАРСЬКИЙ*\n\n🕐 Час: %s\n❌ %s\n🔧 Авто-фікс спробований, не вдався\n\n%s" \
                "$current_time" "$EXIT_DOWN_REASON" "$(get_system_info)")
            send_notification "$message"
        else
            log "WARN" "Exit-node досі невірний (помилок: $exit_errors)"
            if [ "$exit_errors" -gt 0 ] && [ $((exit_errors % REMINDER_EVERY_ERRORS)) -eq 0 ]; then
                local message
                message=$(printf "⚠️ *EXIT-NODE ДОСІ НЕ ШВЕЙЦАРСЬКИЙ*\n\n🕐 Час: %s\n❌ %s\n📈 Послідовних помилок: %s" \
                    "$current_time" "$EXIT_DOWN_REASON" "$exit_errors")
                send_notification "$message"
            fi
        fi
        save_exit_state "down"
    else
        if [ "$last_exit_state" = "down" ]; then
            log "INFO" "EXIT-NODE RECOVERED"
            send_notification "$(printf '✅ *EXIT-NODE ВІДНОВЛЕНО*\n\n🕐 Час: %s\n🇨🇭 Швейцарський маршрут активний знову' "$current_time")"
            reset_exit_errors
        fi
        save_exit_state "up"
    fi

    # ─── Phase 2: SOCKS5 proxy health ───
    local start_time last_proxy_state
    start_time=$(date +%s.%N)
    last_proxy_state=$(get_proxy_state)

    if check_proxy; then
        local end_time response_time
        end_time=$(date +%s.%N)
        response_time=$(echo "$end_time - $start_time" | bc)

        save_metrics "up" "$response_time" "up"

        if [ "$last_proxy_state" = "down" ]; then
            local downtime uptime_pct
            downtime=$(get_downtime_duration_from "$PROXY_STATE_TS_FILE")
            uptime_pct=$(calculate_uptime)
            log "INFO" "PROXY RECOVERED"
            local message
            message=$(printf "✅ *PROXY RECOVERED*\n\n🕐 Час: %s\n🌐 Проксі: socks5://%s:%s\n⏱ Час простою: %s\n📊 Uptime: %s%%\n⚡ Час відповіді: %ss\n\n%s" \
                "$current_time" "$PROXY_HOST" "$PROXY_PORT" "$downtime" "$uptime_pct" "$response_time" "$(get_system_info)")
            send_notification "$message"
            send_n8n_webhook "proxy_up"
            reset_proxy_errors
        else
            log "INFO" "Проксі OK (${response_time}s)"
        fi
        save_proxy_state "up"
    else
        inc_proxy_errors
        local proxy_errors
        proxy_errors=$(get_proxy_errors)

        save_metrics "down" "0" "up"

        if [ "$last_proxy_state" != "down" ]; then
            log "ERROR" "PROXY DOWN"
            local message
            message=$(printf "🚨 *PROXY DOWN DETECTED*\n\n🕐 Час: %s\n🌐 Проксі: socks5://%s:%s\n❌ Причина: Немає відповіді від SOCKS5\n🔄 Спроб: %s\n📡 Tailscale: online\n\n%s" \
                "$current_time" "$PROXY_HOST" "$PROXY_PORT" "$MAX_RETRIES" "$(get_system_info)")
            send_notification "$message"
            send_n8n_webhook "proxy_down"
        else
            log "WARN" "Проксі досі недоступний (помилок: $proxy_errors)"
            if [ "$proxy_errors" -gt 0 ] && [ $((proxy_errors % REMINDER_EVERY_ERRORS)) -eq 0 ]; then
                local downtime
                downtime=$(get_downtime_duration_from "$PROXY_STATE_TS_FILE")
                local message
                message=$(printf "⚠️ *PROXY STILL DOWN*\n\n🕐 Час: %s\n🌐 Проксі: socks5://%s:%s\n📈 Послідовних помилок: %s\n⏱ Час простою: %s\n🔧 Рекомендація: Перевірте Termux та SOCKS5 службу" \
                    "$current_time" "$PROXY_HOST" "$PROXY_PORT" "$proxy_errors" "$downtime")
                send_notification "$message"
            fi
        fi
        save_proxy_state "down"
    fi

    log "INFO" "=========================================="
    log "INFO" "   WATCHDOG END"
    log "INFO" "=========================================="
}

trap 'log "WARN" "Отримано сигнал переривання"; exit 130' INT TERM

# Якщо запущено з IS_UPDATE=1 — оновити служби і вийти
if [ "${IS_UPDATE:-0}" -eq 1 ]; then
    echo -e "${BLUE}▶ Завершення оновлення та запуск служб${NC}"
    sudo systemctl daemon-reload
    sudo systemctl enable watchdog-proxy.timer
    sudo systemctl start watchdog-proxy.timer
    echo -e "${GREEN}✓ Оновлення завершено${NC}"
    exit 0
fi

main
exit 0
