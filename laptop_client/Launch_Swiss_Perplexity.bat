@echo off
title Swiss Perplexity Browser
echo Launching isolated Swiss Perplexity session via Oracle (100.66.97.93:1080)...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data\SwissPerplexity" --proxy-server="socks5://100.66.97.93:1080" https://www.perplexity.ai
