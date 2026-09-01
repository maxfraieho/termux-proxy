@echo off
chcp 65001 > nul
title Swiss Survey - ДРУЖИНА (Persona B)
echo ========================================================
echo   Запуск Швейцарського браузера Comet: ДРУЖИНА (Persona B)
echo   Проксі: socks5://100.66.97.93:1081 (Канал B)
echo ========================================================
start "" "C:\Program Files\Perplexity\Comet\Application\comet.exe" --user-data-dir="%LOCALAPPDATA%\Perplexity\Comet\User Data\SwissSurvey_Wife" --proxy-server="socks5://100.66.97.93:1081" --lang=de-CH --force-webrtc-ip-handling-policy=disable_non_proxied_udp --disable-reading-from-canvas --remote-debugging-port=9227 --remote-debugging-address=0.0.0.0 --remote-allow-origins=* --window-size=1536,864 https://ipinfo.io/json
