#!/usr/bin/env python3
"""
telegram_bot.py — Interactive Telegram Bot Daemon for Swiss Proxy & Watchdog
Listens for commands: /start, /status, /wake, /restart
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
            [{"text": "📊 Перевірити статус"}, {"text": "⚡ Підняти Tailscale (Push)"}],
            [{"text": "🔄 Перезапустити проксі"}, {"text": "ℹ️ Допомога"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def get_inline_keyboard():
    buttons = [
        [{"text": "📊 Перевірити статус", "callback_data": "cmd_status"}],
        [{"text": "⚡ Підняти Tailscale (Push)", "callback_data": "cmd_wake"}],
        [{"text": "🔄 Перезапустити проксі", "callback_data": "cmd_restart"}]
    ]
    return {"inline_keyboard": buttons}

def check_live_status():
    start = time.time()
    try:
        res = subprocess.run(
            ['curl', '-s', '--connect-timeout', '8', '--proxy', 'socks5://127.0.0.1:1080', 'https://ipinfo.io/json'],
            capture_output=True, text=True, timeout=12
        )
        elapsed = round((time.time() - start), 2)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            ip = data.get("ip", "N/A")
            country = data.get("country", "N/A")
            city = data.get("city", "N/A")
            org = data.get("org", "N/A")
            hostname = data.get("hostname", "N/A")

            status_icon = "🟢" if country == "CH" else "🟡"
            msg = (
                f"{status_icon} *СТАТУС МЕРЕЖІ SWISS PROXY*\n\n"
                f"🌐 *Вихідний IP*: `{ip}`\n"
                f"🇨🇭 *Країна*: `{country}` ({city})\n"
                f"🏢 *Провайдер*: `{org}`\n"
                f"📡 *Хост*: `{hostname}`\n"
                f"⏱ *Час відповіді*: `{elapsed}s`\n"
                f"🔒 *Маскування*: Повне (Swisscom CH)\n\n"
                f"✅ *Швейцарський шлюз працює стабільно!*"
            )
            return msg
        else:
            raise RuntimeError(res.stderr or f"curl exit code {res.returncode}")
    except Exception as e:
        logger.warning(f"Status check failed: {e}")
        return (
            f"🔴 *ПОМИЛКА З'ЄДНАННЯ з Swiss Proxy*\n\n"
            f"❌ Не вдалося отримати відповідь від socks5://127.0.0.1:1080\n"
            f"⚠️ Деталі: `{e}`\n\n"
            f"💡 Скористайтеся кнопкою *⚡ Підняти Tailscale (Push)* або *🔄 Перезапустити проксі*."
        )

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
            "Тут ви можете миттєво перевірити статус швейцарського шлюзу, підняти Tailscale на пристрої вручну або перезапустити служби.\n\n"
            "Оберіть дію з меню нижче або скористайтесь кнопками:"
        )
        send_message(chat_id, msg, reply_markup=get_main_keyboard())
    elif cmd in ["/status", "📊 перевірити статус"]:
        send_message(chat_id, "⏳ *Перевіряємо стан швейцарського проксі...*")
        msg = check_live_status()
        send_message(chat_id, msg, reply_markup=get_inline_keyboard())
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
    logger.info("Starting Telegram Bot Polling Daemon...")
    offset = 0
    while True:
        try:
            updates = api_call("getUpdates", {"offset": offset, "timeout": 25})
            if updates and updates.get("ok"):
                for item in updates.get("result", []):
                    offset = item["update_id"] + 1

                    # Handle message
                    if "message" in item:
                        msg = item["message"]
                        chat_id = str(msg.get("chat", {}).get("id"))
                        text = msg.get("text", "")
                        if ALLOWED_CHAT_ID and chat_id != ALLOWED_CHAT_ID:
                            logger.warning(f"Unauthorized access attempt from chat_id {chat_id}")
                            continue
                        if text:
                            process_command(text, chat_id)

                    # Handle callback_query (inline buttons)
                    elif "callback_query" in item:
                        cq = item["callback_query"]
                        chat_id = str(cq.get("message", {}).get("chat", {}).get("id"))
                        data = cq.get("data", "")
                        cq_id = cq.get("id")
                        api_call("answerCallbackQuery", {"callback_query_id": cq_id})

                        if data == "cmd_status":
                            process_command("/status", chat_id)
                        elif data == "cmd_wake":
                            process_command("/wake", chat_id)
                        elif data == "cmd_restart":
                            process_command("/restart", chat_id)

        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
