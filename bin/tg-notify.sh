#!/data/data/com.termux/files/usr/bin/bash
# tg-notify.sh MESSAGE
BOT_TOKEN="8508516661:AAEQBWvlBk3v62nd5ut3ei70TPFJTkV9LMs"
CHAT_ID="6412868393"
MSG="$1"
curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage"   -d "chat_id=${CHAT_ID}"   --data-urlencode "text=${MSG}"   --max-time 10 || true
