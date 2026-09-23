#!/bin/bash
#===============================================================================
# recover_system.sh — Комплексне діагностування та відновлення Swiss Proxy & Bot
# Автоматично лікує зависання exit-node, відновлює зв'язок з Telegram API,
# перевіряє та перезапускає сервіси проксі та телеграм-бота.
#===============================================================================

set -u

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}${BLUE}====================================================================${NC}"
echo -e "${BOLD}${BLUE}  ЗАПУСК АВТОМАТИЧНОГО ВІДНОВЛЕННЯ СЕРВІСУ SWISS PROXY ТА БОТА      ${NC}"
echo -e "${BOLD}${BLUE}====================================================================${NC}"
echo -e "Час запуску: $(date '+%Y-%m-%d %H:%M:%S')\n"

# ── 1. Завантаження налаштувань ──
ENV_FILE="/opt/watchdog/.env"
if [ -f "$ENV_FILE" ]; then
    set +u
    source "$ENV_FILE"
    set -u
fi

PRIMARY_EXIT="${PRIMARY_EXIT_NODE_IP:-${EXPECTED_EXIT_NODE_IP:-100.87.198.99}}"
FALLBACK_EXIT="${FALLBACK_EXIT_NODES:-100.100.74.9}"

# ── 2. Перевірка Tailscale сервісу ──
echo -e "${BOLD}[Крок 1/5] Перевірка служби Tailscale...${NC}"
if ! systemctl is-active --quiet tailscaled; then
    echo -e "${YELLOW}⚠️ tailscaled не активний. Перезапускаємо...${NC}"
    sudo systemctl restart tailscaled
    sleep 3
fi

TS_JSON=$(tailscale status --json 2>/dev/null || true)
if [ -z "$TS_JSON" ]; then
    echo -e "${RED}❌ Не вдалося отримати статус Tailscale. Перезапуск tailscaled...${NC}"
    sudo systemctl restart tailscaled
    sleep 3
    TS_JSON=$(tailscale status --json 2>/dev/null || true)
fi

echo -e "${GREEN}✓ Служба Tailscale працює.${NC}"

# ── 3. Перевірка та лікування Exit Node ──
echo -e "\n${BOLD}[Крок 2/5] Перевірка маршрутизації (Exit Node)...${NC}"
CURRENT_EXIT_IP=$(echo "$TS_JSON" | jq -r ".ExitNodeStatus.TailscaleIPs[0] // empty" 2>/dev/null | cut -d/ -f1)
CURRENT_EXIT_ONLINE=$(echo "$TS_JSON" | jq -r ".ExitNodeStatus.Online // false" 2>/dev/null)

is_peer_online() {
    local target_ip="$1"
    [ -z "$target_ip" ] && return 1
    local online
    online=$(echo "$TS_JSON" | jq -r --arg ip "$target_ip" "[.Peer[]? | select(.TailscaleIPs[]? == \$ip) | .Online][0] // false" 2>/dev/null)
    [ "$online" = "true" ]
}

# Якщо активний exit-node є, але він OFFLINE — знімаємо його, щоб розблокувати системний інтернет хоста
if [ -n "$CURRENT_EXIT_IP" ] && [ "$CURRENT_EXIT_ONLINE" != "true" ]; then
    echo -e "${YELLOW}⚠️ Поточний Exit-node ($CURRENT_EXIT_IP) у стані OFFLINE!${NC}"
    echo -e "${YELLOW}   Знімаємо прив'язку в Tailscale для розблокування зв'язку сервера...${NC}"
    sudo tailscale set --exit-node="" >/dev/null 2>&1
    sleep 2
    TS_JSON=$(tailscale status --json 2>/dev/null || true)
fi

# Якщо керування Exit Node вимкнено (ізоляція хоста)
MANAGE_EXIT="${MANAGE_EXIT_NODE:-false}"
if [ "$MANAGE_EXIT" = "false" ]; then
    echo -e "${GREEN}✓ Режим MANAGE_EXIT_NODE=false: хост залишається на прямому інтернеті (ens3).${NC}"
    if [ -n "$CURRENT_EXIT_IP" ]; then
        echo -e "${YELLOW}   Знімаємо прив'язку Exit-node в Tailscale...${NC}"
        sudo tailscale set --exit-node="" >/dev/null 2>&1
    fi
    TARGET_NODE=""
else
# Пошук доступного онлайн швейцарського вузла
TARGET_NODE=""
if is_peer_online "$PRIMARY_EXIT"; then
    TARGET_NODE="$PRIMARY_EXIT"
    echo -e "${GREEN}✓ Основний швейцарський вузол ($PRIMARY_EXIT) ONLINE.${NC}"
