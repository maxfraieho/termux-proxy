@echo off
REM 🚀 Launch Persona B (Wife) Swiss Survey Browser
set PROFILE_DIR=%LOCALAPPDATA%\Google\Chrome\User Data\SwissSurveys_PersonaB
echo 🟢 Starting Persona B (Wife) on Swiss Proxy (100.66.97.93:1081)...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%PROFILE_DIR%" --proxy-server="socks5://100.66.97.93:1081" --lang="de-CH" --force-webrtc-ip-handling-policy=disable_non_proxied_udp --window-size=1536,864 --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36" https://ipinfo.io/json
