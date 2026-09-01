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
import logging

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
    except Exception as e:
        logger.error(f"Error saving personas.json: {e}")

ENV = load_env()
BOT_TOKEN = ENV.get("TELEGRAM_TOKEN", "8508516661:AAEQBWvlBk3v62nd5ut3ei70TPFJTkV9LMs")
ALLOWED_CHAT_ID = str(ENV.get("TELEGRAM_CHAT_ID", "6412868393"))
MACRODROID_URL = ENV.get("MACRODROID_WEBHOOK_URL", "")

API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

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
            return json.loads(resp.read().decode('utf-8'))
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
    return api_call("sendMessage", payload)

def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Перевірити статус"}, {"text": "👥 Керування Персонами"}],
            [{"text": "🔄 Повне відновлення (Auto-Heal)"}, {"text": "⚡ Розбудити пристрої (Push)"}],
            [{"text": "🌐 Вибір Exit Node"}, {"text": "ℹ️ Допомога"}]
        ],
        "resize_keyboard": True,
        "persistent": True
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
            if peer.get("ExitNodeOption"):
                ips = peer.get("TailscaleIPs", [])
                ip = ips[0] if ips else ""
                name = peer.get("HostName", "Unknown")
                online = peer.get("Online", False)
                # Exclude non-Swiss nodes
                if ip == "100.80.16.33" or "rpi" in name.lower():
                    continue
                peers.append({"ip": ip, "name": name, "online": online})

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
    st_a = probe_channel(1080, "Channel A (Persona A - Husband)")
    st_b = probe_channel(1081, "Channel B (Persona B - Wife)")
    personas = load_personas()

    h_name = personas.get("husband", {}).get("name", "Чоловік")
    w_name = personas.get("wife", {}).get("name", "Дружина")
    active_p = personas.get("active_persona", "husband")

    lines = ["📊 *СТАТУС ПОДВІЙНОГО ПРОКСІ (DUAL PERSONA)*\n"]
    lines.append(f"⭐ *Активна персона для порту 1080*: `{h_name if active_p == 'husband' else w_name}`\n")

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

    lines.append("💡 *Підказка*: Якщо канал не відповідає, натисніть *🔄 Повне відновлення*.")
    return "\n".join(lines)

# ── PERSONA MANAGEMENT ───────────────────────────────────────────────────────

