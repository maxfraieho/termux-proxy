# 🚀 Swiss Browser & Perplexity Proxy Client Setup

Інструкція та клієнтський комплект підключення ноутбука (Windows / macOS / Linux) до **Повного Швейцарського Браузерного Шлюзу**.

При запуску цього режиму **АБСОЛЮТНО ВЕСЬ ТРАФІК БРАУЗЕРА** (всі вкладки, переходи за посиланнями, Perplexity, зовнішні сайти та API) примусово і повністю маршрутизується через проксі **Oracle (`100.66.97.93`)** ➔ Швейцарський планшет-вихід (`100.100.74.9`).

---

## ⚡ Варіант 1: Ізольований Швейцарський Браузер (Рекомендовано)

Запускає **окремий повністю ізольований екземпляр Google Chrome** із власним профілем даних `SwissPerplexity`. Усі сайти, відкриті у цьому браузері, функціонують **100% через Швейцарію**.

### 🪟 Команда для Windows (CMD / PowerShell):
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%LOCALAPPDATA%\Google\Chrome\User Data\SwissPerplexity" --proxy-server="socks5://100.66.97.93:1080" https://www.perplexity.ai
```

### 🍎 Команда для macOS (Terminal):
```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --user-data-dir="$HOME/Library/Application Support/Google/Chrome/SwissPerplexity" --proxy-server="socks5://100.66.97.93:1080" https://www.perplexity.ai
```

### 🐧 Команда для Linux (Terminal):
```bash
google-chrome --user-data-dir="$HOME/.config/google-chrome/SwissPerplexity" --proxy-server="socks5://100.66.97.93:1080" https://www.perplexity.ai
```

---

## 🎯 Варіант 2: Налаштування всієї системи / браузера через `proxy.pac`

Файл `proxy.pac` направляє **весь веб-трафік** вашої системи чи конкретного профілю браузера через швейцарський проксі Oracle, виключаючи лише локальні IP-адреси (`127.0.0.1`, `192.168.x.x`, `10.x.x.x`).

### 🌐 Підключення в Windows:
1. Збережіть файл `proxy.pac` на ноутбуку (наприклад, `C:\Proxy\proxy.pac`).
2. Відкрийте **Параметри** (`Win + I`) ➔ **Мережа та Інтернет** ➔ **Проксі-сервер**.
3. У розділі **Автоматичне налаштування проксі**:
   * Увімкніть **Використовувати сценарій налаштування**.
   * Вкажіть шлях: `file:///C:/Proxy/proxy.pac` (або URL веб-сервера).
4. Натисніть **Зберегти**.

### 🍏 Підключення в macOS:
1. Відкрийте **Системні параметри** ➔ **Мережа**.
2. Виберіть активне з'єднання ➔ **Деталі** (Details) ➔ вкладка **Проксі** (Proxies).
3. Увімкніть **Автоматичне конфігурування проксі (PAC)**.
4. Введіть шлях до файлу: `file:///Users/YourUser/Documents/proxy.pac`.
5. Натисніть **ОК** та **Застосувати**.

---

## 🤖 Автоматичне розгортання агентом Antigravity CLI

Для швидкого розгортання та виведення **Окремої Кнопки Запуску (Desktop Shortcut)** скопіюйте файл [ANTIGRAVITY_PROMPT.md](file:///storage/emulated/0/Documents/termux-proxy/laptop_client/ANTIGRAVITY_PROMPT.md) або відправте агенту наступний промпт:

```text
Виконай автоматичне розгортання та створення ярлика швидкого запуску для ізольованого швейцарського браузера Perplexity.
Створи на Робочому столі (Desktop) окрему кнопку/ярлик "Swiss Perplexity", яка в 1 клік запускає ізольований Google Chrome із власною папкою профілю даних та примусовим маршрутуванням ВСЬОГО трафіку через Швейцарський проксі Oracle (socks5://100.66.97.93:1080).
```

### 🔘 Готові файли швидкого запуску в цій папці:
* **`Launch_Swiss_Perplexity.bat`** — Запуск для Windows CMD/PowerShell.
* **`Launch_Swiss_Perplexity.command`** — Запуск для macOS Terminal.
* **`Launch_Swiss_Perplexity.desktop`** — Ярлик для Linux Desktop.

---

## 🔍 Перевірка швейцарської геолокації
1. У запущеному швейцарському браузері відкрийте сторінку перевірки IP: `https://ipinfo.io/json`.
2. Значення `"country"` має бути **`"CH"` (Switzerland)**, а місто — **Zürich** або інше місто Швейцарії.
