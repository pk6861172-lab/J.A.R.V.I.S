# JARVIS For Beginners

This file is for people who are new to computers, coding, GitHub, Python, and AI tools.

JARVIS is a personal AI assistant. It can chat with you, help with your computer, use online services, and connect with tools like Telegram, weather, news, email, camera, and a web app.

You do not need to understand everything on the first day. Start with the simple setup, make JARVIS run in text mode, and then add more features one by one.

If you want JARVIS to recognize family members, read [FAMILY_FACE_RECOGNITION.md](FAMILY_FACE_RECOGNITION.md) after basic setup works.

---

## Step 1: Download JARVIS

Use this easy method if you do not know Git.

1. Open the JARVIS GitHub page.
2. Click the green **Code** button.
3. Click **Download ZIP**.
4. After the ZIP downloads, right-click it.
5. Click **Extract All**.
6. Open the extracted `J.A.R.V.I.S` folder.

That is it. You now have the project on your computer.

If you already know Git, you can also use:

```bash
git clone https://github.com/pk6861172-lab/J.A.R.V.I.S.git
cd J.A.R.V.I.S
```

---

## Step 2: Install Python

JARVIS is made with Python.

Install **Python 3.10.x**.

When installing Python, tick this box:

```text
Add Python to PATH
```

This is important. It helps your computer understand the `python` command.

Avoid Python 3.12 for now because some camera and face packages may fail.

---

## Step 3: Install JARVIS Packages

Open the `J.A.R.V.I.S` folder.

If you are on Windows, first try double-clicking:

```text
setup_windows.bat
```

If that does not work, open PowerShell or Command Prompt in the folder and run:

```bash
pip install -r requirements.txt
```

This installs the extra packages JARVIS needs.

---

## Step 4: Make Your Private Settings File

JARVIS needs your private settings in a file named:

```text
jarvis_config.json
```

This file is not included with real passwords because every user must use their own private keys.

### How to create it

1. Find this file:

```text
jarvis_config.template.json
```

2. Copy it.
3. Paste the copy in the same folder.
4. Rename the copy to:

```text
jarvis_config.json
```

5. Open `jarvis_config.json`.
6. Add your own values.

Example:

```json
{
  "user_name": "YourName",
  "groq_api_key": "your-own-groq-key",
  "openweather_api_key": "your-own-weather-key",
  "news_api_key": "your-own-news-key",
  "email": "your-email@gmail.com",
  "email_password": "your-gmail-app-password",
  "telegram_bot_token": "your-telegram-bot-token",
  "telegram_allowed_user_id": 0,
  "web_api_token": "make-a-long-private-token"
}
```

You can leave features empty if you do not want to use them yet.

---

## Step 5: Understand API Keys

An API key is like a secret password for a website service.

| Key | What it is for |
|---|---|
| Groq API key | AI chat |
| Gemini API key | Vision/image features |
| OpenWeatherMap API key | Weather |
| NewsAPI key | News |
| Telegram bot token | Telegram control |
| Gmail app password | Email sending/reading |

Never share API keys in public.

Never upload these files:

```text
jarvis_config.json
.env
jarvis_mobile_settings.json
tokens.json
token_key.key
key.pem
cert.pem
```

These files can contain private information.

---

## Step 6: Start With Text Mode

Text mode is the easiest way to test JARVIS.

Run:

```bash
python jarvis.py --mode text
```

You can type messages to JARVIS. This does not need a microphone or camera.

Try asking:

```text
Hello JARVIS
Explain AI in simple words
What can you do?
```

---

## Step 7: Try Other Modes Later

After text mode works, you can try more.

| Command | What it starts |
|---|---|
| `python jarvis.py --mode hybrid` | Voice plus text fallback |
| `python jarvis_gui.py` | Desktop GUI |
| `python run_jarvis_bot.py` | Telegram bot |
| `python jarvis_web.py --host 127.0.0.1 --port 8765` | Web app on your computer |

For the web app, open:

```text
http://localhost:8765
```

---

## Step 8: Make JARVIS Owner-Only

If you want only you to use JARVIS, set owner protection.

### Telegram owner

Put your own Telegram user ID in:

```json
"telegram_allowed_user_id": 123456789
```

### Web app token

Use a long private token:

```json
"web_api_token": "make-this-long-random-and-secret"
```

Do not use weak tokens like:

```text
1234
password
jarvis
```

---

## Step 9: Safe Use Rules

JARVIS is powerful, so use it carefully.

1. Use JARVIS only on a computer you own.
2. Keep your API keys private.
3. Do not upload `jarvis_config.json`.
4. Do not let unknown people control your Telegram bot.
5. Do not expose the web app to the internet without a strong token.
6. Camera and microphone features should be used only with permission.
7. Do not make JARVIS secretly watch people or steal data.
8. If a secret was shown publicly, delete it from that website and create a new one.

---

## Step 10: Common Problems

| Problem | Simple fix |
|---|---|
| `python` not found | Reinstall Python and tick "Add Python to PATH" |
| Packages fail to install | Use Python 3.10 and run install again |
| JARVIS says config missing | Create `jarvis_config.json` from the template |
| Weather does not work | Add your OpenWeatherMap key |
| News does not work | Add your NewsAPI key |
| Telegram does not work | Check bot token and user ID |
| Web app does not open | Check `http://localhost:8765` |
| Token rejected | Use a longer `web_api_token` |

---

## Best Beginner Path

Follow this order:

1. Download ZIP.
2. Install Python 3.10.
3. Run `setup_windows.bat`.
4. Copy `jarvis_config.template.json`.
5. Rename the copy to `jarvis_config.json`.
6. Run `python jarvis.py --mode text`.
7. Add API keys one by one.
8. Try GUI, voice, Telegram, and web app later.

---

## Final Reminder

The JARVIS code can be public.

Your private config must stay private.

Every user should create their own `jarvis_config.json` and use their own API keys.
