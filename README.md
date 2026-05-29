# J.A.R.V.I.S - Personal AI Assistant

J.A.R.V.I.S means **Just A Rather Very Intelligent System**.

It is a Python AI assistant that can chat, answer questions, open apps, check weather/news, use voice, run a web page, connect to Telegram, and do other computer-helper tasks.

This README is beginner-friendly. If you are very new, start with [for beginners.md](for%20beginners.md). That file explains setup like a simple school guide.

For family face recognition, read [FAMILY_FACE_RECOGNITION.md](FAMILY_FACE_RECOGNITION.md). It explains how to use local photos from Google Photos safely.

For Android access from anywhere through Ngrok, read [REMOTE_ACCESS.md](REMOTE_ACCESS.md).

> Important: JARVIS is safe to share because this repository does not need to contain your private passwords or API keys. Every user must add their own private settings on their own computer.

---

## 1. What You Need

| Thing | Why you need it |
|---|---|
| Windows laptop or PC | JARVIS runs best on Windows right now |
| Internet | To download files and use online services |
| Python 3.10 | The program language JARVIS uses |
| Your own API keys | Secret keys for AI, weather, news, Telegram, etc. |
| Patience | First setup can take some time |

Best Python version: **Python 3.10.x**

Avoid Python 3.12 for now because some camera/face packages may not install correctly.

---

## 2. Download JARVIS

### Easy Way: Download ZIP

Use this if you do not know Git.

1. Open the GitHub page for this project.
2. Click the green **Code** button.
3. Click **Download ZIP**.
4. Right-click the ZIP file and choose **Extract All**.
5. Open the extracted `J.A.R.V.I.S` folder.

### Advanced Way: Use Git

```bash
git clone https://github.com/pk6861172-lab/J.A.R.V.I.S.git
cd J.A.R.V.I.S
```

---

## 3. Install JARVIS

Open the `J.A.R.V.I.S` folder.

### Easy Windows Install

Double-click:

```text
setup_windows.bat
```

### Manual Install

If the setup file does not work, open Command Prompt or PowerShell inside the folder and run:

```bash
pip install -r requirements.txt
```

---

## 4. Make Your Private Settings File

JARVIS needs a private file called:

```text
jarvis_config.json
```

This file is for **your computer only**.

1. Find `jarvis_config.template.json`.
2. Make a copy of it.
3. Rename the copy to `jarvis_config.json`.
4. Open `jarvis_config.json`.
5. Fill only the things you want to use.

Example:

```json
{
  "user_name": "YourName",
  "groq_api_key": "paste-your-own-groq-key-here",
  "openweather_api_key": "paste-your-own-weather-key-here",
  "news_api_key": "paste-your-own-news-key-here",
  "email": "your-email@gmail.com",
  "email_password": "your-gmail-app-password",
  "telegram_bot_token": "your-telegram-bot-token",
  "telegram_allowed_user_id": 0,
  "web_api_token": "make-a-long-private-token"
}
```

You do not have to fill everything on day one. Start small.

---

## 5. What Is An API Key?

An API key is like a secret password for an online service.

| Service | What it does |
|---|---|
| Groq | Gives JARVIS an AI brain |
| Gemini | Helps with image/vision features |
| OpenWeatherMap | Gives weather |
| NewsAPI | Gives news |
| Telegram BotFather | Lets you control JARVIS from Telegram |

Never show API keys to anyone.

Never upload these files to GitHub:

```text
jarvis_config.json
.env
jarvis_mobile_settings.json
token_key.key
tokens.json
key.pem
cert.pem
```

This repository is configured so private files should stay on your computer.

---

## 6. Start JARVIS

Try the simplest mode first:

```bash
python jarvis.py --mode text
```

This lets you type to JARVIS without using microphone or camera.

When that works, try:

```bash
python jarvis.py --mode hybrid
```

For the desktop GUI:

```bash
python jarvis_gui.py
```

For Telegram:

```bash
python run_jarvis_bot.py
```

For the web app on your own computer:

```bash
python jarvis_web.py --host 127.0.0.1 --port 8765
```

Then open:

```text
http://localhost:8765
```

For phone access on the same Wi-Fi, set a strong token and run:

```powershell
$env:JARVIS_WEB_TOKEN="choose-a-long-private-token"
python jarvis_web.py --host 0.0.0.0 --port 8765
```

Then open this on your phone:

```text
http://YOUR-PC-LAN-IP:8765
```

---

## 7. What Can I Ask JARVIS?

| You say/type | What JARVIS tries to do |
|---|---|
| Explain photosynthesis | Explains a topic |
| Open Chrome | Opens an app |
| What is the weather? | Shows weather if configured |
| Top news today | Shows news if configured |
| Take a note: buy milk | Saves a note |
| Take a screenshot | Saves a screenshot |
| System status | Shows CPU, RAM, battery, etc. |
| Start camera | Starts camera features if allowed |
| Send email | Uses Gmail if configured |
| Open Telegram bot | Uses Telegram if configured |

Some commands need extra setup. If a command does not work yet, check the settings file.

---