def handle_personas_menu():
    personas = load_personas()
    h = personas.get("husband", DEFAULT_PERSONAS["husband"])
    w = personas.get("wife", DEFAULT_PERSONAS["wife"])
    active_p = personas.get("active_persona", "husband")

    active_mark_h = " ✅ [АКТИВНИЙ]" if active_p == "husband" else ""
    active_mark_w = " ✅ [АКТИВНИЙ]" if active_p == "wife" else ""

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
        "Оберіть дію або налаштуйте персону:"
    )

    buttons = [
        [
            {"text": f"⚡ Активувати: 👨 Чоловік", "callback_data": "p_activate:husband"},
            {"text": f"⚡ Активувати: 👩 Дружина", "callback_data": "p_activate:wife"}
        ],
        [
            {"text": "⚙️ Налаштувати 👨 Чоловіка", "callback_data": "p_cfg:husband"},
            {"text": "⚙️ Налаштувати 👩 Дружину", "callback_data": "p_cfg:wife"}
        ],
        [
            {"text": "📊 Перевірити статус обох", "callback_data": "cmd_status"}
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
            buttons.append([{"text": b_text, "callback_data": f"p_setnode:{persona_id}:{peer['ip']}:{peer['name']}"}])
    
    buttons.append([
        {"text": "🇨🇭 Мова: de-CH (Німецька)", "callback_data": f"p_setlang:{persona_id}:de-CH"},
        {"text": "🇨🇭 Мова: fr-CH (Французька)", "callback_data": f"p_setlang:{persona_id}:fr-CH"}
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
        subprocess.run(["sudo", "tailscale", "set", f"--exit-node={target_node}", "--exit-node-allow-lan-access=true"], capture_output=True, text=True, timeout=10)

    subprocess.run(["sudo", "systemctl", "restart", "swiss-proxy.service"], capture_output=True, text=True, timeout=10)

    p_name = personas[persona_id].get("name", persona_id)
    return (
        f"✅ *Успішно активовано: {p_name}!*\n\n"
        f"• Головний вихід (Порт 1080/8888) перемкнуто на `{target_node}`\n"
        f"• Застосовано відповідні User-Agent та мовні заголовки\n"
        f"• Службу swiss-proxy оновлено."
    )

def handle_set_persona_node(persona_id: str, node_ip: str, node_name: str):
    personas = load_personas()
    if persona_id in personas:
        personas[persona_id]["exit_node"] = node_ip
        personas[persona_id]["device_name"] = node_name
        save_personas(personas)
        
        if personas.get("active_persona") == persona_id:
            set_env_var("PRIMARY_EXIT_NODE_IP", node_ip)
            set_env_var("EXPECTED_EXIT_NODE_IP", node_ip)
            subprocess.run(["sudo", "tailscale", "set", f"--exit-node={node_ip}", "--exit-node-allow-lan-access=true"], capture_output=True, text=True, timeout=10)
        
        subprocess.run(["sudo", "systemctl", "restart", "swiss-proxy.service"], capture_output=True, text=True, timeout=10)
        p_name = personas[persona_id].get("name", persona_id)
        return f"✅ *Вузол `{node_name} ({node_ip})` успішно закріплено за {p_name}!*"
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
    subprocess.run(["sudo", "tailscale", "set", f"--exit-node={active_ip}", "--exit-node-allow-lan-access=true"], capture_output=True, text=True, timeout=10)
    results.append(f"2️⃣ 🌐 *Tailscale Exit Node*: Застосовано `{active_ip}`")

    # 3. Restart swiss-proxy
    subprocess.run(["sudo", "systemctl", "restart", "swiss-proxy.service"], capture_output=True, text=True, timeout=10)
    results.append("3️⃣ ⚙️ *Proxy Engine*: Перезапущено `swiss-proxy.service`")

    # 4. Probe live status
    time.sleep(2)
    st_a = probe_channel(1080, "Channel A")
    st_b = probe_channel(1081, "Channel B")

    results.append("\n📊 *РЕЗУЛЬТАТ НАЖИВО*:")
    if st_a["ok"]:
        results.append(f"  • 👨 Канал A (1080): 🟢 `{st_a['ip']}` ({st_a['country']}, {st_a['city']}) — {st_a['elapsed']}s")
    else:
        results.append("  • 👨 Канал A (1080): 🔴 Очікує підняття планшета")

    if st_b["ok"]:
        results.append(f"  • 👩 Канал B (1081): 🟢 `{st_b['ip']}` ({st_b['country']}, {st_b['city']}) — {st_b['elapsed']}s")
    else:
        results.append("  • 👩 Канал B (1081): 🔴 Очікує підняття смартфона")

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
        res = subprocess.run(["sudo", "tailscale", "set", "--exit-node="], capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return "🌐 *Успішно переключено на ПРЯМИЙ Інтернет!*\n(Exit Node вимкнено, конфігурацію оновлено)."
        else:
            return f"❌ Помилка tailscale set: `{res.stderr}`"
    else:
        set_env_var("PRIMARY_EXIT_NODE_IP", target)
        set_env_var("EXPECTED_EXIT_NODE_IP", target)
        res = subprocess.run(
            ["sudo", "tailscale", "set", f"--exit-node={target}", "--exit-node-allow-lan-access=true"],
            capture_output=True, text=True, timeout=10
        )
        if res.returncode == 0:
            ping_res = subprocess.run(["ping", "-c", "2", "google.com"], capture_output=True, text=True, timeout=5)
            ping_ok = "✅ Інтернет OK" if ping_res.returncode == 0 else "⚠️ Інтернет не відповідає"
            return f"✅ *Успішно активовано Exit Node*: `{target}`\n\n📊 *Перевірка доступності*: {ping_ok}"
        else:
            return f"❌ Помилка активації Exit Node `{target}`: `{res.stderr}`"

def process_command(cmd_text, chat_id):
    cmd = cmd_text.strip().lower()
    if cmd in ["/start", "/help", "ℹ️ допомога"]:
        msg = (
            "👋 *Вітаємо у боті керування Swiss Proxy Watchdog!*\n\n"
            "Тут ви можете:\n"
            "• Перевіряти статус каналів проксі\n"
            "• Керувати персонами (Чоловік / Дружина) в 1 клік\n"
            "• Виконувати повне авто-відновлення при падінні зв'язку\n"
            "• Дистанційно будити пристрої через Push (MacroDroid)\n\n"
            "Оберіть дію з меню нижче:"
        )
        send_message(chat_id, msg, reply_markup=get_main_keyboard())
    elif cmd in ["/status", "📊 перевірити статус"]:
        send_message(chat_id, "⏳ *Перевіряємо стан швейцарських каналів...*")
        msg = check_live_status()
        send_message(chat_id, msg, reply_markup=get_inline_keyboard())
    elif cmd in ["/personas", "/persona", "👥 керування персонами"]:
        msg, markup = handle_personas_menu()
        send_message(chat_id, msg, reply_markup=markup)
    elif cmd in ["/autoheal", "/heal", "🔄 повне відновлення (auto-heal)", "🔄 перезапустити проксі"]:
        send_message(chat_id, "⏳ *Запускаємо повне автоматичне відновлення...*")
        msg = handle_full_recovery()
        send_message(chat_id, msg, reply_markup=get_inline_keyboard())
    elif cmd in ["/wake", "⚡ розбудити пристрої (push)", "⚡ підняти tailscale (push)"]:
        msg, markup = handle_wake_menu()
        send_message(chat_id, msg, reply_markup=markup)
    elif cmd in ["/exitnode", "/nodes", "🌐 вибір exit node"]:
        msg, markup = handle_exitnode_list()
        send_message(chat_id, msg, reply_markup=markup)
    else:
        msg = "ℹ️ Невідома команда. Оберіть дію з меню нижче."
        send_message(chat_id, msg, reply_markup=get_main_keyboard())

def main():
    logger.info("Starting Telegram Bot Polling Daemon with Auto-Heal & Multi-Persona Manager...")
    offset = 0
    while True:
        try:
            updates = api_call("getUpdates", {"offset": offset, "timeout": 25})
            if updates and updates.get("ok"):
                for item in updates.get("result", []):
                    offset = item["update_id"] + 1

                    if "message" in item:
                        msg = item["message"]
                        chat_id = str(msg.get("chat", {}).get("id"))
                        text = msg.get("text", "")
                        if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
                            logger.warning(f"Unauthorized access attempt from chat_id {chat_id}")
                            continue
                        if text:
                            process_command(text, chat_id)

                    elif "callback_query" in item:
                        cq = item["callback_query"]
                        chat_id = str(cq.get("message", {}).get("chat", {}).get("id"))
                        data = cq.get("data", "")
                        cq_id = cq.get("id")
                        api_call("answerCallbackQuery", {"callback_query_id": cq_id})

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
                        elif data.startswith("p_setnode:"):
                            parts = data.split(":", 3)
                            p_id, n_ip, n_name = parts[1], parts[2], parts[3]
                            res_msg = handle_set_persona_node(p_id, n_ip, n_name)
                            send_message(chat_id, res_msg)
                            msg, markup = handle_persona_config_menu(p_id)
                            send_message(chat_id, msg, reply_markup=markup)
                        elif data.startswith("p_setlang:"):
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
            logger.error(f"Error in polling loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