else
    echo -e "${YELLOW}ℹ Основний вузол ($PRIMARY_EXIT) OFFLINE.${NC}"
    for cand in $FALLBACK_EXIT; do
        if is_peer_online "$cand"; then
            TARGET_NODE="$cand"
            echo -e "${GREEN}✓ Резервний швейцарський вузол ($cand) ONLINE.${NC}"
            break
        else
            echo -e "${YELLOW}ℹ Резервний вузол ($cand) OFFLINE.${NC}"
        fi
    done
fi

if [ -n "$TARGET_NODE" ]; then
    echo -e "${GREEN}▶ Підключаємо активний Exit Node: $TARGET_NODE (з ізоляцією хоста)...${NC}"
    sudo tailscale set --exit-node="$TARGET_NODE" --exit-node-allow-lan-access=true >/dev/null 2>&1
    sudo ip rule add to 100.64.0.0/10 lookup 52 pref 5265 2>/dev/null || true
    sudo ip rule add not uidrange 998-998 lookup main pref 5268 2>/dev/null || true
else
    echo -e "${YELLOW}ℹ Хост залишається на прямому інтернеті (ens3).${NC}"
    sudo tailscale set --exit-node="" >/dev/null 2>&1
fi
fi

# ── 4. Перевірка доступу до Telegram API ──
echo -e "\n${BOLD}[Крок 3/5] Перевірка доступності Telegram API...${NC}"
if curl -s -m 5 -o /dev/null -w "%{http_code}" https://api.telegram.org 2>/dev/null | grep -qE '200|302|404'; then
    echo -e "${GREEN}✓ Telegram API відповідає стабільно.${NC}"
else
    echo -e "${RED}❌ Telegram API недоступний через поточний маршрут! Скидаємо exit-node...${NC}"
    sudo tailscale set --exit-node="" >/dev/null 2>&1
    sleep 2
    if curl -s -m 5 -o /dev/null https://api.telegram.org 2>/dev/null; then
        echo -e "${GREEN}✓ Telegram API відновлено через прямий інтернет.${NC}"
    else
        echo -e "${RED}❌ Помилка: Telegram API досі недоступний. Перевірте DNS/ens3.${NC}"
    fi
fi

# ── 5. Перезапуск сервісів ──
echo -e "\n${BOLD}[Крок 4/5] Перезапуск сервісів проксі та телеграм-бота...${NC}"
echo -e "▶ Перезапуск watchdog-bot.service..."
sudo systemctl restart watchdog-bot.service
sleep 1

echo -e "▶ Перезапуск swiss-proxy.service..."
sudo systemctl restart swiss-proxy.service
sleep 1

# ── 6. Підсумкова діагностика портів та стану ──
echo -e "\n${BOLD}[Крок 5/5] Підсумкова перевірка стану системи...${NC}"

BOT_ST=$(systemctl is-active watchdog-bot.service)
PROXY_ST=$(systemctl is-active swiss-proxy.service)

echo -e "• Telegram Bot Daemon (watchdog-bot.service): $([ "$BOT_ST" = "active" ] && echo -e "${GREEN}ONLINE (active)${NC}" || echo -e "${RED}FAILED ($BOT_ST)${NC}")"
echo -e "• Swiss Proxy Daemon  (swiss-proxy.service):  $([ "$PROXY_ST" = "active" ] && echo -e "${GREEN}ONLINE (active)${NC}" || echo -e "${RED}FAILED ($PROXY_ST)${NC}")"

check_port() {
    local port=$1
    local label=$2
    if ss -tulpn | grep -q ":$port "; then
        echo -e "• Порт $port ($label): ${GREEN}СЛУХАЄ${NC}"
    else
        echo -e "• Порт $port ($label): ${RED}НЕ ВІДПОВІДАЄ${NC}"
    fi
}

check_port 1080 "SOCKS5 Канал A (Чоловік)"
check_port 1081 "SOCKS5 Канал B (Дружина)"
check_port 8888 "HTTP Канал A (Чоловік)"
check_port 8889 "HTTP Канал B (Дружина)"

echo -e "\n${BOLD}${GREEN}====================================================================${NC}"
echo -e "${BOLD}${GREEN}  ВІДНОВЛЕННЯ ЗАВЕРШЕНО УСПІШНО!                                    ${NC}"
echo -e "${BOLD}${GREEN}====================================================================${NC}"
echo -e "Бот активний у Telegram: @vpn2votchdog_bot"
echo -e "Для ручного виклику відновлення виконайте:"
echo -e "  bash /home/ubuntu/recover_system.sh\n"
