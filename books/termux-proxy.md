# Код проєкту: termux-proxy
**Згенеровано:** 2026-07-24 07:28:28
**Директорія:** `/storage/emulated/0/Documents/termux-proxy`
**Формат:** Markdown
---
## Структура проєкту
```
termux-proxy/
├── METHODOLOGY.md
├── README.md
├── deploy.sh
├── detect.sh
├── install.sh
├── bin/
│   ├── restart-proxy.sh
│   ├── tg-notify.sh
│   ├── watchdog-loop.sh
├── boot/
│   ├── start-services.sh
├── modules/
│   ├── boot.sh
│   ├── bridges.sh
│   ├── cleanup.sh
│   ├── ssh.sh
│   ├── tor.sh
│   ├── tsproxy-recover.sh
│   ├── tsproxy.sh
│   ├── verify.sh
├── oracle/
│   ├── dashboard.sh
│   ├── smart_proxy.py
│   ├── watchdog.sh
│   ├── systemd/
│   │   ├── swiss-proxy.service
│   │   ├── watchdog-proxy.service
│   │   ├── watchdog-proxy.timer
├── services/
│   ├── local-watchdog/
│   │   ├── run
│   │   ├── log/
│   │   │   ├── run
│   ├── sshd/
│   │   ├── run
│   ├── ts-proxy/
│   │   ├── finish
│   │   ├── run
│   │   ├── log/
│   │   │   ├── run
├── books/```
---
### METHODOLOGY.md
**Розмір:** 4,556 байт
```text
# Termux Geo-Bypass — Методологія

## Шари системи

```
┌──────────────────────────────────────────────────┐
│  ШАР 1 — ВИЯВЛЕННЯ                              │
│  detect.sh → config.env                          │
└─────────────────────┬────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────┐
│  ШАР 2 — РОЗГОРТАННЯ                            │
│  deploy.sh → modules/                            │
└─────────────────────┬────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────┐
│  ШАР 3 — AI-АДАПТАЦІЯ (опціонально)             │
│  gen-prompt.sh + prompts/*.tmpl → Claude         │
└──────────────────────────────────────────────────┘
```

**detect.sh** збирає факти про реальну систему один раз.
Усі модулі читають ці факти з `config.env` — жодних hardcoded значень.

---

## Змінні config.env

| Змінна | Дефолт | Джерело |
|---|---|---|
| `TERMUX_USER` | `$(whoami)` | shell |
| `PREFIX` | `/data/data/com.termux/files/usr` | env |
| `HOME_DIR` | `/data/data/com.termux/files/home` | env |
| `DEPLOY_DIR` | шлях до проекту | `detect.sh` |
| `TS_IP` | — | `tailscale ip` або `ip addr` |
| `SSH_PORT` | `8022` | `sshd_config` або дефолт |
| `TOR_PORT` | `9050` | `torrc` або дефолт |
| `TSPROXY_PORT` | `9888` | дефолт |
| `HAS_SSH` | yes/no | `command -v sshd` |
| `HAS_TOR` | yes/no | `command -v tor` |
| `HAS_SV` | yes/no | `command -v sv` |
| `HAS_OBFS4` | yes/no | `command -v obfs4proxy` |
| `HAS_GO` | yes/no | `command -v go` |
| `HAS_GIT` | yes/no | `command -v git` |
| `HAS_CURL` | yes/no | `command -v curl` |
| `HAS_TSPROXY` | yes/no | наявність бінарника |
| `HAS_TSBOOT` | yes/no | наявність `~/.termux/boot` |
| `BOOT_SCRIPT` | yes/no | наявність boot скрипту |
| `SV_SSHD` | running/stopped/absent | `sv status` |
| `SV_TOR` | running/stopped/absent | `sv status` |
| `SV_TSPROXY` | running/stopped/absent | `sv status` |
| `TORRC_EXISTS` | yes/no | `-f torrc` |
| `BRIDGES_COUNT` | число | `grep -c ^Bridge` |

---

## Порти — фінальний розподіл

| Сервіс | Порт | Призначення |
|---|---|---|
| sshd | 8022 | SSH доступ ззовні через Tailscale |
| tor | 9050 | Анонімний SOCKS5, стандартний Tor порт |
| ts-proxy | 9888 | Швидкий SOCKS5 для PinchTab/Chrome |

Порти не перетинаються. Tor і ts-proxy можуть працювати одночасно.

---

## Правила для модулів

Кожен модуль:

```bash
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"
```

- `grep` завжди з `|| true`
- `passwd` замість `chpasswd`
- `printf '%s\n' >> file` замість `sed /a\` з багаторядковою змінною
- Бекап перед будь-якою зміною конфігу
- Ідемпотентність: перевіряй стан перед дією

---

## Принципи

1. **Ідемпотентність** — будь-який скрипт безпечно запускати повторно
2. **Відмовостійкість** — `|| true` де потрібно; `set -euo pipefail` скрізь
3. **Без hardcode** — всі значення через `config.env`
4. **Бекап** — завжди `*.bak` перед редагуванням конфігів
5. **Один порт — один сервіс** — немає конфлікту між Tor і ts-proxy
```
---
### README.md
**Розмір:** 8,886 байт
```text
# Proxy Infrastructure — Termux + Oracle

Full geo-masking proxy stack: Android tablet (Termux/Tailscale) as Swiss exit node,
Oracle VPS as HTTP/SOCKS5 entry point with Swiss header injection, dual watchdog system.

---

## Architecture

```
Client (MacBook / GoClaw / PinchTab)
  │
  │  HTTP  → 127.0.0.1:8888   (oracle: smart_proxy.py)
  │  SOCKS5 → 127.0.0.1:1080  (oracle: smart_proxy.py)
  ▼
Oracle VPS (100.66.97.93) — swiss-proxy.service
  smart_proxy.py
  • Injects Swiss headers: Accept-Language: de-CH, Swiss Chrome UA
  • Chains upstream to Termux microsocks
  │
  │  SOCKS5 → 100.100.74.9:9888  (Tailscale VPN)
  ▼
Android Tablet — Termux (100.100.74.9)
  ts-proxy service (microsocks)
  bound to Tailscale IP only
  │
  │  exits via tablet's real network
  ▼
Internet — appears as Swiss IP (178.x.x.x)
```

### Tailscale network
| Host | Tailscale IP | Role |
|------|-------------|------|
| Oracle VPS | 100.66.97.93 | entry proxy + watchdog |
| Termux tablet | 100.100.74.9 | Swiss exit node |
| rpi4b | 100.80.16.33 | management / GoClaw |

---

## Repository Structure

```
proxy/
├── detect.sh          — detect system params, write config.env
├── deploy.sh          — run all modules in order
├── install.sh         — deploy services/ and bin/ to runtime locations
│
├── modules/           — idempotent setup modules
│   ├── tsproxy.sh     — microsocks SOCKS5 service via Tailscale
│   ├── ssh.sh         — sshd on SSH_PORT
│   ├── boot.sh        — termux-boot autostart
│   ├── tor.sh         — Tor + obfs4 (port 9050)
│   ├── tsproxy-recover.sh — recovery helpers
│   ├── verify.sh      — post-install checks
│   └── cleanup.sh     — remove services
│
├── services/          — runit service configs (source of truth)
│   ├── ts-proxy/
│   │   ├── run        — starts microsocks (with port-free wait)
│   │   ├── finish     — logs exit codes
│   │   └── log/run    — svlogd logging
│   ├── sshd/run       — openssh daemon
│   └── local-watchdog/
│       ├── run        — runs bin/watchdog-loop.sh
│       └── log/run
│
├── bin/               — runtime scripts (deployed to ~/bin/)
│   ├── restart-proxy.sh   — full restart: sv down → pkill → sv up + verify
│   ├── watchdog-loop.sh   — local 30s watchdog, calls tg-notify + restart
│   └── tg-notify.sh       — send Telegram alert
│
├── boot/
│   └── start-services.sh  — termux-boot: starts runsvdir + all services
│
└── oracle/            — oracle VPS code (reference copy)
    ├── watchdog.sh    — systemd oneshot, checks proxy every 5min, alerts Telegram + n8n
    ├── smart_proxy.py — HTTP/SOCKS5 geo-masking proxy with Swiss header injection
    ├── dashboard.sh   — CLI status dashboard
    └── systemd/
        ├── swiss-proxy.service    — smart_proxy.py systemd unit
        ├── watchdog-proxy.service — watchdog systemd unit
        └── watchdog-proxy.timer   — 5min timer
```

---

## Termux Services

Runtime location: `$PREFIX/var/service/`

### ts-proxy (microsocks)
- **Port**: 9888 on Tailscale IP only (100.100.74.9)
- **Supervisor**: runit via runsvdir
- **run script**: pkill-9 existing + wait for port free → exec microsocks
- **finish script**: logs exit code + signal to ~/logs/ts-proxy-exit.log
- **Logs**: `$PREFIX/var/log/sv/ts-proxy/current`

### sshd (openssh)
- **Port**: 8022 (set in sshd_config)
- **run script**: `exec sshd -D -e`

### local-watchdog
- **Interval**: 30s
- **Action**: curl check on 100.100.74.9:9888 → if fail → tg-notify + restart-proxy.sh

---

## Oracle Services

### swiss-proxy.service (smart_proxy.py)
- **HTTP**: 0.0.0.0:8888
- **SOCKS5**: 0.0.0.0:1080
- **Upstream**: 100.100.74.9:9888 (Termux)
- **Swiss headers**: Accept-Language: de-CH, User-Agent Chrome/Swiss

### watchdog-proxy.service / .timer
- **Schedule**: every 5 min (OnUnitActiveSec=5min)
- **Check**: `curl --socks5 100.100.74.9:9888 http://checkip.amazonaws.com/`
- **Alert**: direct Telegram API (-x "" bypasses system proxy)
- **Recovery trigger**: n8n webhook → SSH to Termux → restart-proxy.sh

---

## Key Scripts

### bin/restart-proxy.sh
Full proxy restart with flock (no concurrent runs):
1. `sv down ts-proxy`
2. `pkill -x microsocks` + `pkill -9 -x microsocks`
3. Wait until port 9888 is free
4. `sv up ts-proxy`
5. Wait up to 15s for port to open
6. Log result; restart sshd if also down

### bin/watchdog-loop.sh
Local 30s watchdog:
- Tests `curl --socks5-hostname 100.100.74.9:9888 https://api.ipify.org`
- On 2 consecutive failures: sends Telegram alert + calls restart-proxy.sh

### oracle/watchdog.sh (deployed to /opt/watchdog/)
Oracle-side watchdog with state machine:
- **down→up**: sends recovery notification
- **up→down**: sends alert + n8n webhook (triggers n8n auto-restart flow)
- State files: `/opt/watchdog/logs/proxy.state`, `proxy.state.timestamp`
- Lock: `/var/lock/watchdog-proxy.lock` (flock, prevents concurrent runs)

---

## Deploy on New Device

```bash
# 1. Clone
git clone <repo> ~/proxy
cd ~/proxy

# 2. Detect system params (writes config.env)
./detect.sh

# 3. Edit config.env — set SSH_PORT, TSPROXY_PORT, Telegram tokens
nano config.env

# 4. Full deploy (all modules)
./deploy.sh

# OR: deploy services + bin manually
./install.sh
```

### Prerequisites
- Tailscale installed and connected
- termux-boot app installed
- openssh installed (`pkg install openssh`)

---

## Oracle Setup

On oracle VPS (100.66.97.93):

```bash
# Install smart_proxy
cp oracle/smart_proxy.py /home/ubuntu/swiss-ai-proxy-legion-go/proxy/
cp oracle/systemd/swiss-proxy.service /etc/systemd/system/
systemctl enable --now swiss-proxy

# Install watchdog
cp oracle/watchdog.sh /opt/watchdog/watchdog.sh
chmod +x /opt/watchdog/watchdog.sh
cp oracle/systemd/watchdog-proxy.{service,timer} /etc/systemd/system/
systemctl enable --now watchdog-proxy.timer

# Set permissions
chown ubuntu:ubuntu /opt/watchdog/logs/*.state 2>/dev/null || true
```

Required in /opt/watchdog/.env (or exported):
```
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
N8N_WEBHOOK_URL=https://n8n.exodus.pp.ua/webhook/proxy-watchdog
```

System proxy in /etc/environment (routes oracle traffic through smart_proxy):
```
HTTP_PROXY=http://127.0.0.1:8888
HTTPS_PROXY=http://127.0.0.1:8888
NO_PROXY=localhost,127.0.0.1,100.66.97.93,100.100.74.9,...
```

---

## Fixes Applied 2026-05-03

Root cause: multiple simultaneous restarts (oracle watchdog + local watchdog + n8n)
caused "Address already in use" loop → microsocks never stayed up.

1. **ts-proxy/run**: added `pkill -9` + port-free wait loop before `exec microsocks`
2. **ts-proxy/finish**: new script — logs exit code + signal for diagnostics
3. **restart-proxy.sh**: added `flock` at top — prevents concurrent restarts
4. **oracle watchdog**: `--socks5-hostname` → `--socks5` (DNS stays local, not through proxy)
5. **oracle watchdog**: `send_notification` changed from Cloudflare Worker → direct Telegram API
   with `-x ""` (bypasses system proxy — critical when Termux proxy is DOWN)
6. **oracle watchdog**: removed `--retry 2` from n8n webhook call (was causing double execution)
7. **oracle watchdog**: increased `--max-time` to 25s on n8n call (SSH execution takes ~9s)
8. **oracle watchdog**: `TEST_URL` → `http://checkip.amazonaws.com/` (more reliable than example.com)

---

## Troubleshooting

### Proxy not working
```bash
# Check microsocks status
sv status $PREFIX/var/service/ts-proxy

# Check exit log
tail ~/logs/ts-proxy-exit.log

# Manual restart
~/bin/restart-proxy.sh

# Test from oracle
ssh -i oracle/ssh-key ubuntu@100.66.97.93 \
  "curl --socks5 100.100.74.9:9888 http://checkip.amazonaws.com/"
```

### Watchdog false alerts
- Check if oracle system proxy (HTTP_PROXY) is routing watchdog's curl through Termux
- Watchdog must use `-x ""` for Telegram notifications
- Check `/opt/watchdog/logs/watchdog.log` on oracle for details

### Double restart loop
```bash
# Check for concurrent restarts
tail ~/logs/restart-proxy.log | grep SKIP

# Check ts-proxy exit log for SIGTERM (signal 15 = intentional kill)
tail ~/logs/ts-proxy-exit.log
```

### Port already in use
```bash
# Find what's holding port 9888
netstat -tlnp | grep 9888
# Force kill all microsocks
pkill -9 -x microsocks
```

---

## Ports Reference
| Port | Protocol | Host | Purpose |
|------|----------|------|---------|
| 8022 | SSH | Termux | SSH access |
| 9888 | SOCKS5 | Termux | Exit proxy (bound to Tailscale IP) |
| 9050 | SOCKS5 | Termux | Tor exit (anonymous) |
| 8888 | HTTP | Oracle | Entry proxy (Swiss header injection) |
| 1080 | SOCKS5 | Oracle | Entry proxy |

```
---
### deploy.sh
**Розмір:** 6,032 байт
```bash
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
```
---
### detect.sh
**Розмір:** 6,442 байт
```bash
#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# detect.sh — збір стану системи → config.env
# Запускати першим і після будь-яких змін у системі.
# ============================================================
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$DEPLOY_DIR/config.env"

PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
HOME_DIR="${HOME:-/data/data/com.termux/files/home}"

echo "════════════════════════════════════════"
echo " Termux Deploy — System Detection"
echo "════════════════════════════════════════"

_d() { printf "  %-22s %s\n" "$1" "$2"; }
check_cmd() { command -v "$1" &>/dev/null && echo "yes" || echo "no"; }

# ── Базове середовище ────────────────────────────────────────
echo; echo "[ Base environment ]"
TERMUX_USER=$(whoami)
_d "User:"    "$TERMUX_USER"
_d "PREFIX:"  "$PREFIX"
_d "HOME:"    "$HOME_DIR"

# ── Tailscale IP ─────────────────────────────────────────────
echo; echo "[ Tailscale ]"
TS_IP=""

if command -v tailscale &>/dev/null; then
    TS_IP=$(tailscale ip -4 2>/dev/null | head -1 || true)
fi

if [ -z "$TS_IP" ]; then
    TS_IP=$(ip addr 2>/dev/null \
        | grep -oE '100\.[0-9]+\.[0-9]+\.[0-9]+' \
        | head -1 || true)
fi

if [ -n "$TS_IP" ]; then
    _d "Tailscale IP:" "$TS_IP"
else
    echo "  ⚠️  Tailscale IP not found — enter manually"
    printf "  Enter Tailscale IP (or Enter to skip): "
    read -r _ts
    TS_IP="${_ts:-unknown}"
fi

# ── Пакети ───────────────────────────────────────────────────
echo; echo "[ Installed packages ]"

HAS_SSH=$(check_cmd sshd)
HAS_TOR=$(check_cmd tor)
HAS_SV=$(check_cmd sv)
HAS_OBFS4=$(check_cmd obfs4proxy)
HAS_GO=$(check_cmd go)
HAS_GIT=$(check_cmd git)
HAS_CURL=$(check_cmd curl)

_d "openssh:"          "$HAS_SSH"
_d "tor:"              "$HAS_TOR"
_d "termux-services:"  "$HAS_SV"
_d "obfs4proxy:"       "$HAS_OBFS4"
_d "golang:"           "$HAS_GO"
_d "git:"              "$HAS_GIT"
_d "curl:"             "$HAS_CURL"

# ts-proxy backend: prefer microsocks, fall back to legacy binary
TSPROXY_BIN="$HOME_DIR/ts-proxy/ts-proxy"
HAS_TSPROXY="no"
if command -v microsocks &>/dev/null || [ -f "$TSPROXY_BIN" ]; then
    HAS_TSPROXY="yes"
fi
_d "ts-proxy binary:"  "$HAS_TSPROXY"

# ── Termux:Boot ──────────────────────────────────────────────
echo; echo "[ Auto-start ]"
HAS_TSBOOT="no"
[ -d "$HOME_DIR/.termux/boot" ] && HAS_TSBOOT="yes"

BOOT_SCRIPT="no"
[ -f "$HOME_DIR/.termux/boot/start-services.sh" ] && BOOT_SCRIPT="yes"

_d "Termux:Boot dir:"  "$HAS_TSBOOT"
_d "Boot script:"      "$BOOT_SCRIPT"

# ── Стан сервісів ────────────────────────────────────────────
echo; echo "[ Services ]"

svc_status() {
    local name="$1"
    [ "$HAS_SV" = "no" ] && { echo "no-sv"; return; }
    local p="$PREFIX/var/service/$name"
    [ ! -d "$p" ] && { echo "absent"; return; }
    sv status "$p" 2>/dev/null | grep -oE '^(run|down)' || echo "unknown"
}

SV_SSHD=$(svc_status sshd)
SV_TOR=$(svc_status tor)
SV_TSPROXY=$(svc_status ts-proxy)

_d "sshd:"     "$SV_SSHD"
_d "tor:"      "$SV_TOR"
_d "ts-proxy:" "$SV_TSPROXY"

# ── Порти ────────────────────────────────────────────────────
echo; echo "[ Ports ]"

SSH_PORT=8022
TOR_PORT=9050
TSPROXY_PORT=9888

# Читаємо з sshd_config якщо є
if [ -f "$PREFIX/etc/ssh/sshd_config" ]; then
    _p=$(grep -iE '^Port ' "$PREFIX/etc/ssh/sshd_config" 2>/dev/null \
         | awk '{print $2}' | head -1 || true)
    [ -n "$_p" ] && SSH_PORT="$_p"
fi

# Читаємо з torrc якщо є
if [ -f "$PREFIX/etc/tor/torrc" ]; then
    _p=$(grep '^SOCKSPort' "$PREFIX/etc/tor/torrc" 2>/dev/null \
         | grep -oE '[0-9]+$' | head -1 || true)
    [ -n "$_p" ] && TOR_PORT="$_p"
fi

_d "SSH port:"          "$SSH_PORT"
_d "Tor SOCKS5 port:"   "$TOR_PORT"
_d "ts-proxy port:"     "$TSPROXY_PORT"

# ── Tor bridges ──────────────────────────────────────────────
echo; echo "[ Tor configuration ]"

BRIDGES_COUNT=0
TORRC_EXISTS="no"

if [ -f "$PREFIX/etc/tor/torrc" ]; then
    TORRC_EXISTS="yes"
    BRIDGES_COUNT=$(grep -c '^Bridge obfs4' "$PREFIX/etc/tor/torrc" || true)
fi

_d "torrc exists:"   "$TORRC_EXISTS"
_d "Bridge lines:"   "$BRIDGES_COUNT"

# ── Запис config.env ─────────────────────────────────────────
echo; echo "[ Writing config.env ]"

cat > "$CONFIG" << EOF
# ============================================================
# config.env — auto-generated by detect.sh
# $(date)
# DO NOT edit manually — re-run detect.sh to refresh
# ============================================================

TERMUX_USER="$TERMUX_USER"
PREFIX="$PREFIX"
HOME_DIR="$HOME_DIR"
DEPLOY_DIR="$DEPLOY_DIR"

TS_IP="$TS_IP"

SSH_PORT="$SSH_PORT"
TOR_PORT="$TOR_PORT"
TSPROXY_PORT="$TSPROXY_PORT"

HAS_SSH="$HAS_SSH"
HAS_TOR="$HAS_TOR"
HAS_SV="$HAS_SV"
HAS_OBFS4="$HAS_OBFS4"
HAS_GO="$HAS_GO"
HAS_GIT="$HAS_GIT"
HAS_CURL="$HAS_CURL"
HAS_TSPROXY="$HAS_TSPROXY"

HAS_TSBOOT="$HAS_TSBOOT"
BOOT_SCRIPT="$BOOT_SCRIPT"

SV_SSHD="$SV_SSHD"
SV_TOR="$SV_TOR"
SV_TSPROXY="$SV_TSPROXY"

TORRC_EXISTS="$TORRC_EXISTS"
BRIDGES_COUNT="$BRIDGES_COUNT"
EOF

_d "Saved:" "$CONFIG"

echo
echo "════════════════════════════════════════"
echo " Detection complete. Next: ./deploy.sh"
echo "════════════════════════════════════════"
```
---
### install.sh
**Розмір:** 1,342 байт
```bash
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
```
---
### bin/restart-proxy.sh
**Розмір:** 2,460 байт
```bash
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
```
---
### bin/tg-notify.sh
**Розмір:** 309 байт
```bash
#!/data/data/com.termux/files/usr/bin/bash
# tg-notify.sh MESSAGE
BOT_TOKEN="8508516661:AAEQBWvlBk3v62nd5ut3ei70TPFJTkV9LMs"
CHAT_ID="6412868393"
MSG="$1"
curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage"   -d "chat_id=${CHAT_ID}"   --data-urlencode "text=${MSG}"   --max-time 10 || true
```
---
### bin/watchdog-loop.sh
**Розмір:** 3,054 байт
```bash
#!/data/data/com.termux/files/usr/bin/bash
# watchdog-loop.sh — monitors ts-proxy (microsocks) and sshd, auto-restarts
# Runit service: local-watchdog
# NOTE: microsocks binds to 100.100.74.9:9888 (Tailscale IP), NOT 127.0.0.1

PREFIX="/data/data/com.termux/files/usr"
HOME_DIR="/data/data/com.termux/files/home"
PROXY_HOST="100.100.74.9"    # Tailscale IP — microsocks binds here
PROXY_PORT="9888"
CHECK_INTERVAL=30
COOLDOWN=300
FLAG_FILE="$PREFIX/tmp/watchdog_proxy_down.flag"
LAST_ALERT_FILE="$PREFIX/tmp/watchdog_last_alert"
LOG="$HOME_DIR/logs/watchdog-loop.log"

mkdir -p "$HOME_DIR/logs"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $1" | tee -a "$LOG"; }

notify() {
    local msg="$1"
    if [ -f "$LAST_ALERT_FILE" ]; then
        local last now diff
        last=$(cat "$LAST_ALERT_FILE")
        now=$(date +%s)
        diff=$(( now - last ))
        if [ "$diff" -lt "$COOLDOWN" ]; then
            log "Cooldown active (${diff}s < ${COOLDOWN}s), skipping notify"
            return
        fi
    fi
    date +%s > "$LAST_ALERT_FILE"
    "$HOME_DIR/bin/tg-notify.sh" "$msg" &
}

check_port() {
    # microsocks binds to Tailscale IP, not localhost
    bash -c "echo > /dev/tcp/$PROXY_HOST/$PROXY_PORT" 2>/dev/null
}

check_sshd() {
    sv status "$PREFIX/var/service/sshd" 2>/dev/null | grep -q '^run:'
}

log "=== watchdog-loop started (interval=${CHECK_INTERVAL}s, cooldown=${COOLDOWN}s) ==="
log "Monitoring: $PROXY_HOST:$PROXY_PORT (ts-proxy/microsocks)"

while true; do
    # --- ts-proxy check ---
    if check_port; then
        if [ -f "$FLAG_FILE" ]; then
            rm -f "$FLAG_FILE"
            log "ts-proxy RECOVERED on $PROXY_HOST:$PROXY_PORT"
            notify "✅ [tab-s8-ultra] ts-proxy RECOVERED on port $PROXY_PORT"
        fi
    else
        if [ ! -f "$FLAG_FILE" ]; then
            touch "$FLAG_FILE"
            log "ts-proxy DOWN on $PROXY_HOST:$PROXY_PORT — restarting..."
            notify "⚠️ [tab-s8-ultra] ts-proxy DOWN — auto-restarting..."

            "$HOME_DIR/bin/restart-proxy.sh" >> "$LOG" 2>&1

            sleep 5

            if check_port; then
                rm -f "$FLAG_FILE"
                log "ts-proxy restarted successfully"
                notify "✅ [tab-s8-ultra] ts-proxy restarted OK"
            else
                log "ts-proxy STILL down after restart"
                notify "❌ [tab-s8-ultra] ts-proxy STILL DOWN after restart — manual intervention needed"
            fi
        else
            log "ts-proxy still down (flag exists, restart already attempted)"
        fi
    fi

    # --- sshd check (always, independent) ---
    if ! check_sshd; then
        log "sshd DOWN — restarting via sv..."
        sv up "$PREFIX/var/service/sshd" >> "$LOG" 2>&1 || true
        sleep 3
        if check_sshd; then
            log "sshd restarted OK"
            notify "⚠️ [tab-s8-ultra] sshd was down — auto-restarted OK"
        else
            log "sshd STILL down after restart"
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
```
---
### boot/start-services.sh
**Розмір:** 1,165 байт
```bash
#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot auto-start script
# Generated by termux-deploy/modules/boot.sh
#
# ВАЖЛИВО: Termux:Boot запускає скрипти в порожньому середовищі.
# Усі змінні середовища треба експортувати явно тут.
export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH
export HOME=/data/data/com.termux/files/home
export PREFIX=/data/data/com.termux/files/usr
export LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib

# Тримаємо wake lock щоб сервіси не вбивалися системою
termux-wake-lock

# Ensure runsvdir is running (manages all runit services incl. local-watchdog)
pgrep -x runsvdir >/dev/null 2>&1 || \
  nohup runsvdir "$PREFIX/var/service" >/dev/null 2>&1 &
sleep 2
sv up "$PREFIX/var/service/local-watchdog" 2>/dev/null || true

sv up "$PREFIX/var/service/sshd" 2>/dev/null || true
sv up "$PREFIX/var/service/tor" 2>/dev/null || true
sv up "$PREFIX/var/service/ts-proxy" 2>/dev/null || true
sv up /data/data/com.termux/files/usr/var/service/privoxy 2>/dev/null || true
```
---
### modules/boot.sh
**Розмір:** 4,370 байт
```bash
#!/data/data/com.termux/files/usr/bin/bash
# modules/boot.sh — створення Termux:Boot скрипту автозапуску
# Важливо: Termux:Boot запускає скрипти в порожньому середовищі,
# тому PATH / HOME / PREFIX треба експортувати явно всередині скрипту.
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

BOOT_DIR="$HOME_DIR/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/start-services.sh"

echo
echo "════════════════════════════════════════"
echo " Termux:Boot Auto-start"
echo "════════════════════════════════════════"

# ── Перевірка ────────────────────────────────────────────────
echo
if [ "$HAS_TSBOOT" = "no" ]; then
    echo "  ⚠️  ~/.termux/boot/ not found."
    echo "     Install Termux:Boot from F-Droid or Google Play,"
    echo "     then open the app once to activate it."
    echo "     Creating directory anyway..."
fi

mkdir -p "$BOOT_DIR"

# ── Бекап існуючого скрипту ───────────────────────────────────
if [ -f "$BOOT_SCRIPT" ]; then
    cp "$BOOT_SCRIPT" "$BOOT_SCRIPT.bak"
    echo "  💾  backup: $BOOT_SCRIPT.bak"
fi

# ── Визначаємо які сервіси активні ───────────────────────────
# Додаємо сервіс тільки якщо його service dir існує
SERVICES=()
[ -d "$PREFIX/var/service/local-watchdog" ] && SERVICES+=(local-watchdog)
[ -d "$PREFIX/var/service/sshd"     ] && SERVICES+=(sshd)
[ -d "$PREFIX/var/service/tor"      ] && SERVICES+=(tor)
[ -d "$PREFIX/var/service/ts-proxy" ] && SERVICES+=("ts-proxy")

if [ "${#SERVICES[@]}" -eq 0 ]; then
    echo "  ⚠️  No configured services found."
    echo "     Run ssh.sh / tor.sh / tsproxy.sh first, then re-run boot.sh"
fi

# ── Генерація boot script ─────────────────────────────────────
{
cat << 'HEADER'
#!/data/data/com.termux/files/usr/bin/bash
# Termux:Boot auto-start script
# Generated by termux-deploy/modules/boot.sh
#
# ВАЖЛИВО: Termux:Boot запускає скрипти в порожньому середовищі.
# Усі змінні середовища треба експортувати явно тут.
export PATH=/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/sbin:$PATH
export HOME=/data/data/com.termux/files/home
export PREFIX=/data/data/com.termux/files/usr
export LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib

# Тримаємо wake lock щоб сервіси не вбивалися системою
termux-wake-lock

# Запустити runit supervisor (обов'язково перед sv up)
pgrep -x runsvdir >/dev/null 2>&1 || \
  nohup runsvdir "$PREFIX/var/service" >/dev/null 2>&1 &
sleep 2

HEADER

# Додаємо рядок для кожного активного сервісу
for svc in "${SERVICES[@]}"; do
    echo "sv up \"\$PREFIX/var/service/$svc\" 2>/dev/null || true"
done
} > "$BOOT_SCRIPT"

chmod +x "$BOOT_SCRIPT"

echo "  ✅  Created: $BOOT_SCRIPT"
echo "  Services queued for auto-start:"
for svc in "${SERVICES[@]}"; do
    echo "       • $svc"
done

echo
echo "════════════════════════════════════════"
echo " Boot script ready."
echo
echo "  File: $BOOT_SCRIPT"
echo
if [ "${#SERVICES[@]}" -eq 0 ]; then
    echo "  ⚠️  No services added yet."
    echo "     Deploy services first, then run boot.sh again."
else
    echo "  Services will auto-start on next Termux open:"
    for svc in "${SERVICES[@]}"; do
        printf "    • %s\n" "$svc"
    done
fi
echo
echo "  Requires: Termux:Boot app (F-Droid / Google Play)"
echo "════════════════════════════════════════"
```
---
### modules/bridges.sh
**Розмір:** 5,464 байт
```bash
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
```
---
### modules/cleanup.sh
**Розмір:** 4,083 байт
```bash
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
```
---
### modules/ssh.sh
**Розмір:** 4,559 байт
```bash
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
```
---
### modules/tor.sh
**Розмір:** 5,292 байт
```bash
#!/data/data/com.termux/files/usr/bin/bash
# modules/tor.sh — Tor + obfs4 SOCKS5 проксі на порту TOR_PORT (9050)
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

TORRC="$PREFIX/etc/tor/torrc"
SVC_DIR="$PREFIX/var/service/tor"

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
echo " Tor + obfs4  (port $TOR_PORT)"
echo "════════════════════════════════════════"

# ── 1. Пакети ────────────────────────────────────────────────
echo; echo "[1/4] Packages..."

pkgs=()
[ "$HAS_TOR"   = "no" ] && pkgs+=(tor)
[ "$HAS_OBFS4" = "no" ] && pkgs+=(obfs4proxy)

if [ "${#pkgs[@]}" -gt 0 ]; then
    if pkg install -y "${pkgs[@]}"; then
        echo "  ✅  installed: ${pkgs[*]}"
    else
        echo "❌  pkg install failed: ${pkgs[*]}"
        exit 1
    fi
else
    echo "  ✅  tor and obfs4proxy present"
fi

# ── 2. torrc ─────────────────────────────────────────────────
echo; echo "[2/4] torrc..."

mkdir -p "$PREFIX/var/lib/tor" "$PREFIX/var/log/tor"

# Зберігаємо існуючі bridges і робимо бекап перед перезаписом
existing_bridges=""
if [ -f "$TORRC" ]; then
    existing_bridges=$(grep '^Bridge obfs4' "$TORRC" || true)
    cp "$TORRC" "$TORRC.bak"
    echo "  💾  backup: $TORRC.bak"
fi

# Звільнити порт якщо зайнятий
kill "$(lsof -t -i:"$TOR_PORT" 2>/dev/null)" 2>/dev/null || true

# Записуємо базовий конфіг
cat > "$TORRC" << TOREOF
SOCKSPort 127.0.0.1:$TOR_PORT
Log notice file $PREFIX/var/log/tor/notices.log
DataDirectory $PREFIX/var/lib/tor
ExitPolicy reject *:*
UseBridges 1
ClientTransportPlugin obfs4 exec $PREFIX/bin/obfs4proxy

# ⚠️  ДОДАЙТЕ МОСТИ ТУТ:
# https://bridges.torproject.org/  або  @GetBridgesBot → /bridges obfs4
#
# Формат:
# Bridge obfs4 <IP>:<PORT> <FINGERPRINT> cert=<CERT> iat-mode=0
TOREOF

# Відновлюємо збережені bridges — не стираємо те, що вже є
if [ -n "$existing_bridges" ]; then
    printf '%s\n' "$existing_bridges" >> "$TORRC"
    bridge_count=$(printf '%s\n' "$existing_bridges" | wc -l | tr -d ' ')
    echo "  ✅  torrc written, $bridge_count bridge(s) preserved"
else
    echo "  ✅  torrc written (port $TOR_PORT)"
    echo "  ⚠️   No bridges — add via: deploy.sh → [5]"
fi

# ── 3. Сервіс ────────────────────────────────────────────────
echo; echo "[3/4] Service..."

_ensure_sv

if [ -d "$SVC_DIR" ]; then
    sv down "$SVC_DIR" 2>/dev/null || true
fi

mkdir -p "$SVC_DIR/log"

cat > "$SVC_DIR/run" << RUNEOF
#!/data/data/com.termux/files/usr/bin/sh
exec tor -f $TORRC 2>&1
RUNEOF
chmod +x "$SVC_DIR/run"

sv-enable tor 2>/dev/null || true
sv up "$SVC_DIR" 2>/dev/null || true
sleep 3

if sv status "$SVC_DIR" 2>/dev/null | grep -q '^run:'; then
    echo "  ✅  tor running"
else
    echo "  ⚠️   Tor likely waiting for bridges — add them then restart"
    echo "       sv down $SVC_DIR && sv up $SVC_DIR"
fi

# ── 4. Boot script ───────────────────────────────────────────
echo; echo "[4/4] Boot script..."

BOOT="$HOME_DIR/.termux/boot/start-services.sh"
if [ -f "$BOOT" ]; then
    if ! grep -q 'var/service/tor' "$BOOT"; then
        printf 'sv up "%s"\n' "$SVC_DIR" >> "$BOOT"
        echo "  ✅  added to boot script"
    else
        echo "  ✅  already in boot script"
    fi
else
    echo "  ⚠️   boot script not found — run modules/boot.sh first"
fi

# ── Підсумок ─────────────────────────────────────────────────
echo
echo "════════════════════════════════════════"
echo " Tor ready  (after adding bridges)"
echo "  SOCKS5:  127.0.0.1:$TOR_PORT"
echo "  Bridges: ./deploy.sh → [5] Update Tor bridges"
echo "  Logs:    tail -f $PREFIX/var/log/tor/notices.log"
echo "════════════════════════════════════════"
```
---
### modules/tsproxy-recover.sh
**Розмір:** 2,032 байт
```bash
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
```
---
### modules/tsproxy.sh
**Розмір:** 5,224 байт
```bash
#!/data/data/com.termux/files/usr/bin/bash
# modules/tsproxy.sh — стабільний SOCKS5 через Tailscale для PinchTab/Chrome
# Порт: TSPROXY_PORT (9888) — окремий від Tor (9050), немає конфлікту
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

SVC_DIR="$PREFIX/var/service/ts-proxy"
LOG_DIR="$PREFIX/var/log/sv/ts-proxy"

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
echo " ts-proxy — SOCKS5 via Tailscale"
echo " Port: $TSPROXY_PORT  (Chrome/PinchTab)"
echo "════════════════════════════════════════"

# ── 1. Перевірки ─────────────────────────────────────────────
echo; echo "[1/5] Prerequisites..."

if [ "$TS_IP" = "unknown" ] || [ -z "$TS_IP" ]; then
    echo "❌ Tailscale IP not detected. Is Tailscale running?"
    exit 1
fi
echo "  ✅  Tailscale IP: $TS_IP"

# ── 2. Залежності ────────────────────────────────────────────
echo; echo "[2/5] Dependencies..."

if ! command -v microsocks >/dev/null 2>&1; then
    if pkg install -y microsocks; then
        echo "  ✅  installed: microsocks"
    else
        echo "❌  pkg install failed: microsocks"
        exit 1
    fi
else
    echo "  ✅  microsocks present"
fi

# ── 3. Бекенд ────────────────────────────────────────────────
echo; echo "[3/5] Backend..."
echo "  Using microsocks bound to Tailscale IP only"

# ── 4. Сервіс ────────────────────────────────────────────────
echo; echo "[4/5] Configuring service..."

_ensure_sv

if [ -d "$SVC_DIR" ]; then
    sv down "$SVC_DIR" 2>/dev/null || true
    sleep 1
fi

mkdir -p "$SVC_DIR/log" "$LOG_DIR"

cat > "$SVC_DIR/run" <<'RUNEOF'
#!/data/data/com.termux/files/usr/bin/sh
pkill -x microsocks 2>/dev/null || true
pkill -9 -x microsocks 2>/dev/null || true
i=0
while [ $i -lt 10 ]; do
    bash -c "exec 3<>/dev/tcp/TSPROXY_IP/TSPROXY_PORT_PLACEHOLDER" 2>/dev/null || break
    sleep 1
    i=$((i+1))
done
exec microsocks -i TSPROXY_IP -p TSPROXY_PORT_PLACEHOLDER 2>&1
RUNEOF
chmod +x "$SVC_DIR/run"
sed -i "s/TSPROXY_IP/$TS_IP/g; s/TSPROXY_PORT_PLACEHOLDER/$TSPROXY_PORT/g" "$SVC_DIR/run"

cat > "$SVC_DIR/finish" <<'FINEOF'
#!/data/data/com.termux/files/usr/bin/sh
echo "$(date +%Y-%m-%dT%H:%M:%S) ts-proxy EXIT code=$1 signal=$2" \
  >> /data/data/com.termux/files/home/logs/ts-proxy-exit.log
FINEOF
chmod +x "$SVC_DIR/finish"

cat > "$SVC_DIR/log/run" <<LOGEOF
#!/data/data/com.termux/files/usr/bin/sh
exec svlogd -tt $LOG_DIR
LOGEOF
chmod +x "$SVC_DIR/log/run"

sv-enable ts-proxy 2>/dev/null || true
rm -f "$SVC_DIR/down" 2>/dev/null || true  # sv-enable has -u/-z bug
sv up "$SVC_DIR" 2>/dev/null || true
sleep 2

if sv status "$SVC_DIR" 2>/dev/null | grep -q '^run:'; then
    echo "  ✅  ts-proxy running on $TS_IP:$TSPROXY_PORT"
else
    echo "  ⚠️   check: sv status $SVC_DIR"
fi

# ── 5. Boot script ───────────────────────────────────────────
echo; echo "[5/5] Boot script..."

BOOT="$HOME_DIR/.termux/boot/start-services.sh"
if [ -f "$BOOT" ]; then
    if ! grep -q 'ts-proxy' "$BOOT"; then
        printf 'sv up "%s"\n' "$SVC_DIR" >> "$BOOT"
        echo "  ✅  added to boot script"
    else
        echo "  ✅  already in boot script"
    fi
else
    echo "  ⚠️   boot script not found — run modules/boot.sh first"
fi

echo
echo "════════════════════════════════════════"
echo " ts-proxy ready"
echo
echo "  Remote:   $TS_IP:$TSPROXY_PORT   (від MacBook через Tailscale)"
echo
echo "  Chrome / PinchTab flags:"
echo "  --proxy-server=\"socks5://$TS_IP:$TSPROXY_PORT\""
echo "  --host-resolver-rules=\"MAP * ~NOTFOUND, EXCLUDE localhost\""
echo
echo "  Logs: tail -f $LOG_DIR/current"
echo "  Test: curl --socks5-hostname $TS_IP:$TSPROXY_PORT https://ipinfo.io"
echo "════════════════════════════════════════"
```
---
### modules/verify.sh
**Розмір:** 3,978 байт
```bash
#!/data/data/com.termux/files/usr/bin/bash
# modules/verify.sh — перевірка всіх сервісів системи
set -euo pipefail

CONFIG="${1:-$(dirname "$0")/../config.env}"
[ ! -f "$CONFIG" ] && { echo "❌ Run ./detect.sh first"; exit 1; }
source "$CONFIG"

echo
echo "════════════════════════════════════════"
echo " Service Verification"
echo "════════════════════════════════════════"
echo

_ok()   { printf "  ✅  %-28s %s\n" "$1" "$2"; }
_warn() { printf "  ⚠️   %-28s %s\n" "$1" "$2"; }
_fail() { printf "  ❌  %-28s %s\n" "$1" "$2"; }

_svc_check() {
    local name="$1" port="$2" has_pkg="$3"

    if [ "$has_pkg" = "no" ]; then
        _fail "$name" "package not installed"
        return
    fi

    local svc_path="$PREFIX/var/service/$name"
    if [ ! -d "$svc_path" ]; then
        _fail "$name" "service not configured (run deploy.sh)"
        return
    fi

    local status
    status=$(sv status "$svc_path" 2>/dev/null | grep -oE '^(run|down)' || echo "unknown")

    if [ "$status" = "run" ]; then
        _ok "$name" "running  port $port"
    else
        _fail "$name" "not running ($status)"
    fi
}

# ── Сервіси ──────────────────────────────────────────────────
_svc_check "sshd"     "$SSH_PORT"     "$HAS_SSH"
_svc_check "tor"      "$TOR_PORT"     "$HAS_TOR"
_svc_check "ts-proxy" "$TSPROXY_PORT" "$HAS_TSPROXY"

echo

# ── Tor bridges ──────────────────────────────────────────────
if [ "$BRIDGES_COUNT" -gt 0 ]; then
    _ok "Tor bridges" "$BRIDGES_COUNT configured"
else
    _warn "Tor bridges" "none — Tor may not connect outside CH"
fi

# ── Termux:Boot ──────────────────────────────────────────────
if [ "$BOOT_SCRIPT" = "yes" ]; then
    _ok "Termux:Boot script" "present"
else
    _warn "Termux:Boot script" "missing — services won't auto-start"
fi

# ── Tailscale ────────────────────────────────────────────────
if [ "$TS_IP" != "unknown" ] && [ -n "$TS_IP" ]; then
    _ok "Tailscale" "$TS_IP"
else
    _warn "Tailscale" "IP not detected"
fi

echo

# ── Опціональний тест проксі ─────────────────────────────────
if [ "$HAS_CURL" = "yes" ]; then
    echo "  Test which proxy?"
    echo "  [1] ts-proxy (port $TSPROXY_PORT)"
    echo "  [2] Tor      (port $TOR_PORT)"
    echo "  [3] Skip"
    printf "  Choice: "
    read -r _t

    _run_test() {
        local target="$1" label="$2"
        echo "  Testing $label via $target ..."
        local resp
        resp=$(curl --socks5-hostname "$target" \
               -s --max-time 15 https://check.torproject.org/api/ip 2>&1 || true)
        if echo "$resp" | grep -q '"IsTor":true'; then
            _ok "$label test" "IsTor:true — working"
        elif echo "$resp" | grep -q '"IP"'; then
            _ok "$label test" "connected (not via Tor exit)"
            echo "      Response: $resp"
        else
            _fail "$label test" "no response: $resp"
        fi
    }

    case "$_t" in
        1) _run_test "$TS_IP:$TSPROXY_PORT" "ts-proxy" ;;
        2) _run_test "127.0.0.1:$TOR_PORT"  "Tor" ;;
        *) echo "  Skipped." ;;
    esac
fi

echo
echo "  SSH access:  ssh -p $SSH_PORT $TERMUX_USER@$TS_IP"
echo "  ts-proxy:    socks5://$TS_IP:$TSPROXY_PORT  (PinchTab/Chrome)"
echo "  Tor:         socks5://127.0.0.1:$TOR_PORT"
echo "  Logs:        tail -f $PREFIX/var/log/tor/notices.log"
echo
```
---
### oracle/dashboard.sh
**Розмір:** 804 байт
```bash
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
```
---
### oracle/smart_proxy.py
**Розмір:** 9,091 байт
```python
#!/usr/bin/env python3
"""
smart_proxy.py — Swiss geo-masking proxy
  HTTP  proxy : 0.0.0.0:8888  (handles CONNECT for HTTPS + plain HTTP)
  SOCKS5 proxy: 0.0.0.0:1080  (chains to upstream)

All traffic is forwarded through tablet SOCKS5 → Swiss VPN → Zürich exit IP.
Swiss headers injected on every plain-HTTP request.
"""

import asyncio
import struct
import logging
import re

import aiohttp
from aiohttp_socks import ProxyConnector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

UPSTREAM      = ('100.100.74.9', 9888)   # tablet SOCKS5 → Swiss VPN
HTTP_PORT     = 8888
SOCKS5_PORT   = 1080
BIND          = '0.0.0.0'
BUF           = 65536

SWISS_HEADERS = {
    'Accept-Language': 'de-CH,de;q=0.9,fr-CH;q=0.8,en;q=0.7',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
}
STRIP_REQ = {
    'x-forwarded-for', 'x-real-ip', 'via', 'forwarded',
    'proxy-connection', 'proxy-authorization',
}


# ── Upstream SOCKS5 connect ───────────────────────────────────────────────────

async def upstream_connect(host: str, port: int):
    """Open a tunnel through the tablet SOCKS5 to (host, port)."""
    r, w = await asyncio.open_connection(*UPSTREAM)
    # Handshake
    w.write(b'\x05\x01\x00')
    await w.drain()
    if (await r.readexactly(2))[1] != 0x00:
        raise ConnectionError('upstream auth failed')
    # CONNECT
    hb = host.encode()
    w.write(b'\x05\x01\x00\x03' + bytes([len(hb)]) + hb + struct.pack('!H', port))
    await w.drain()
    rep = await r.readexactly(4)
    if rep[1] != 0x00:
        raise ConnectionError(f'upstream connect error {rep[1]}')
    atype = rep[3]
    if   atype == 1: await r.readexactly(4)
    elif atype == 3: await r.readexactly((await r.readexactly(1))[0])
    elif atype == 4: await r.readexactly(16)
    await r.readexactly(2)
    return r, w


# ── Pipe ─────────────────────────────────────────────────────────────────────

async def pipe(src, dst):
    try:
        while True:
            data = await src.read(BUF)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:
        pass
    finally:
        try: dst.close()
        except Exception: pass


# ── HTTP proxy (raw TCP) ──────────────────────────────────────────────────────

async def http_proxy_client(cr, cw):
    """Handle one HTTP proxy client connection."""
    peer = cw.get_extra_info('peername', ('?', 0))[0]
    try:
        # Read request line + headers (up to 16 KB)
        raw = b''
        while b'\r\n\r\n' not in raw:
            chunk = await asyncio.wait_for(cr.read(4096), timeout=15)
            if not chunk:
                return
            raw += chunk
            if len(raw) > 16384:
                break

        head, _, body_start = raw.partition(b'\r\n\r\n')
        lines = head.decode('utf-8', errors='replace').split('\r\n')
        req_line = lines[0]
        method, path, _ = req_line.split(' ', 2)

        # ── CONNECT (HTTPS tunnel) ──────────────────────────────────────────
        if method == 'CONNECT':
            host, _, port = path.rpartition(':')
            port = int(port or 443)
            logger.info(f"CONNECT {host}:{port} from {peer}")
            try:
                ur, uw = await upstream_connect(host, port)
            except Exception as e:
                cw.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
                await cw.drain()
                return
            cw.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
            await cw.drain()
            await asyncio.gather(pipe(cr, uw), pipe(ur, cw))
            return

        # ── Plain HTTP ──────────────────────────────────────────────────────
        # Parse headers
        req_headers = {}
        for ln in lines[1:]:
            if ':' in ln:
                k, _, v = ln.partition(':')
                req_headers[k.strip().lower()] = v.strip()

        host = req_headers.get('host', '')
        logger.info(f"{method} {path[:70]} from {peer}")

        # Build clean headers for upstream
        fwd_headers = {
            k: v for k, v in req_headers.items()
            if k not in STRIP_REQ
        }
        fwd_headers.update({k.lower(): v for k, v in SWISS_HEADERS.items()})

        # Read remaining body if Content-Length present
        body = body_start
        clen = int(req_headers.get('content-length', 0))
        while len(body) < clen:
            body += await cr.read(clen - len(body))

        # Forward via aiohttp through upstream SOCKS5
        try:
            connector = ProxyConnector.from_url(
                f'socks5://{UPSTREAM[0]}:{UPSTREAM[1]}', ssl=False
            )
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.request(
                    method=method,
                    url=path if path.startswith('http') else f'http://{host}{path}',
                    headers=fwd_headers,
                    data=body or None,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    rb = await resp.read()
                    status_line = f'HTTP/1.1 {resp.status} {resp.reason}\r\n'
                    resp_hdrs = ''.join(
                        f'{k}: {v}\r\n'
                        for k, v in resp.headers.items()
                        if k.lower() not in {'transfer-encoding'}
                    )
                    cw.write(
                        status_line.encode() +
                        resp_hdrs.encode() +
                        b'\r\n' + rb
                    )
                    await cw.drain()
        except Exception as e:
            logger.warning(f"HTTP error: {e}")
            cw.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
            await cw.drain()

    except Exception as e:
        logger.debug(f"http_proxy_client error: {e}")
    finally:
        try: cw.close()
        except Exception: pass


# ── SOCKS5 proxy (chains to upstream) ────────────────────────────────────────

async def socks5_client(cr, cw):
    peer = cw.get_extra_info('peername', ('?', 0))[0]
    try:
        g = await cr.readexactly(2)
        if g[0] != 0x05:
            return
        await cr.readexactly(g[1])
        cw.write(b'\x05\x00')
        await cw.drain()

        req = await cr.readexactly(4)
        if req[1] != 0x01:
            cw.write(b'\x05\x07\x00\x01' + b'\x00'*6)
            return

        atype = req[3]
        if   atype == 0x01:
            host = '.'.join(str(b) for b in await cr.readexactly(4))
        elif atype == 0x03:
            n = (await cr.readexactly(1))[0]
            host = (await cr.readexactly(n)).decode()
        elif atype == 0x04:
            import ipaddress
            host = str(ipaddress.IPv6Address(await cr.readexactly(16)))
        else:
            return
        port = struct.unpack('!H', await cr.readexactly(2))[0]
        logger.info(f"SOCKS5 {peer} → {host}:{port}")

        ur, uw = await upstream_connect(host, port)
        cw.write(b'\x05\x00\x00\x01' + b'\x00'*6)
        await cw.drain()
        await asyncio.gather(pipe(cr, uw), pipe(ur, cw))

    except Exception as e:
        logger.warning(f"SOCKS5 error {peer}: {e}")
        try: cw.write(b'\x05\x01\x00\x01' + b'\x00'*6)
        except Exception: pass
    finally:
        try: cw.close()
        except Exception: pass


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    h_srv = await asyncio.start_server(http_proxy_client,  BIND, HTTP_PORT)
    s_srv = await asyncio.start_server(socks5_client,       BIND, SOCKS5_PORT)
    logger.info(f"HTTP  proxy : {BIND}:{HTTP_PORT}")
    logger.info(f"SOCKS5 proxy: {BIND}:{SOCKS5_PORT}")
    logger.info(f"Upstream    : socks5://{UPSTREAM[0]}:{UPSTREAM[1]}  (Swiss VPN)")
    async with h_srv, s_srv:
        await asyncio.gather(
            h_srv.serve_forever(),
            s_srv.serve_forever(),
        )

if __name__ == '__main__':
    asyncio.run(main())
```
---
### oracle/watchdog.sh
**Розмір:** 17,523 байт
```bash
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

PROXY_HOST="${PROXY_HOST:-100.100.74.9}"
PROXY_PORT="${PROXY_PORT:-9888}"
PROXY_TYPE="${PROXY_TYPE:-socks5}"
PROXY_URL="socks5://${PROXY_HOST}:${PROXY_PORT}"

WORKER_URL="${WORKER_URL:-https://watchdog-notifier.maxfraieho.workers.dev/}"
TELEGRAM_TOKEN="${TELEGRAM_TOKEN:-8508516661:AAEQBWvlBk3v62nd5ut3ei70TPFJTkV9LMs}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-6412868393}"
N8N_WEBHOOK_URL="${N8N_WEBHOOK_URL:-https://n8n.exodus.pp.ua/webhook/proxy-watchdog}"

CHECK_TIMEOUT="${CHECK_TIMEOUT:-10}"
MAX_RETRIES="${MAX_RETRIES:-3}"
RETRY_DELAY="${RETRY_DELAY:-5}"
TEST_URL="${TEST_URL:-http://checkip.amazonaws.com/}"
REMINDER_EVERY_ERRORS="${REMINDER_EVERY_ERRORS:-60}"

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

send_notification() {
    local message="$1"
    log "INFO" "Відправка сповіщення в Telegram..."

    local response
    response=$(curl -s -x "" -X POST \
        "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${message}" \
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
```
---
### services/local-watchdog/run
**Розмір:** 105 байт
```text
#!/data/data/com.termux/files/usr/bin/sh
exec /data/data/com.termux/files/home/bin/watchdog-loop.sh 2>&1
```
---
### services/local-watchdog/log/run
**Розмір:** 111 байт
```text
#!/data/data/com.termux/files/usr/bin/sh
exec svlogd -tt /data/data/com.termux/files/home/logs/local-watchdog/
```
---
### services/sshd/run
**Розмір:** 62 байт
```text
#!/data/data/com.termux/files/usr/bin/sh
exec sshd -D -e 2>&1
```
---
### services/ts-proxy/finish
**Розмір:** 170 байт
```text
#!/data/data/com.termux/files/usr/bin/sh
echo "$(date +%Y-%m-%dT%H:%M:%S) ts-proxy EXIT code=$1 signal=$2" \
  >> /data/data/com.termux/files/home/logs/ts-proxy-exit.log
```
---
### services/ts-proxy/run
**Розмір:** 341 байт
```text
#!/data/data/com.termux/files/usr/bin/sh
pkill -x microsocks 2>/dev/null || true
pkill -9 -x microsocks 2>/dev/null || true
# Wait up to 10s for port 9888 to be free
i=0
while [ $i -lt 10 ]; do
    bash -c "exec 3<>/dev/tcp/100.100.74.9/9888" 2>/dev/null || break
    sleep 1
    i=$((i+1))
done
exec microsocks -i 100.100.74.9 -p 9888 2>&1
```
---
### services/ts-proxy/log/run
**Розмір:** 109 байт
```text
#!/data/data/com.termux/files/usr/bin/sh
exec svlogd -tt /data/data/com.termux/files/usr/var/log/sv/ts-proxy
```
---
## Статистика
- **Оброблено файлів:** 26
- **З них прихованих:** 0
- **Пропущено сервісних:** 1
- **Загальний розмір:** 97,564 байт (95.3 KB)
- **Дата створення:** 2026-07-24 07:28:28
