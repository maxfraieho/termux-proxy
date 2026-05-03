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
