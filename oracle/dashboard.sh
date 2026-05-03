#!/bin/bash

METRICS_FILE="/opt/watchdog/logs/metrics.json"
LOG_FILE="/opt/watchdog/logs/watchdog.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

clear
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}     TAILSCALE SOCKS5 WATCHDOG DASHBOARD${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════${NC}"
echo ""

if [ ! -f "$METRICS_FILE" ]; then
    echo -e "${RED}❌ Метрики ще не зібрані. Запустіть watchdog спочатку.${NC}"
    exit 1
