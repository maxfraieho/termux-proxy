#!/data/data/com.termux/files/usr/bin/bash
# install.sh — deploy services/ and bin/ to their runtime locations
# Run after cloning on a new device (after detect.sh + deploy.sh)
set -e
PREFIX="/data/data/com.termux/files/usr"
HOME_DIR="/data/data/com.termux/files/home"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Installing services ==="
for svc in ts-proxy sshd local-watchdog; do
    SVC_DIR="$PREFIX/var/service/$svc"
    src="$SCRIPT_DIR/services/$svc"
    [ -d "$src" ] || continue
    sv down "$SVC_DIR" 2>/dev/null || true
    mkdir -p "$SVC_DIR/log"
    cp "$src/run" "$SVC_DIR/run" && chmod +x "$SVC_DIR/run"
    [ -f "$src/finish" ] && cp "$src/finish" "$SVC_DIR/finish" && chmod +x "$SVC_DIR/finish"
    [ -f "$src/log/run" ] && cp "$src/log/run" "$SVC_DIR/log/run" && chmod +x "$SVC_DIR/log/run"
    rm -f "$SVC_DIR/down"
    sv up "$SVC_DIR" 2>/dev/null || true
    echo "  installed: $svc"
done

echo "=== Installing bin/ ==="
mkdir -p "$HOME_DIR/bin"
cp "$SCRIPT_DIR/bin/"*.sh "$HOME_DIR/bin/"
chmod +x "$HOME_DIR/bin/"*.sh
echo "  installed: bin/"

echo "=== Installing boot script ==="
mkdir -p "$HOME_DIR/.termux/boot"
cp "$SCRIPT_DIR/boot/start-services.sh" "$HOME_DIR/.termux/boot/start-services.sh"
chmod +x "$HOME_DIR/.termux/boot/start-services.sh"
echo "  installed: boot/start-services.sh"

echo "Done."
