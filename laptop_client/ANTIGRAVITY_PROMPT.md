# 🤖 Antigravity Agent Deployment Prompt — Swiss Perplexity Launcher

Скопіюйте та відправте цей промпт агенту **Antigravity CLI** на ноутбуці для автоматичного створення кнопки швидкого запуску та ізольованого швейцарського профілю.

---

```text
Виконай автоматичне розгортання та створення ярлика швидкого запуску для ізольованого швейцарського браузера Perplexity.

МЕТА:
Створити на Робочому столі користувача окрему кнопку/ярлик "Swiss Perplexity", яка в один клік запускає ізольований Google Chrome із власною папкою профілю даних та примусовим маршрутуванням ВСЬОГО трафіку через Швейцарський проксі Oracle (socks5://100.66.97.93:1080).

КРОКИ ДЛЯ ВИКОНАННЯ:

1. Визнач ОС користувача (Windows / macOS / Linux).

2. Створи ярлик запуску на Робочому столі (Desktop):

   • ДЛЯ WINDOWS:
     Створи файл `%USERPROFILE%\Desktop\Swiss Perplexity.bat`:
     ```cmd
     @echo off
     title Swiss Perplexity Browser
     echo Launching isolated Swiss Perplexity session...
     start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data\SwissPerplexity" --proxy-server="socks5://100.66.97.93:1080" https://www.perplexity.ai
     ```

   • ДЛЯ MACOS:
     Створи файл `~/Desktop/Swiss Perplexity.command` та зроби його виконуваним (`chmod +x`):
     ```bash
     #!/bin/bash
     "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --user-data-dir="$HOME/Library/Application Support/Google/Chrome/SwissPerplexity" --proxy-server="socks5://100.66.97.93:1080" https://www.perplexity.ai &
     ```

   • ДЛЯ LINUX:
     Створи файл `~/.local/share/applications/swiss-perplexity.desktop` та `~/Desktop/Swiss Perplexity.desktop`:
     ```ini
     [Desktop Entry]
     Version=1.0
     Name=Swiss Perplexity
     Comment=Launch Chrome via Swiss Exit Proxy (100.66.97.93)
     Exec=google-chrome --user-data-dir=%h/.config/google-chrome/SwissPerplexity --proxy-server="socks5://100.66.97.93:1080" https://www.perplexity.ai
     Icon=google-chrome
     Terminal=false
     Type=Application
     Categories=Network;WebBrowser;
     ```
     Зроби його виконуваним (`chmod +x`).

3. Перевір працездатність:
   Запусти створений ярлик і відкрий `https://ipinfo.io/json` для підтвердження швейцарської геолокації (CH).
```
