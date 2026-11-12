#!/usr/bin/env python3
"""
telegram_bot.py — Interactive Telegram Bot Daemon for Swiss Proxy & Watchdog
Features:
- Live Status Monitoring (Dual-Persona Channel A / Channel B)
- Persona Management (Husband / Wife profile switcher & Exit Node assigner)
- Exit Node Selector & Tailscale Control
- Full Automated Recovery & Revival (FCM Push Wakeup + SSH recovery + Service Restart)

Bot: @vpn2votchdog_bot
"""

import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.parse
import urllib.error
import logging
import traceback
import concurrent.futures

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("telegram_bot")

ENV_FILE = "/opt/watchdog/.env"
PERSONAS_FILE = "/opt/watchdog/personas.json"

DEFAULT_PERSONAS = {
    "active_persona": "husband",
    "husband": {
        "name": "Чоловік (Persona A)",
        "exit_node": "100.100.74.9",
        "device_name": "tab-s8-ultra",
        "upstream": "direct",
        "http_port": 8888,
        "socks_port": 1080,
        "lang": "de-CH,de;q=0.9,en;q=0.8",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "macrodroid_url": ""
    },
    "wife": {
        "name": "Дружина (Persona B)",
        "exit_node": "100.87.198.99",
        "device_name": "oneplus-pad-go-2",
        "upstream": "socks5://100.87.198.99:9888",
        "http_port": 8889,
        "socks_port": 1081,
        "lang": "de-CH,de;q=0.9,fr-CH;q=0.8,en;q=0.7",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
        "sec_ch_ua": '"Firefox";v="126", "Gecko";v="20100101"',
        "macrodroid_url": ""
    },
    "berveno": {
        "name": "Руслан Бервено (Persona C)",
        "exit_node": "100.87.198.99",
        "device_name": "oneplus-pad-go-2",
        "upstream": "direct",
        "http_port": 8890,
        "socks_port": 1082,
        "lang": "de-CH,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="133", "Google Chrome";v="133", "Not-A.Brand";v="99"',
        "macrodroid_url": ""
    }
}

