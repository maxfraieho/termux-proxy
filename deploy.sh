#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# deploy.sh — головний оркестратор
# Вимагає: ./detect.sh перед першим запуском
# ============================================================
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$DEPLOY_DIR/config.env"

if [ ! -f "$CONFIG" ]; then
    echo "❌ config.env not found. Run: ./detect.sh"
    exit 1
fi

source "$CONFIG"

# ── UI хелпери ───────────────────────────────────────────────
banner() {
    echo
    echo "════════════════════════════════════════"
    echo "  $1"
    echo "════════════════════════════════════════"
}

status_line() {
    printf "  %s  %-24s %s\n" "$1" "$2" "$3"
}

confirm() {
    printf "  Continue? (y/N): "
    read -r _r
    [[ "${_r,,}" == "y" ]]
}

# ── Стан системи ─────────────────────────────────────────────
show_status() {
    banner "System Status"
    status_line "📱" "Tailscale IP:"     "$TS_IP"
    status_line "👤" "User:"             "$TERMUX_USER"
    echo
    status_line "📦" "openssh:"          "$HAS_SSH"
    status_line "📦" "tor:"              "$HAS_TOR"
    status_line "📦" "obfs4proxy:"       "$HAS_OBFS4"
    status_line "📦" "termux-services:"  "$HAS_SV"
    status_line "📦" "ts-proxy binary:"  "$HAS_TSPROXY"
    echo
    status_line "🔌" "sshd:"             "$SV_SSHD    port $SSH_PORT"
    status_line "🔌" "tor:"              "$SV_TOR     port $TOR_PORT"
    status_line "🔌" "ts-proxy:"         "$SV_TSPROXY  port $TSPROXY_PORT"
    status_line "🌉" "Tor bridges:"      "$BRIDGES_COUNT configured"
    status_line "🥾" "Termux:Boot:"      "$HAS_TSBOOT"
    echo
}

# ── Запуск модуля ─────────────────────────────────────────────
# Передає шлях до config як $1, оновлює config після завершення
run_module() {
    local name="$1"
    local script="$DEPLOY_DIR/modules/$name"

    if [ ! -f "$script" ]; then
        echo "❌ Module not found: modules/$name"
        return 1
    fi

    chmod +x "$script"
    bash "$script" "$CONFIG"

    # Оновлюємо config після змін у системі
    bash "$DEPLOY_DIR/detect.sh" > /dev/null 2>&1 || true
    source "$CONFIG"
}

# ── Підменю AI-промптів ──────────────────────────────────────
prompt_menu() {
    echo
    echo "  [1]  Full setup prompt   (SSH + Tor + ts-proxy)"
    echo "  [2]  Bridges update prompt"
    echo "  [3]  Back"
    echo
    printf "  Choice: "
    read -r _p

    local gen="$DEPLOY_DIR/gen-prompt.sh"
    [ ! -f "$gen" ] && { echo "❌ gen-prompt.sh not found"; return 1; }
    chmod +x "$gen"

    case "$_p" in
        1) bash "$gen" setup ;;
        2) bash "$gen" bridges ;;
        3) return ;;
        *) echo "  Invalid choice." ;;
    esac
}

# ── Головне меню ─────────────────────────────────────────────
main_menu() {
    while true; do
        banner "Termux Geo-Bypass Deploy — Main Menu"
        show_status

        echo "  [1]  Full deployment   (SSH + Tor + ts-proxy + Boot)"
        echo "  [2]  SSH server only"
        echo "  [3]  Tor proxy only    (port $TOR_PORT)"
        echo "  [4]  ts-proxy only     (port $TSPROXY_PORT, для PinchTab)"
        echo "  [5]  Update Tor bridges"
        echo "  [6]  Verify all services"
        echo "  [7]  Generate AI prompt"
        echo "  [8]  Re-run detection  (refresh config.env)"
        echo "  [9]  Full cleanup"
        echo "  [q]  Quit"
        echo
        printf "  Choice: "
        read -r choice

        case "$choice" in
            1)
                banner "Full Deployment"
                echo "  Will configure: SSH + Tor + ts-proxy + Termux:Boot"
                confirm && {
                    run_module ssh.sh
                    run_module tor.sh
                    run_module tsproxy.sh
                    run_module boot.sh
                    run_module verify.sh
                }
                ;;
            2)
                banner "SSH Server"
                confirm && run_module ssh.sh
                ;;
            3)
                banner "Tor Proxy (port $TOR_PORT)"
                confirm && run_module tor.sh
                ;;
            4)
                banner "ts-proxy (port $TSPROXY_PORT)"
                confirm && run_module tsproxy.sh
                ;;
            5)
                banner "Update Tor Bridges"
                run_module bridges.sh
                ;;
            6)
                banner "Verify Services"
                run_module verify.sh
                ;;
            7)
                banner "Generate AI Prompt"
                prompt_menu
                ;;
            8)
                banner "Re-running detection..."
                bash "$DEPLOY_DIR/detect.sh"
                source "$CONFIG"
                ;;
            9)
                banner "Full Cleanup"
                echo "  ⚠️  Removes all services, configs, boot scripts."
                confirm && run_module cleanup.sh
                ;;
            q|Q)
                echo; echo "  Bye!"; exit 0
                ;;
            *)
                echo "  Invalid choice."
                ;;
        esac

        echo
        printf "  Press Enter to return to menu..."
        read -r _
    done
}

main_menu
