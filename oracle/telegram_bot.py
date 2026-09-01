#!/usr/bin/env python3
"""
telegram_bot.py — Interactive Telegram Bot Daemon for Swiss Proxy & Watchdog
Listens for commands: /start, /status, /wake, /restart, /exitnode
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
            [{"text": "📊 Перевірити статус"}, {"text": "🌐 Вибір Exit Node"}],
            [{"text": "⚡ Підняти Tailscale (Push)"}, {"text": "🔄 Перезапустити проксі"}],
            [{"text": "ℹ️ Допомога"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def get_inline_keyboard():
    buttons = [
        [{"text": "📊 Перевірити статус", "callback_data": "cmd_status"}],
        [{"text": "🌐 Вибір Exit Node", "callback_data": "cmd_exitnode"}],
        [{"text": "⚡ Підняти Tailscale (Push)", "callback_data": "cmd_wake"}],
        [{"text": "🔄 Перезапустити проксі", "callback_data": "cmd_restart"}]
    ]
    return {"inline_keyboard": buttons}

def set_env_var(key: str, val: str):
    env_file = "/opt/watchdog/.env"
    lines = []
    found = False
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
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
    
    with open(env_file, 'w', encoding='utf-8') as f:
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
                # Exclude Ukrainian/non-Swiss nodes (e.g. 100.80.16.33 rpi4b)
                if ip == "100.80.16.33" or "rpi" in name.lower():
                    continue
                peers.append({"ip": ip, "name": name, "online": online})

        
        env = load_env()
        primary_ip = env.get("PRIMARY_EXIT_NODE_IP", "")
        return current_ip, primary_ip, peers
    except Exception as e:
        logger.error(f"Error getting exit nodes: {e}")
        return None, None, []

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

    lines = ["📊 *СТАТУС ПОДВІЙНОГО ПРОКСІ (DUAL PERSONA)*\n"]

    # Channel A
    if st_a["ok"]:
        icon_a = "🟢" if st_a["country"] == "CH" else "🟡"
        lines.append(
            f"{icon_a} *Канал A (Чоловік / Порт 1080 & 8888)*:\n"
            f"  • IP: `{st_a['ip']}` ({st_a['country']}, {st_a['city']})\n"
            f"  • ISP: `{st_a['org']}`\n"
            f"  • Час: `{st_a['elapsed']}s`\n"
        )
    else:
        lines.append("🔴 *Канал A (Порт 1080)*: Не відповідає\n")

    # Channel B
    if st_b["ok"]:
        icon_b = "🟢" if st_b["country"] == "CH" else "🟡"
        lines.append(
            f"{icon_b} *Канал B (Дружина / Порт 1081 & 8889)*:\n"
            f"  • IP: `{st_b['ip']}` ({st_b['country']}, {st_b['city']})\n"
            f"  • ISP: `{st_b['org']}`\n"
            f"  • Час: `{st_b['elapsed']}s`\n"
        )
    else:
        lines.append("🔴 *Канал B (Порт 1081)*: Очікує підключення другого пристрою\n")

    lines.append("💡 *Підказка*: Переконайтеся, що кожен браузер налаштований на свій порт!")
    return "\n".join(lines)

def handle_wake():
    if not MACRODROID_URL or "YOUR_DEVICE_ID" in MACRODROID_URL:
        return (
            "⚠️ *ПОМИЛКА*: MacroDroid Webhook URL ще не налаштовано!\n\n"
            "Додайте скопійоване посилання MacroDroid у файл `/opt/watchdog/.env` на Oracle:\n"
            "`MACRODROID_WEBHOOK_URL=\"https://trigger.macrodroid.com/ВАШ_ID/wake_tailscale\"`"
        )
    try:
        req = urllib.request.Request(MACRODROID_URL, headers={'User-Agent': 'Oracle-Watchdog-Bot'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return (
                "📲 *СИГНАЛ НАДІСЛАНО!*\n\n"
                "⚡ FCM Push-сигнал успішно відправлено на ваш планшет через MacroDroid.\n"
                "Зачекайте 5-10 секунд та натисніть *📊 Перевірити статус*."
            )
    except Exception as e:
        return f"❌ *Помилка відправки Push на MacroDroid*: `{e}`"

def handle_restart():
    try:
        res = subprocess.run(
            ["sudo", "systemctl", "restart", "swiss-proxy.service"],
            capture_output=True, text=True, timeout=15
        )
        if res.returncode == 0:
            return "🔄 *Службу swiss-proxy.service успішно перезапущено на Oracle!*"
        else:
            return f"❌ *Помилка перезапуску*: `{res.stderr}`"
    except Exception as e:
        return f"❌ *Помилка*: `{e}`"

def process_command(cmd_text, chat_id):
    cmd = cmd_text.strip().lower()
    if cmd in ["/start", "/help", "ℹ️ допомога"]:
        msg = (
            "👋 *Вітаємо у боті керування Swiss Proxy Watchdog!*\n\n"
            "Тут ви можете перевіряти статус шлюзу, обирати кінцеву точку (Exit Node) з доступних або перезапускати служби.\n\n"
            "Оберіть дію з меню нижче:"
        )
        send_message(chat_id, msg, reply_markup=get_main_keyboard())
    elif cmd in ["/status", "📊 перевірити статус"]:
        send_message(chat_id, "⏳ *Перевіряємо стан швейцарського проксі...*")
        msg = check_live_status()
        send_message(chat_id, msg, reply_markup=get_inline_keyboard())
    elif cmd in ["/exitnode", "/nodes", "🌐 вибір exit node"]:
        msg, markup = handle_exitnode_list()
        send_message(chat_id, msg, reply_markup=markup)
    elif cmd in ["/wake", "⚡ підняти tailscale (push)"]:
        send_message(chat_id, "⏳ *Відправляємо FCM Push на планшет...*")
        msg = handle_wake()
        send_message(chat_id, msg, reply_markup=get_inline_keyboard())
    elif cmd in ["/restart", "🔄 перезапустити проксі"]:
        send_message(chat_id, "⏳ *Перезапускаємо службу проксі...*")
        msg = handle_restart()
        send_message(chat_id, msg, reply_markup=get_inline_keyboard())
    else:
        msg = "ℹ️ Невідома команда. Оберіть дію з меню нижче."
        send_message(chat_id, msg, reply_markup=get_main_keyboard())

def main():
    logger.info("Starting Telegram Bot Polling Daemon with Exit Node Selector...")
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
                        elif data == "cmd_exitnode":
                            process_command("/exitnode", chat_id)
                        elif data == "cmd_wake":
                            process_command("/wake", chat_id)
                        elif data == "cmd_restart":
                            process_command("/restart", chat_id)
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
