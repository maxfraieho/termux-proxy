@echo off
REM 🚀 Launch Persona A (Husband) Swiss Survey Browser
set PROFILE_DIR=%LOCALAPPDATA%\Google\Chrome\User Data\SwissSurveys_PersonaA
echo 🟢 Starting Persona A (Husband) on Swiss Proxy (100.66.97.93:1080)...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%PROFILE_DIR%" --proxy-server="socks5://100.66.97.93:1080" --lang="de-CH" --force-webrtc-ip-handling-policy=disable_non_proxied_udp --window-size=1920,1080 https://ipinfo.io/json
