@echo off
chcp 65001 > nul
title Swiss Survey - ЧОЛОВІК (Persona A)
echo ========================================================
echo   Запуск Швейцарського браузера Comet: ЧОЛОВІК (Persona A)
echo   Проксі: socks5://100.66.97.93:1080 (Канал A)
echo ========================================================
start "" "C:\Program Files\Perplexity\Comet\Application\comet.exe" --user-data-dir="%LOCALAPPDATA%\Perplexity\Comet\User Data\SwissSurvey_Husband" --proxy-server="socks5://100.66.97.93:1080" --lang=de-CH --force-webrtc-ip-handling-policy=disable_non_proxied_udp --disable-reading-from-canvas --remote-debugging-port=9225 --remote-debugging-address=0.0.0.0 --remote-allow-origins=* --window-size=1920,1080 https://ipinfo.io/json