## 8. Safety Rules

Please read this part carefully.

1. Keep `jarvis_config.json` private.
2. Do not paste real passwords into public GitHub files.
3. Use your own API keys, not someone else's.
4. Use a strong `web_api_token` if you use the web app.
5. Set `telegram_allowed_user_id` so only you can control the Telegram bot.
6. Do not give JARVIS permission to control a computer you do not own.
7. Camera, microphone, email, WhatsApp, Telegram, and screen tools should be used only with permission.
8. JARVIS should not be changed to secretly watch people, steal data, bypass security, or expose private files.

JARVIS can be powerful, but it must be used responsibly.

---

## 9. Owner-Only Protection

If you want only you to use your JARVIS:

### Telegram

Set your own Telegram user ID:

```json
"telegram_allowed_user_id": 123456789
```

### Web App

Set a long private token:

```json
"web_api_token": "make-this-long-random-and-private"
```

Do not use simple tokens like `1234`, `password`, or `jarvis`.

### Config Files

Private config files are ignored by Git so they do not get uploaded by mistake.

---

## 10. Gmail Setup

Do not use your normal Gmail password.

Use a Gmail App Password:

1. Go to `myaccount.google.com`.
2. Open **Security**.
3. Turn on **2-Step Verification**.
4. Create an **App Password** for Mail.
5. Paste that app password in `jarvis_config.json`.

---

## 11. Telegram Setup

1. Open Telegram.
2. Search for `@BotFather`.
3. Create a new bot.
4. Copy the bot token.
5. Search for `@userinfobot`.
6. Copy your user ID.
7. Put both values in `jarvis_config.json`.
8. Run:

```bash
python run_jarvis_bot.py
```

---

## 12. If Something Goes Wrong

| Problem | Try this |
|---|---|
| `python` not found | Install Python 3.10 and tick "Add Python to PATH" |
| Install fails | Run `pip install -r requirements.txt` again |
| Microphone not working | Allow microphone access in Windows settings |
| Config error | Check commas and quotes in `jarvis_config.json` |
| Telegram not replying | Check bot token and `telegram_allowed_user_id` |
| Weather/news not working | Check your API key |
| Camera package fails | Use Python 3.10 instead of Python 3.12 |
| Web app rejects token | Set a stronger `web_api_token` |

If you are new, start with text mode first:

```bash
python jarvis.py --mode text
```

---

## 13. Project Files In Simple Words

| File/folder | Meaning |
|---|---|
| `jarvis.py` | Main JARVIS program |
| `jarvis_gui.py` | Desktop GUI version |
| `jarvis_web.py` | Web app/server version |
| `run_jarvis_bot.py` | Telegram bot runner |
| `jarvis_config.template.json` | Safe example settings file |
| `jarvis_config.json` | Your private settings file, do not upload |
| `requirements.txt` | List of Python packages to install |
| `setup_windows.bat` | Easy Windows installer |
| `backend/` | Web/backend code |
| `web/` | Browser app files |
| `mobile/` | Mobile app files |

---

## 14. Advanced Users

These files are for people who already know deployment, Docker, servers, or mobile builds:

| File | Purpose |
|---|---|
| `SECURITY.md` | Security notes |
| `DEPLOY.md` | Deployment guide |
| `README_DEPLOYMENT.md` | More deployment details |
| `ADMIN_API.md` | Admin API notes |
| `WEBRTC_SETUP.md` | WebRTC setup |
| `mobile/README.md` | Mobile notes |
| `mobile/android/README.md` | Android notes |
| `docker-compose.yml` | Docker local setup |
| `docker-compose.prod.yml` | Docker production setup |

Beginners can ignore this section at first.

---

## 15. For People Who Fork This Project

If you copy this project to your own GitHub:

1. Do not upload `jarvis_config.json`.
2. Do not upload `.env`.
3. Do not upload real API keys.
4. Do not upload private certificates.
5. Use the template files only.
6. Tell users to create their own config.
7. If a key was ever shown publicly, delete it from the service dashboard and make a new one.

Before publishing, check that no private files are tracked:

```bash
git status
git ls-files
```

You can also search for accidental secrets before pushing.

---

## 16. Current Features

| Feature | Status |
|---|---|
| AI chat | Available |
| Text mode | Available |
| Voice mode | Available |
| Desktop GUI | Available |
| Weather | Needs API key |
| News | Needs API key |
| Gmail | Needs Gmail app password |
| Telegram bot | Needs Telegram setup |
| Web app | Available |
| Camera and vision | Depends on setup |
| Family face recognition | Uses local `known_faces/` folders |
| WhatsApp bridge | Depends on setup |
| Mobile app | Advanced setup |
| Docker/server deployment | Advanced setup |

---

## 17. About

Built by **Prashant Bhagat**.

GitHub: [pk6861172-lab](https://github.com/pk6861172-lab)

J.A.R.V.I.S is made for learning, experimenting, and building a personal AI assistant safely.

---

## Final Reminder

The code can be public.

Your secrets must stay private.

Every user should create their own `jarvis_config.json` and use their own API keys.
