# Proxy Infrastructure — Termux + Oracle (Dual-Persona v4.1)

Full Swiss geo-masking proxy stack supporting **Dual-Persona Multi-Channel Routing** (Husband & Wife) for survey completions without account linking or IP/fingerprint collisions:
- **Channel A (Husband / Persona A)**: HTTP `8888`, SOCKS5 `1080` -> Android Exit Node 1 (`100.100.74.9`, Tab S8)
- **Channel B (Wife / Persona B)**: HTTP `8889`, SOCKS5 `1081` -> Android Exit Node 2 (`100.87.198.99`, OnePlus / Pixel)
- **Telegram Bot**: `@vpn2votchdog_bot` with live Persona switching and status monitoring
- **Client Suite**: Windows 11 / Linux / macOS isolated Comet / Chromium browser launchers

---

## 📚 Швидкі посилання на документацію
- [📱 Пояснювальна записка для сина (Налаштування Android-пристроїв)](file:///home/vokov/projects/termux-proxy/ANDROID_DEVICE_SETUP_NOTE.md)
- [🛡️ Повний посібник проходження опитувань без банів (Dual Persona Guide)](file:///home/vokov/projects/termux-proxy/DUAL_PERSONA_SURVEY_GUIDE.md)
- [📲 MacroDroid Setup Guide](file:///home/vokov/projects/termux-proxy/MACRODROID_SETUP.md)
- [💻 Комплект клієнтських лаунчерів для ПК (laptop_client)](file:///home/vokov/projects/termux-proxy/laptop_client/README.md)

---

## Architecture (Dual-Persona v4.1)

```
[Windows 11 Ноутбук / Client]
  ├── 👨 Чоловік: Swiss_Survey_CHOLOVIK.bat ──→ Comet (Persona A) ──→ Oracle :1080 / :8888
  └── 👩 Дружина: Swiss_Survey_DRUZHYNA.bat ──→ Comet (Persona B) ──→ Oracle :1081 / :8889

[Oracle VPS (100.66.97.93) — smart_proxy.py Engine v4.1]
  ├── Channel A (:1080/:8888) ───[Tailscale]───► Android 1 (Tab S8: 100.100.74.9)   ───► Swisscom IP A 🇨🇭 (Bern)
  ├── Channel B (:1081/:8889) ───[Tailscale]───► Android 2 (OnePlus: 100.87.198.99) ───► Swiss Mobile/Res IP B 🇨🇭
  └── Telegram Bot (@vpn2votchdog_bot) — Меню "👥 Керування Персонами" + перемикач в 1 клік
```

### Tailscale network
| Host | Tailscale IP | Role |
|------|-------------|------|
| Oracle VPS | 100.66.97.93 | Dual-channel entry proxy + Telegram bot + watchdog |
| Tab S8 Ultra | 100.100.74.9 | Swiss Exit Node 1 (Persona A - Husband) |
| OnePlus / Pixel | 100.87.198.99 | Swiss Exit Node 2 (Persona B - Wife) |
| rpi4b | 100.80.16.33 | management / backup node |

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

## 💻 Laptop Client Configuration (Swiss Browser & Perplexity)

Client configuration files for Windows, macOS, and Linux laptops are located in `laptop_client/`:
- **`laptop_client/proxy.pac`**: PAC routing script directing ALL browser web traffic through Oracle (`100.66.97.93`) ➔ Swiss exit node (`100.100.74.9`), bypassing only local network IPs.
- **`laptop_client/README.md`**: Complete connection instructions for OS PAC settings and isolated Swiss Chrome browser (`--user-data-dir` + `--proxy-server="socks5://100.66.97.93:1080"`).

---

---

## 📲 MacroDroid Remote Wakeup (Non-Termux Remote Recovery)

Detailed setup guide for Android tablets and smartphones without Termux is documented in [MACRODROID_SETUP.md](file:///storage/emulated/0/Documents/termux-proxy/MACRODROID_SETUP.md):
- **Incoming Webhook**: `https://trigger.macrodroid.com/<DEVICE_ID>/wake_tailscale`
- **Telegram Bot Integration**: Adds inline keyboard button `⚡ Підняти Tailscale (Push)` to Telegram notifications.
- **FCM Push Recovery**: Automatically wakes up the Android device and launches Tailscale upon network failure.

---

## Ports Reference
| Port | Protocol | Host | Purpose |
|------|----------|------|---------|
| 8022 | SSH | Termux | SSH access |
| 9888 | SOCKS5 | Termux | Exit proxy (bound to Tailscale IP) |
| 9050 | SOCKS5 | Termux | Tor exit (anonymous) |
| 8888 | HTTP | Oracle | Entry proxy (Swiss header injection) |
| 1080 | SOCKS5 | Oracle | Entry proxy |


