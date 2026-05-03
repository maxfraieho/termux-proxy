#!/data/data/com.termux/files/usr/bin/bash
# modules/ssh.sh — налаштування SSH сервера на порту SSH_PORT
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

SVC_DIR="$PREFIX/var/service/sshd"

# ── Ensure termux-services ────────────────────────────────────
_ensure_sv() {
    if ! command -v sv >/dev/null 2>&1; then
        echo "  Installing termux-services..."
        if ! pkg install -y termux-services; then
            echo "❌  Failed to install termux-services"
            exit 1
        fi
        echo "  ✅  termux-services installed"
    fi
    if ! pgrep runsvdir >/dev/null 2>&1; then
        nohup runsvdir "$PREFIX/var/service" >/dev/null 2>&1 &
        sleep 1
    fi
}

echo
echo "════════════════════════════════════════"
echo " SSH Server  (port $SSH_PORT)"
echo "════════════════════════════════════════"

# ── 1. Встановити openssh ─────────────────────────────────────
echo; echo "[1/4] Package..."
if [ "$HAS_SSH" = "no" ]; then
    pkg install -y openssh
    echo "  ✅  openssh installed"
else
    echo "  ✅  openssh present"
fi

# ── 2. Host keys та sshd_config ──────────────────────────────
echo; echo "[2/4] SSH configuration..."

# Генеруємо host keys якщо відсутні
[ ! -f "$PREFIX/etc/ssh/ssh_host_rsa_key" ] && ssh-keygen -A && \
    echo "  ✅  host keys generated" || echo "  ✅  host keys present"

# Бекап sshd_config перед змінами
if [ -f "$PREFIX/etc/ssh/sshd_config" ]; then
    cp "$PREFIX/etc/ssh/sshd_config" "$PREFIX/etc/ssh/sshd_config.bak"
fi

# Переконуємось що порт правильний у sshd_config
# Termux sshd_config може не мати Port рядка — додаємо якщо нема
SSHD_CONF="$PREFIX/etc/ssh/sshd_config"
if [ -f "$SSHD_CONF" ]; then
    if grep -qE '^Port ' "$SSHD_CONF"; then
        sed -i "s/^Port .*/Port $SSH_PORT/" "$SSHD_CONF"
    else
        printf '\nPort %s\n' "$SSH_PORT" >> "$SSHD_CONF"
    fi
    # Дозволяємо password auth (потрібно для passwd-based login)
    if grep -qE '^PasswordAuthentication' "$SSHD_CONF"; then
        sed -i 's/^PasswordAuthentication.*/PasswordAuthentication yes/' "$SSHD_CONF"
    else
        printf '\nPasswordAuthentication yes\n' >> "$SSHD_CONF"
    fi
    echo "  ✅  sshd_config updated (port $SSH_PORT, PasswordAuthentication yes)"
fi

# ── 3. Пароль ────────────────────────────────────────────────
echo; echo "[3/4] User password..."
echo "  Set SSH password for: $TERMUX_USER"
echo "  (passwd — Termux native, no root needed)"
# passwd є інтерактивним — просто запускаємо
passwd

# ── 4. Сервіс ────────────────────────────────────────────────
echo; echo "[4/4] Service..."

_ensure_sv

# Зупиняємо якщо вже запущено
if [ -d "$SVC_DIR" ]; then
    sv down "$SVC_DIR" 2>/dev/null || true
fi

mkdir -p "$SVC_DIR/log"

cat > "$SVC_DIR/run" << 'RUNEOF'
#!/data/data/com.termux/files/usr/bin/sh
exec sshd -D -e 2>&1
RUNEOF
chmod +x "$SVC_DIR/run"

sv-enable sshd 2>/dev/null || true
rm -f "$SVC_DIR/down" 2>/dev/null || true  # sv-enable has -u/-z bug
sv up "$SVC_DIR" 2>/dev/null || true
sleep 2

if sv status "$SVC_DIR" 2>/dev/null | grep -q '^run:'; then
    echo "  ✅  sshd running"
else
    echo "  ⚠️   check: sv status $SVC_DIR"
fi

# ── Підсумок ─────────────────────────────────────────────────
echo
echo "════════════════════════════════════════"
echo " SSH ready"
echo "  Connect: ssh -p $SSH_PORT $TERMUX_USER@$TS_IP"
echo "════════════════════════════════════════"
