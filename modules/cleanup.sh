#!/data/data/com.termux/files/usr/bin/bash
# modules/cleanup.sh — повне скидання конфігів до нуля
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$HOME_DIR/.termux-deploy-backup/$TIMESTAMP"

echo
echo "════════════════════════════════════════"
echo " Full Cleanup"
echo "════════════════════════════════════════"
echo
echo "  Removes: sshd / tor / ts-proxy services"
echo "           ~/.termux/boot/start-services.sh"
echo "           service lines from .bashrc / .profile"
echo
echo "  Backups → $BACKUP_DIR"
echo
printf "  Type 'yes' to confirm: "
read -r _confirm
[ "$_confirm" != "yes" ] && { echo "  Cancelled."; exit 0; }

mkdir -p "$BACKUP_DIR"

# ── 1. Зупинити сервіси ──────────────────────────────────────
echo; echo "[1/5] Stopping services..."

if command -v sv &>/dev/null; then
    for svc in sshd tor ts-proxy; do
        local_path="$PREFIX/var/service/$svc"
        if [ -d "$local_path" ]; then
            sv down "$local_path" 2>/dev/null || true
            echo "  ⏹  $svc stopped"
        else
            echo "  –  $svc absent"
        fi
    done
else
    pkill -f "sshd -D" 2>/dev/null || true
    pkill -f "tor -f"  2>/dev/null || true
    pkill -f "ts-proxy" 2>/dev/null || true
    echo "  sv not found — killed processes directly"
fi

# ── 2. Бекап ─────────────────────────────────────────────────
echo; echo "[2/5] Backing up configs..."

_bak() {
    [ -e "$1" ] && cp -r "$1" "$BACKUP_DIR/" && \
        echo "  💾  $1" || true
}

_bak "$PREFIX/etc/tor/torrc"
_bak "$PREFIX/etc/ssh/sshd_config"
_bak "$HOME_DIR/.bashrc"
_bak "$HOME_DIR/.profile"
_bak "$HOME_DIR/.termux/boot/start-services.sh"

# ── 3. Видалити сервіси ──────────────────────────────────────
echo; echo "[3/5] Removing service directories..."

for svc in sshd tor ts-proxy; do
    svc_path="$PREFIX/var/service/$svc"
    if [ -d "$svc_path" ]; then
        rm -rf "$svc_path"
        echo "  🗑  $svc_path"
    fi
done

# ── 4. Видалити boot script ──────────────────────────────────
echo; echo "[4/5] Removing boot script..."

BOOT="$HOME_DIR/.termux/boot/start-services.sh"
if [ -f "$BOOT" ]; then
    rm -f "$BOOT"
    echo "  🗑  $BOOT"
else
    echo "  –  not found"
fi

# ── 5. Очистити .bashrc / .profile ──────────────────────────
echo; echo "[5/5] Cleaning .bashrc and .profile..."

for f in "$HOME_DIR/.bashrc" "$HOME_DIR/.profile"; do
    if [ -f "$f" ]; then
        sed -i '/sshd\|\btor\b\|microsocks\|tailscaled\|ts-proxy\|sv up/d' "$f"
        # Прибрати подвійні порожні рядки
        sed -i '/^[[:space:]]*$/N;/^\n[[:space:]]*$/d' "$f"
        echo "  ✅  cleaned: $f"
    fi
done

# ── Підсумок ─────────────────────────────────────────────────
echo
echo "════════════════════════════════════════"
echo " Cleanup complete."
echo
echo "  Backups: $BACKUP_DIR"
echo
echo "  Restore torrc:"
echo "    cp $BACKUP_DIR/torrc $PREFIX/etc/tor/torrc"
echo
echo "  Redeploy:"
echo "    cd $DEPLOY_DIR && ./detect.sh && ./deploy.sh"
echo "════════════════════════════════════════"