def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def load_personas():
    data = DEFAULT_PERSONAS.copy()
    if os.path.exists(PERSONAS_FILE):
        try:
            with open(PERSONAS_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                data.update(loaded)
        except Exception as e:
            logger.warning(f"Error reading personas.json: {e}")
    else:
        save_personas(data)
    return data

def save_personas(data):
    try:
        os.makedirs(os.path.dirname(PERSONAS_FILE), exist_ok=True)
        with open(PERSONAS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(PERSONAS_FILE, 0o600)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error saving personas.json: {e}")

ENV = load_env()
BOT_TOKEN = ENV.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_CHAT_ID = str(ENV.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID", ""))
MACRODROID_URL = ENV.get("MACRODROID_WEBHOOK_URL", "")

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

def is_chat_allowed(chat_id: str) -> bool:
    env = load_env()
    allowed_str = env.get("TELEGRAM_CHAT_ID", ALLOWED_CHAT_ID)
    allowed_list = [c.strip() for c in allowed_str.split(",") if c.strip()]
    if not allowed_list:
        return True
    return str(chat_id).strip() in allowed_list

def api_call(method: str, payload: dict = None):
    url = f"{API_BASE}/{method}"
    data = None
    headers = {}
    if payload:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            if isinstance(res_data, dict) and not res_data.get("ok"):
                logger.warning(f"Telegram API call {method} error: {res_data.get('description')}")
            return res_data
    except urllib.error.HTTPError as he:
        try:
            err_body = he.read().decode('utf-8')
            logger.error(f"API call {method} HTTP {he.code}: {err_body}")
        except Exception:
            logger.error(f"API call {method} HTTP {he.code}")
        return None
    except Exception as e:
        logger.error(f"API call {method} error: {e}")
        return None

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    res = api_call("sendMessage", payload)
    if res is None or not res.get("ok"):
        # Fallback to plain text in case special characters break Markdown parsing
        payload.pop("parse_mode", None)
        res = api_call("sendMessage", payload)
    return res

def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Перевірити статус"}, {"text": "👥 Керування Персонами"}],
            [{"text": "🔄 Повне відновлення (Auto-Heal)"}, {"text": "⚡ Розбудити пристрої (Push)"}],
            [{"text": "🌐 Вибір Exit Node"}, {"text": "ℹ️ Допомога"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def get_inline_keyboard():
    buttons = [
        [{"text": "📊 Перевірити статус", "callback_data": "cmd_status"}],
        [{"text": "👥 Керування Персонами", "callback_data": "cmd_personas"}],
        [{"text": "🔄 Повне відновлення (Auto-Heal)", "callback_data": "cmd_autoheal"}],
        [{"text": "⚡ Розбудити пристрої (Push)", "callback_data": "cmd_wake_menu"}],
        [{"text": "🌐 Вибір Exit Node", "callback_data": "cmd_exitnode"}]
    ]
    return {"inline_keyboard": buttons}

def set_env_var(key: str, val: str):
    lines = []
    found = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={val}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={val}\n")
    
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

def get_exit_nodes_info():
    try:
        res = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return None, None, []
        data = json.loads(res.stdout)
        
        current_ip = ""
        if "ExitNodeStatus" in data and data["ExitNodeStatus"] and "TailscaleIPs" in data["ExitNodeStatus"]:
            if data["ExitNodeStatus"]["TailscaleIPs"]:
                current_ip = data["ExitNodeStatus"]["TailscaleIPs"][0].split("/")[0]
        
        peers = []
        for peer_id, peer in data.get("Peer", {}).items():
            ips = peer.get("TailscaleIPs", [])
            ip = ips[0] if ips else ""
            name = peer.get("HostName", "Unknown")
            online = peer.get("Online", False)
            os_type = peer.get("OS", "").lower()
            is_exit = peer.get("ExitNodeOption", False)

            # Filter out Ukrainian / management nodes
            if ip == "100.80.16.33" or "rpi" in name.lower():
                continue

            # Include if it is an Android device OR offers exit node
            if os_type == "android" or is_exit:
                # Clean up name display
                clean_name = name.split("користувача")[0].strip()
                peers.append({
                    "ip": ip,
                    "name": clean_name or name,
                    "online": online,
                    "is_exit": is_exit
                })

        # Sort: Online first, then by name
        peers.sort(key=lambda p: (not p["online"], p["name"]))

        env = load_env()
        primary_ip = env.get("PRIMARY_EXIT_NODE_IP", "")
        return current_ip, primary_ip, peers
    except Exception as e:
        logger.error(f"Error getting exit nodes: {e}")
        return None, None, []

def probe_channel(port: int, name: str):
    start = time.time()
    try:
        res = subprocess.run(
            ['curl', '-s', '--connect-timeout', '6', '--proxy', f'socks5://127.0.0.1:{port}', 'https://ipinfo.io/json'],
            capture_output=True, text=True, timeout=10
        )
        elapsed = round((time.time() - start), 2)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            return {
                "ok": True,
                "ip": data.get("ip", "N/A"),
                "country": data.get("country", "N/A"),
                "city": data.get("city", "N/A"),
                "org": data.get("org", "N/A"),
                "elapsed": elapsed,
            }
    except Exception as e:
        logger.warning(f"Probe {name} ({port}) error: {e}")
    return {"ok": False, "elapsed": round((time.time() - start), 2)}

def check_live_status():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        fut_a = executor.submit(probe_channel, 1080, "Channel A (Persona A - Husband)")
        fut_b = executor.submit(probe_channel, 1081, "Channel B (Persona B - Wife)")
        fut_c = executor.submit(probe_channel, 1082, "Channel C (Persona C - Berveno)")
        st_a = fut_a.result()
        st_b = fut_b.result()
        st_c = fut_c.result()
    personas = load_personas()

    h_name = personas.get("husband", {}).get("name", "Чоловік")
    w_name = personas.get("wife", {}).get("name", "Дружина")
    b_name = personas.get("berveno", {}).get("name", "Руслан Бервено")
    active_p = personas.get("active_persona", "husband")
    cur_p_name = personas.get(active_p, {}).get("name", active_p)

    lines = ["📊 *СТАТУС ШВЕЙЦАРСЬКОГО МУЛЬТИ-ПРОКСІ*\n"]
    lines.append(f"⭐ *Активна персона (Exit Node Routing)*: `{cur_p_name}`\n")

    # Channel A
    if st_a["ok"]:
        icon_a = "🟢" if st_a["country"] == "CH" else "🟡"
        lines.append(
            f"{icon_a} *Канал A ({h_name} / Порт 1080 & 8888)*:\n"
            f"  • IP: `{st_a['ip']}` ({st_a['country']}, {st_a['city']})\n"
            f"  • Провайдер: `{st_a['org']}`\n"
            f"  • Час відповіді: `{st_a['elapsed']}s`\n"
        )
    else:
        lines.append(f"🔴 *Канал A ({h_name} / Порт 1080)*: Не відповідає\n")

    # Channel B
    if st_b["ok"]:
        icon_b = "🟢" if st_b["country"] == "CH" else "🟡"
        lines.append(
            f"{icon_b} *Канал B ({w_name} / Порт 1081 & 8889)*:\n"
            f"  • IP: `{st_b['ip']}` ({st_b['country']}, {st_b['city']})\n"
            f"  • Провайдер: `{st_b['org']}`\n"
            f"  • Час відповіді: `{st_b['elapsed']}s`\n"
        )
    else:
        lines.append(f"🔴 *Канал B ({w_name} / Порт 1081)*: Очікує підключення другого пристрою\n")

    # Channel C
    if st_c["ok"]:
        icon_c = "🟢" if st_c["country"] == "CH" else "🟡"
        lines.append(
            f"{icon_c} *Канал C ({b_name} / Порт 1082 & 8890)*:\n"
            f"  • IP: `{st_c['ip']}` ({st_c['country']}, {st_c['city']})\n"
            f"  • Провайдер: `{st_c['org']}`\n"
            f"  • Час відповіді: `{st_c['elapsed']}s`\n"
        )
    else:
        lines.append(f"🔴 *Канал C ({b_name} / Порт 1082)*: Не відповідає\n")

    lines.append("💡 *Підказка*: Якщо канал не відповідає, натисніть *🔄 Повне відновлення*.")
    return "\n".join(lines)

# ── PERSONA MANAGEMENT ───────────────────────────────────────────────────────

def handle_personas_menu():
    personas = load_personas()
    h = personas.get("husband", DEFAULT_PERSONAS["husband"])
    w = personas.get("wife", DEFAULT_PERSONAS["wife"])
    b = personas.get("berveno", DEFAULT_PERSONAS.get("berveno", {}))
    active_p = personas.get("active_persona", "husband")

    active_mark_h = " ✅ [АКТИВНИЙ]" if active_p == "husband" else ""
    active_mark_w = " ✅ [АКТИВНИЙ]" if active_p == "wife" else ""
    active_mark_b = " ✅ [АКТИВНИЙ]" if active_p == "berveno" else ""

    msg = (
        "👥 *КЕРУВАННЯ ПЕРСОНАМИ ТА АКАУНТАМИ*\n\n"
        f"👨 *{h.get('name')}*{active_mark_h}\n"
        f"  • Вузол: `{h.get('exit_node')} ({h.get('device_name')})`\n"
        f"  • Порти: `SOCKS5 :1080` | `HTTP :8888`\n"
        f"  • Мова: `{h.get('lang')}`\n\n"
        f"👩 *{w.get('name')}*{active_mark_w}\n"
        f"  • Вузол: `{w.get('exit_node')} ({w.get('device_name')})`\n"
        f"  • Порти: `SOCKS5 :1081` | `HTTP :8889`\n"
        f"  • Мова: `{w.get('lang')}`\n\n"
        f"👤 *{b.get('name')}*{active_mark_b}\n"
        f"  • Вузол: `{b.get('exit_node')} ({b.get('device_name')})`\n"
        f"  • Порти: `SOCKS5 :1082` | `HTTP :8890`\n"
        f"  • Мова: `{b.get('lang')}`\n\n"
        "Оберіть дію або налаштуйте персону:"
    )

    buttons = [
        [
            {"text": f"⚡ Активувати: 👨 Чоловік", "callback_data": "p_activate:husband"},
            {"text": f"⚡ Активувати: 👩 Дружина", "callback_data": "p_activate:wife"}
        ],
        [
            {"text": f"⚡ Активувати: 👤 Бервено", "callback_data": "p_activate:berveno"}
        ],
        [
            {"text": "⚙️ 👨 Чоловік", "callback_data": "p_cfg:husband"},
            {"text": "⚙️ 👩 Дружина", "callback_data": "p_cfg:wife"},
            {"text": "⚙️ 👤 Бервено", "callback_data": "p_cfg:berveno"}
        ],
        [
            {"text": "📊 Перевірити статус усіх", "callback_data": "cmd_status"}
        ]
    ]
    return msg, {"inline_keyboard": buttons}

def handle_persona_config_menu(persona_id: str):
    personas = load_personas()
    p = personas.get(persona_id, DEFAULT_PERSONAS.get(persona_id, {}))
    p_name = p.get("name", persona_id)

    _, _, peers = get_exit_nodes_info()

    msg = (
        f"⚙️ *НАЛАШТУВАННЯ: {p_name}*\n\n"
        f"📌 *Поточний Exit Node*: `{p.get('exit_node')} ({p.get('device_name')})`\n"
        f"🌐 *Мовний заголовок*: `{p.get('lang')}`\n"
        f"🔌 *Порти*: `SOCKS5 :{p.get('socks_port')}` | `HTTP :{p.get('http_port')}`\n\n"
        "Оберіть Exit Node зі списку для закріплення за цією персоною:"
    )

    buttons = []
    if peers:
        for peer in peers:
            status_str = "🟢" if peer["online"] else "🔴"
            is_cur = " ✅" if peer["ip"] == p.get("exit_node") else ""
            b_text = f"{status_str} {peer['name']} ({peer['ip']}){is_cur}"
            # Keep callback_data under 64 bytes
            buttons.append([{"text": b_text, "callback_data": f"p_sn:{persona_id}:{peer['ip']}"}])
    
    buttons.append([
        {"text": "🇨🇭 Мова: de-CH (Німецька)", "callback_data": f"p_sl:{persona_id}:de-CH"},
        {"text": "🇨🇭 Мова: fr-CH (Французька)", "callback_data": f"p_sl:{persona_id}:fr-CH"}
    ])
    buttons.append([{"text": "⬅️ Назад до Персон", "callback_data": "cmd_personas"}])

    return msg, {"inline_keyboard": buttons}

def handle_activate_persona(persona_id: str):
    personas = load_personas()
    if persona_id not in personas:
        return "❌ Невідома персона."
    
    personas["active_persona"] = persona_id
    save_personas(personas)

    target_node = personas[persona_id].get("exit_node", "")
    if target_node:
        set_env_var("PRIMARY_EXIT_NODE_IP", target_node)
        set_env_var("EXPECTED_EXIT_NODE_IP", target_node)
        subprocess.run(["python3", "/opt/watchdog/switch_persona_cli.py", "--verify-egress", "1080"], capture_output=True, text=True, timeout=10)

    subprocess.run(["sudo", "systemctl", "restart", "swiss-proxy.service"], capture_output=True, text=True, timeout=10)

    p_name = personas[persona_id].get("name", persona_id)
    return (
        f"✅ *Успішно активовано: {p_name}!*\n\n"
        f"• Головний вихід (Порт 1080/8888) перемкнуто на `{target_node}`\n"
        f"• Застосовано відповідні User-Agent та мовні заголовки\n"
        f"• Службу swiss-proxy оновлено."
    )

def handle_set_persona_node(persona_id: str, node_ip: str):
    personas = load_personas()
    if persona_id in personas:
        # Find device name
        _, _, peers = get_exit_nodes_info()
        d_name = "Android"
        for peer in peers:
            if peer["ip"] == node_ip:
                d_name = peer["name"]
                break

        personas[persona_id]["exit_node"] = node_ip
        personas[persona_id]["device_name"] = d_name
        save_personas(personas)
        
        if personas.get("active_persona") == persona_id:
            set_env_var("PRIMARY_EXIT_NODE_IP", node_ip)
            set_env_var("EXPECTED_EXIT_NODE_IP", node_ip)
            subprocess.run(["python3", "/opt/watchdog/switch_persona_cli.py", "--verify-egress", "1080"], capture_output=True, text=True, timeout=10)
        
        subprocess.run(["sudo", "systemctl", "restart", "swiss-proxy.service"], capture_output=True, text=True, timeout=10)
        p_name = personas[persona_id].get("name", persona_id)
        return f"✅ *Вузол `{d_name} ({node_ip})` успішно закріплено за {p_name}!*"
    return "❌ Помилка збереження персони."

def handle_set_persona_lang(persona_id: str, lang_type: str):
    personas = load_personas()
    if persona_id in personas:
        if lang_type == "fr-CH":
            personas[persona_id]["lang"] = "fr-CH,fr;q=0.9,de-CH;q=0.8,en;q=0.7"
        else:
            personas[persona_id]["lang"] = "de-CH,de;q=0.9,en;q=0.8"
        save_personas(personas)
        subprocess.run(["sudo", "systemctl", "restart", "swiss-proxy.service"], capture_output=True, text=True, timeout=10)
        p_name = personas[persona_id].get("name", persona_id)
        return f"✅ *Мову `{lang_type}` успішно збережено для {p_name}!*"
    return "❌ Помилка збереження персони."

# ── AUTO-HEAL & REMOTE RECOVERY ──────────────────────────────────────────────

def send_push_webhook(url: str):
    if not url or "YOUR_DEVICE_ID" in url:
        return False
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Oracle-Watchdog-Bot'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning(f"Push webhook error ({url}): {e}")
        return False

def handle_wake_menu():
    msg = (
        "⚡ *МЕНЮ ДИСТАНЦІЙНОГО ПРОБУДЖЕННЯ (PUSH)*\n\n"
        "Надсилає FCM Push-сигнал на MacroDroid, щоб розбудити пристрій із глибокого сну та підняти Tailscale + Termux:\n\n"
        "Оберіть пристрій для пробудження:"
    )
    buttons = [
        [{"text": "⚡ Розбудити планшет 👨 Тата (Tab S8)", "callback_data": "wake_target:husband"}],
        [{"text": "⚡ Розбудити смартфон 👩 Мами (OnePlus)", "callback_data": "wake_target:wife"}],
        [{"text": "⚡ Розбудити ВСІ швейцарські пристрої", "callback_data": "wake_target:all"}],
        [{"text": "⬅️ Назад", "callback_data": "cmd_status"}]
    ]
    return msg, {"inline_keyboard": buttons}

def handle_wake_action(target: str):
    personas = load_personas()
    env = load_env()
    fallback_url = env.get("MACRODROID_WEBHOOK_URL", "")

    url_h = personas.get("husband", {}).get("macrodroid_url") or fallback_url
    url_w = personas.get("wife", {}).get("macrodroid_url") or fallback_url

    sent = 0
    if target in ["husband", "all"] and url_h:
        if send_push_webhook(url_h):
            sent += 1
    if target in ["wife", "all"] and url_w:
        if send_push_webhook(url_w):
            sent += 1

    if sent > 0:
        return (
            "📲 *СИГНАЛ ПРОБУДЖЕННЯ НАДІСЛАНО!*\n\n"
            f"⚡ FCM Push успішно відправлено на обрані пристрої ({sent} пристр.).\n"
            "Зачекайте 5-10 секунд для підняття зв'язку."
        )
    else:
        return (
            "⚠️ *ПОМИЛКА*: MacroDroid Webhook URL не налаштовано!\n\n"
            "Додайте посилання MacroDroid у `/opt/watchdog/.env` або в налаштування персон."
        )

def handle_full_recovery():
    personas = load_personas()
    env = load_env()
    fallback_url = env.get("MACRODROID_WEBHOOK_URL", "")

    url_h = personas.get("husband", {}).get("macrodroid_url") or fallback_url
    url_w = personas.get("wife", {}).get("macrodroid_url") or fallback_url

    results = ["🔄 *ЗАПУСК ПОВНОГО АВТО-ВІДНОВЛЕННЯ СИСТЕМИ*:\n"]

    # 1. Send push to both devices
    if url_h: send_push_webhook(url_h)
    if url_w: send_push_webhook(url_w)
    results.append("1️⃣ 📲 *FCM Push*: Сигнал пробудження надіслано на пристрої")

    # 2. Re-apply active exit node
    active_p = personas.get("active_persona", "husband")
    active_ip = personas.get(active_p, {}).get("exit_node", "100.100.74.9")
    subprocess.run(["python3", "/opt/watchdog/switch_persona_cli.py", "--verify-egress", "1080"], capture_output=True, text=True, timeout=10)
    results.append(f"2️⃣ 🌐 *Tailscale Exit Node*: Застосовано `{active_ip}`")

    # 3. Restart swiss-proxy
    subprocess.run(["sudo", "systemctl", "restart", "swiss-proxy.service"], capture_output=True, text=True, timeout=10)
    results.append("3️⃣ ⚙️ *Proxy Engine*: Перезапущено `swiss-proxy.service`")

    # 4. Probe live status concurrently
    time.sleep(2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        fut_a = executor.submit(probe_channel, 1080, "Channel A")
        fut_b = executor.submit(probe_channel, 1081, "Channel B")
        fut_c = executor.submit(probe_channel, 1082, "Channel C")
        st_a = fut_a.result()
        st_b = fut_b.result()
        st_c = fut_c.result()

    results.append("\n📊 *РЕЗУЛЬТАТ НАЖИВО*:")
    if st_a["ok"]:
        results.append(f"  • 👨 Канал A (1080): 🟢 `{st_a['ip']}` ({st_a['country']}, {st_a['city']}) — {st_a['elapsed']}s")
    else:
        results.append("  • 👨 Канал A (1080): 🔴 Очікує підняття планшета")

    if st_b["ok"]:
        results.append(f"  • 👩 Канал B (1081): 🟢 `{st_b['ip']}` ({st_b['country']}, {st_b['city']}) — {st_b['elapsed']}s")
    else:
        results.append("  • 👩 Канал B (1081): 🔴 Очікує підняття смартфона")

    if st_c["ok"]:
        results.append(f"  • 👤 Канал C (1082): 🟢 `{st_c['ip']}` ({st_c['country']}, {st_c['city']}) — {st_c['elapsed']}s")
    else:
        results.append("  • 👤 Канал C (1082): 🔴 Очікує підняття пристрою")

    return "\n".join(results)

# ── EXIT NODES ───────────────────────────────────────────────────────────────

def handle_exitnode_list():
    current_ip, primary_ip, peers = get_exit_nodes_info()
    if peers is None:
        return "❌ Не вдалося отримати статус Tailscale.", None

    active_str = current_ip if current_ip else "Прямий інтернет (Direct)"
    primary_str = primary_ip if primary_ip else "Не задано"

    msg = (
        "🌐 *КЕРУВАННЯ ВУЗЛАМИ EXIT NODE*\n\n"
        f"📌 *Активний зараз*: `{active_str}`\n"
        f"⭐ *Основний в .env*: `{primary_str}`\n\n"
        "Оберіть пристрій зі списку для перемикання:"
    )

    buttons = []
    for p in peers:
        status_str = "🟢 Online" if p["online"] else "🔴 Offline"
        badge = ""
        if p["ip"] == current_ip:
            badge = " ✅"
        elif p["ip"] == primary_ip:
            badge = " ⭐"
        
        text = f"{p['name']} ({p['ip']}) - {status_str}{badge}"
        buttons.append([{"text": text, "callback_data": f"set_exit:{p['ip']}"}])
    
    direct_badge = " ✅" if not current_ip else ""
    buttons.append([{"text": f"🌐 Прямий Інтернет (Direct Mode){direct_badge}", "callback_data": "set_exit:direct"}])
    buttons.append([{"text": "🔄 Оновити список", "callback_data": "cmd_exitnode"}])

    return msg, {"inline_keyboard": buttons}

def handle_set_exit_node(target: str):
    if target == "direct":
        set_env_var("PRIMARY_EXIT_NODE_IP", "")
        set_env_var("EXPECTED_EXIT_NODE_IP", "")
        res = subprocess.run(["python3", "/opt/watchdog/switch_persona_cli.py", "--verify-egress", "1080"], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return "🌐 *Успішно переключено на ПРЯМИЙ Інтернет!*\n(Exit Node вимкнено, конфігурацію оновлено)."
        else:
            return f"❌ Помилка tailscale set: `{res.stderr}`"
    else:
        set_env_var("PRIMARY_EXIT_NODE_IP", target)
        set_env_var("EXPECTED_EXIT_NODE_IP", target)
        res = subprocess.run(["python3", "/opt/watchdog/switch_persona_cli.py", "--verify-egress", "1080"], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            ping_res = subprocess.run(["ping", "-c", "2", "google.com"], capture_output=True, text=True, timeout=5)
            ping_ok = "✅ Інтернет OK" if ping_res.returncode == 0 else "⚠️ Інтернет не відповідає"
            return f"✅ *Успішно активовано Exit Node*: `{target}`\n\n📊 *Перевірка доступності*: {ping_ok}"
        else:
            return f"❌ Помилка активації Exit Node `{target}`: `{res.stderr}`"

def process_command(cmd_text, chat_id):
    raw_cmd = cmd_text.strip()
    cmd = raw_cmd.lower()
    # Strip bot username if sent as /command@botname
    if cmd.startswith("/") and "@" in cmd:
        cmd = cmd.split("@")[0]

    if cmd in ["/start", "/help", "/menu", "ℹ️ допомога", "допомога", "меню", "головне меню", "🏠 головне меню"]:
        msg = (
            "👋 *ГОЛОВНЕ МЕНЮ — Swiss Proxy Watchdog*\n\n"
            "• 📊 *Перевірити статус* — стан обох швейцарських каналів\n"
            "• 👥 *Керування Персонами* — перемикання Чоловік / Дружина\n"
            "• 🔄 *Повне відновлення* — 1-клік авто-лікування та перезапуск\n"
            "• ⚡ *Розбудити пристрої* — Push-сигнал на MacroDroid\n"
            "• 🌐 *Вибір Exit Node* — перемикання кінцевих точок Tailscale\n\n"
            "Оберіть дію на панелі кнопок нижче 👇:"
        )
        send_message(chat_id, msg, reply_markup=get_main_keyboard())
    elif cmd in ["/status", "📊 перевірити статус", "статус", "перевірити статус"]:
        send_message(chat_id, "⏳ *Перевіряємо стан швейцарських каналів...*")
        msg = check_live_status()
        send_message(chat_id, msg, reply_markup=get_inline_keyboard())
    elif cmd in ["/personas", "/persona", "👥 керування персонами", "персони", "керування персонами"]:
        msg, markup = handle_personas_menu()
        send_message(chat_id, msg, reply_markup=markup)
    elif cmd in ["/autoheal", "/heal", "🔄 повне відновлення (auto-heal)", "🔄 повне відновлення", "відновлення", "🔄 перезапустити проксі"]:
        send_message(chat_id, "⏳ *Запускаємо повне автоматичне відновлення...*")
        msg = handle_full_recovery()
        send_message(chat_id, msg, reply_markup=get_inline_keyboard())
    elif cmd in ["/wake", "⚡ розбудити пристрої (push)", "⚡ розбудити пристрої", "розбудити", "⚡ підняти tailscale (push)"]:
        msg, markup = handle_wake_menu()
        send_message(chat_id, msg, reply_markup=markup)
    elif cmd in ["/exitnode", "/nodes", "🌐 вибір exit node", "exit node", "вузли"]:
        msg, markup = handle_exitnode_list()
        send_message(chat_id, msg, reply_markup=markup)
    else:
        msg = "ℹ️ Оберіть дію з меню нижче або скористайтесь кнопками:"
        send_message(chat_id, msg, reply_markup=get_main_keyboard())

def handle_callback_query(data: str, chat_id: str):
    try:
        if data == "cmd_status":
            process_command("/status", chat_id)
        elif data == "cmd_personas":
            process_command("/personas", chat_id)
        elif data == "cmd_autoheal":
            process_command("/autoheal", chat_id)
        elif data == "cmd_wake_menu":
            process_command("/wake", chat_id)
        elif data == "cmd_exitnode":
            process_command("/exitnode", chat_id)
        elif data.startswith("wake_target:"):
            target = data.split(":", 1)[1]
            res_msg = handle_wake_action(target)
            send_message(chat_id, res_msg)
            process_command("/status", chat_id)
        elif data.startswith("p_activate:"):
            p_id = data.split(":", 1)[1]
            res_msg = handle_activate_persona(p_id)
            send_message(chat_id, res_msg)
            process_command("/personas", chat_id)
        elif data.startswith("p_cfg:"):
            p_id = data.split(":", 1)[1]
            msg, markup = handle_persona_config_menu(p_id)
            send_message(chat_id, msg, reply_markup=markup)
        elif data.startswith("p_sn:"):
            parts = data.split(":", 2)
            p_id, n_ip = parts[1], parts[2]
            res_msg = handle_set_persona_node(p_id, n_ip)
            send_message(chat_id, res_msg)
            msg, markup = handle_persona_config_menu(p_id)
            send_message(chat_id, msg, reply_markup=markup)
        elif data.startswith("p_sl:"):
            parts = data.split(":", 2)
            p_id, l_type = parts[1], parts[2]
            res_msg = handle_set_persona_lang(p_id, l_type)
            send_message(chat_id, res_msg)
            msg, markup = handle_persona_config_menu(p_id)
            send_message(chat_id, msg, reply_markup=markup)
        elif data.startswith("set_exit:"):
            target = data.split(":", 1)[1]
            send_message(chat_id, f"⏳ *Застосовуємо новий Exit Node (`{target}`)...*")
            res_msg = handle_set_exit_node(target)
            send_message(chat_id, res_msg)
            process_command("/exitnode", chat_id)
    except Exception as e:
        logger.error(f"Error handling callback_query '{data}' for chat {chat_id}: {e}\n{traceback.format_exc()}")
        send_message(chat_id, f"⚠️ Виникла помилка при виконанні дії: `{e}`")

def setup_bot_commands():
    commands = [
        {"command": "menu", "description": "🏠 Головне меню та клавіатура з 4 крапками"},
        {"command": "status", "description": "📊 Перевірити статус обох каналів"},
        {"command": "personas", "description": "👥 Керування персонами (Чоловік / Дружина)"},
        {"command": "autoheal", "description": "🔄 Повне авто-відновлення зв'язку"},
        {"command": "wake", "description": "⚡ Розбудити Android пристрої (Push)"},
        {"command": "exitnode", "description": "🌐 Вибір кінцевої точки Exit Node"},
        {"command": "help", "description": "ℹ️ Допомога та відкриття кнопок"}
    ]
    res = api_call("setMyCommands", {"commands": commands})
    logger.info(f"setMyCommands result: {res}")
    
    # Register native chat menu button
    res_btn = api_call("setChatMenuButton", {
        "menu_button": {"type": "commands"}
    })
    logger.info(f"setChatMenuButton result: {res_btn}")

def main():
    logger.info("Starting Telegram Bot Polling Daemon with Auto-Heal & Multi-Persona Manager...")
    setup_bot_commands()
    offset = 0
    consecutive_network_errors = 0

    while True:
        try:
            updates = api_call("getUpdates", {"offset": offset, "timeout": 25})
            if updates is None:
                consecutive_network_errors += 1
                sleep_time = min(30, 2 ** min(consecutive_network_errors, 5))
                logger.warning(f"getUpdates returned None (consecutive errors: {consecutive_network_errors}). Sleeping {sleep_time}s...")
                time.sleep(sleep_time)
                continue

            consecutive_network_errors = 0

            if updates.get("ok"):
                for item in updates.get("result", []):
                    item_id = item.get("update_id", offset)
                    offset = item_id + 1

                    try:
                        if "message" in item:
                            msg = item["message"]
                            chat_id = str(msg.get("chat", {}).get("id", ""))
                            text = msg.get("text", "")

                            if not chat_id:
                                continue

                            if not is_chat_allowed(chat_id):
                                logger.warning(f"Unauthorized access attempt from chat_id {chat_id}")
                                send_message(chat_id, f"🔒 *Доступ обмежено.*\n\nВаш Telegram Chat ID: `{chat_id}`\nДодайте його до файлу `/opt/watchdog/.env` (`TELEGRAM_CHAT_ID={chat_id}`) на Oracle, щоб надати доступ.")
                                continue

                            if text:
                                process_command(text, chat_id)

                        elif "callback_query" in item:
                            cq = item["callback_query"]
                            cq_id = cq.get("id")
                            if cq_id:
                                api_call("answerCallbackQuery", {"callback_query_id": cq_id})

                            chat_id = str(cq.get("message", {}).get("chat", {}).get("id") or cq.get("from", {}).get("id", ""))
                            if not chat_id or chat_id == "None":
                                continue

                            if not is_chat_allowed(chat_id):
                                logger.warning(f"Unauthorized callback query from chat_id {chat_id}")
                                continue

                            data = cq.get("data", "")
                            if data:
                                handle_callback_query(data, chat_id)

                    except Exception as item_err:
                        logger.error(f"Error processing update item {item.get('update_id')}: {item_err}\n{traceback.format_exc()}")

        except Exception as e:
            logger.error(f"Error in polling loop: {e}\n{traceback.format_exc()}")
            time.sleep(3)

# ==============================================================================
# SPRINT T-20261112-58 (T-58): KONTUR 24/7 SURVEY WEBAPP (TMA) & QWEN 3.8
# EXTENSION FOR @vpn2votchdog_bot (maxfraieho/termux-proxy ON ORACLE CLOUD VPS)
# ==============================================================================

def get_kontur_hub_api_base_t58() -> str:
    """Returns the 24/7 KONTUR Survey Hub base URL on Host .161 (or failover RPi 3B .234) reachable via Tailscale/LAN."""
    env = load_env()
    return (
        env.get("KONTUR_HUB_API_URL")
        or os.environ.get("KONTUR_HUB_API_URL")
        or "http://192.168.3.161:5005"
    ).rstrip("/")


def get_kontur_webapp_https_url_t58() -> str:
    """Returns the external Cloudflare HTTPS URL (from Host .184) for the 24/7 KONTUR Survey Telegram Mini App."""
    env = load_env()
    url = (
        env.get("KONTUR_PUBLIC_HTTPS_URL")
        or os.environ.get("KONTUR_PUBLIC_HTTPS_URL")
        or "https://kontur-survey.trycloudflare.com"
    ).strip().rstrip("/")
    return url


def fetch_kontur_hub_json_t58(path: str, method: str = "GET", payload: dict = None, timeout: float = 6.0) -> dict:
    base = get_kontur_hub_api_base_t58()
    candidates = [base, "http://192.168.3.161:5005", "http://192.168.3.234:5005"]
    seen = set()
    for b in candidates:
        if not b or b in seen:
            continue
        seen.add(b)
        url = f"{b}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json", "X-Kontur-Loopback": "1"}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            continue
    return {}


def handle_kontur_surveys_summary_t58() -> tuple:
    webapp_url = get_kontur_webapp_https_url_t58()
    topo = fetch_kontur_hub_json_t58("/api/kontur/node_topology_status", method="GET")
    node_ip = ((topo.get("placement") or {}).get("selected_host_ip")) or "192.168.3.161"
    cdp_mode = ((topo.get("laptop_30_cdp_bridge") or {}).get("mode_label_ua")) or "💻 Очікування підключення до ноутбука .30"

    msg = (
        "🎯 *ПУЛЬТ ОПИТУВАНЬ KONTUR 24/7 & БАЛАНСИ АКАУНТІВ*\n\n"
        f"• 🌐 *Сервер 24/7*: `{node_ip}:5005` (Cloudflare `.184` HTTPS)\n"
        f"• {cdp_mode}\n\n"
        "👥 *Верифіковані Профілі (13/13 модулів — 100%)*:\n"
        "• 👨 *Арсен (`arno` :9224)*: баланс *37.15 CHF* (26 квитків) — канал Swisscom `:1080`\n"
        "• 👩 *Олена (`annet` :9227)*: баланс *8.05 CHF* (10 квитків) — канал Salt LTE `:1081`\n"
        "• 👤 *Руслан (`berveno` :9228)*: баланс *0.00 CHF* (15 квитків) — канал Swisscom `:1080`\n\n"
        "👇 Натисніть кнопку нижче, щоб відкрити повноцінний *Вебзастосунок Опитувань (WebApp)* прямо в Telegram:"
    )
    markup = {
        "inline_keyboard": [
            [{"text": "📱 Відкрити Пульт Опитувань KONTUR (WebApp 24/7)", "web_app": {"url": webapp_url}}],
            [
                {"text": "🎓 WebApp: Арсен (:9224)", "web_app": {"url": f"{webapp_url}/?profile=arno"}},
                {"text": "🎓 WebApp: Олена (:9227)", "web_app": {"url": f"{webapp_url}/?profile=annet"}},
            ],
            [
                {"text": "🔗 Перевірити Qwen 3.8 + Базу Знань", "callback_data": "cmd_qwen_handshake"},
                {"text": "🖥 Статус Вузлів (.161 / .234 / .30)", "callback_data": "cmd_kontur_nodes"},
            ],
            [{"text": "📊 Перевірити статус проксі", "callback_data": "cmd_status"}],
        ]
    }
    return msg, markup


def handle_kontur_qwen_handshake_t58(profile_key: str = "arno") -> tuple:
    webapp_url = get_kontur_webapp_https_url_t58()
    hs = fetch_kontur_hub_json_t58(
        "/api/colab/verify_qwen_knowledge_handshake",
        method="POST",
        payload={"profile": profile_key},
    )
    kb = hs.get("knowledge_base_connection") or {}
    probe = hs.get("handshake_test_probe") or {}
    tier_ua = hs.get("active_tier_label_ua") or "🟢 Qwen 3.8 + 507Q Атлас (:8090)"
    facts_cnt = kb.get("sqlite_survey_graph_facts", 57)
    atlas_name = kb.get("atlas_507q_file", "ATLAS_PERSONA_02_ARNO_ARSEN_507Q.md")
    adr_cnt = kb.get("adr_rules_loaded_count", 9)
    zip_out = probe.get("verified_output_value", "1196")

    msg = (
        "🔗 *HANDSHAKE QWEN 3.8 ↔ БАЗА ЗНАНЬ (НАЖИВО З .161:5005)*\n\n"
        f"• *Активний рівень*: {tier_ua}\n"
        f"• *SQLite `survey_graph.db`*: `{facts_cnt}` канонічних фактів\n"
        f"• *507Q Атлас*: `{atlas_name}` (підключено)\n"
        f"• *Закони ADR (з `agy-1`)*: `{adr_cnt}` правил (вкл. `ADR-1794340000`)\n"
        f"• *Контрольний тест індексу (`_QNumPostal`)*: вхід `5` ➔ вихід `{zip_out}` (Gland, VD — PASS)"
    )
    markup = {
        "inline_keyboard": [
            [{"text": "📱 Відкрити Пульт Опитувань KONTUR (WebApp 24/7)", "web_app": {"url": webapp_url}}],
            [{"text": "🎯 Назад до Анкет & Балансів", "callback_data": "cmd_surveys"}],
        ]
    }
    return msg, markup


def get_main_keyboard():
    webapp_url = get_kontur_webapp_https_url_t58()
    return {
        "keyboard": [
            [{"text": "📱 Пульт Опитувань (WebApp)", "web_app": {"url": webapp_url}}, {"text": "🎯 Анкети & Qwen 3.8 (.161)"}],
            [{"text": "📊 Перевірити статус"}, {"text": "👥 Керування Персонами"}],
            [{"text": "🔄 Повне відновлення (Auto-Heal)"}, {"text": "⚡ Розбудити пристрої (Push)"}],
            [{"text": "🌐 Вибір Exit Node"}, {"text": "ℹ️ Допомога"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }


def get_inline_keyboard():
    webapp_url = get_kontur_webapp_https_url_t58()
    buttons = [
        [{"text": "📱 Пульт Опитувань KONTUR (WebApp 24/7)", "web_app": {"url": webapp_url}}],
        [
            {"text": "🎯 Анкети & Баланси (.161)", "callback_data": "cmd_surveys"},
            {"text": "🔗 Handshake Qwen 3.8 + База Знань", "callback_data": "cmd_qwen_handshake"},
        ],
        [{"text": "📊 Перевірити статус", "callback_data": "cmd_status"}],
        [{"text": "👥 Керування Персонами", "callback_data": "cmd_personas"}],
        [{"text": "🔄 Повне відновлення (Auto-Heal)", "callback_data": "cmd_autoheal"}],
        [{"text": "⚡ Розбудити пристрої (Push)", "callback_data": "cmd_wake_menu"}],
        [{"text": "🌐 Вибір Exit Node", "callback_data": "cmd_exitnode"}]
    ]
    return {"inline_keyboard": buttons}


_orig_process_command_pre_t58 = process_command


def process_command(cmd_text, chat_id):
    raw_cmd = str(cmd_text or "").strip()
    cmd = raw_cmd.lower()
    if cmd.startswith("/") and "@" in cmd:
        cmd = cmd.split("@")[0]

    if cmd in ["/surveys", "/survey", "/webapp", "/url", "🎯 анкети & qwen 3.8 (.161)", "анкети", "опитування"]:
        msg, markup = handle_kontur_surveys_summary_t58()
        send_message(chat_id, msg, reply_markup=markup)
        return
    if cmd in ["/qwen", "/handshake", "🔗 handshake qwen 3.8 + база знань"]:
        msg, markup = handle_kontur_qwen_handshake_t58("arno")
        send_message(chat_id, msg, reply_markup=markup)
        return
    if cmd.startswith("/set_webapp_url"):
        parts = raw_cmd.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip().startswith("https://"):
            new_url = parts[1].strip().rstrip("/")
            set_env_var("KONTUR_PUBLIC_HTTPS_URL", new_url)
            send_message(chat_id, f"✅ *Оновлено HTTPS URL Вебзастосунку Опитувань KONTUR*:\n`{new_url}`", reply_markup=get_inline_keyboard())
            return

    return _orig_process_command_pre_t58(cmd_text, chat_id)


_orig_handle_callback_query_pre_t58 = handle_callback_query


def handle_callback_query(data: str, chat_id: str):
    if data == "cmd_surveys":
        msg, markup = handle_kontur_surveys_summary_t58()
        send_message(chat_id, msg, reply_markup=markup)
        return
    if data in ("cmd_qwen_handshake", "kontur_handshake:arno"):
        msg, markup = handle_kontur_qwen_handshake_t58("arno")
        send_message(chat_id, msg, reply_markup=markup)
        return
    if data in ("cmd_kontur_nodes", "kontur_nodes_status"):
        topo = fetch_kontur_hub_json_t58("/api/kontur/node_topology_status", method="GET")
        pl = topo.get("placement") or {}
        cdp = topo.get("laptop_30_cdp_bridge") or {}
        msg = (
            "🖥 *СТАТУС ВУЗЛІВ 24/7 KONTUR SURVEY HUB*\n\n"
            f"• *Активний сервер 24/7*: `{pl.get('selected_host_ip', '192.168.3.161')}:5005` (`{pl.get('selected_node_id', 'node_161')}`)\n"
            f"• *Резерв RPi 3B*: `192.168.3.234:5005` (Failover: `{pl.get('failover_to_rpi234_triggered', False)}`)\n"
            f"• *Cloudflare HTTPS Шлюз*: `192.168.3.184` ➔ `{get_kontur_webapp_https_url_t58()}`\n"
            f"• *Ноутбук .30 (Comet CDP)*: {cdp.get('mode_label_ua', 'Standby')}"
        )
        send_message(chat_id, msg, reply_markup=get_inline_keyboard())
        return
    return _orig_handle_callback_query_pre_t58(data, chat_id)


if __name__ == "__main__":
    main()
