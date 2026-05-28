# J.A.R.V.I.S — Personal AI Assistant
## Just A Rather Very Intelligent System

```
  ╔══════════════════════════════════════════════════════════════╗
  ║   Built by Prashant Bhagat  |  Powered by Claude AI + Groq  ║
  ║   Bihar, India  |  Class 11 Student  |  Future AI Engineer  ║
  ╚══════════════════════════════════════════════════════════════╝
```

> *"Sometimes you gotta run before you can walk." — Tony Stark*

---

## 🎬 Demo

> 📹 **[Watch JARVIS in action → YouTube Demo](#)** *(coming soon)*

---

## ✨ Features

| Module | What JARVIS Can Do |
|---|---|
| 🎙️ Voice | Wake word detection (OpenWakeWord / Google STT), TTS male voice |
| 🧠 AI Brain | Claude AI + Groq — full conversational intelligence, memory |
| 💻 System | Open 92+ apps, hardware monitor, volume, screenshot, file search |
| 📧 Email | Check unread Gmail, send emails by voice |
| 📅 Calendar | Today/upcoming events, add events, Google Calendar |
| 🌤️ Weather | Real-time weather + forecast (OpenWeatherMap) |
| 📰 News | Top headlines, topic-specific news (NewsAPI) |
| 📝 Notes | Voice notes, reminders, saved as JSON |
| 📷 Camera | Live camera feed with HUD overlay, 5 vision modes, face detection |
| 💬 WhatsApp | Send WhatsApp messages by voice via pywhatkit |
| 📱 Telegram Bot | Control JARVIS from your phone via Telegram |
| 🌐 HTTP Server | Mobile app integration via Flask REST API |
| 🔍 OCR | Read screen content using Tesseract |
| 🤖 Offline LLM | Ollama fallback when internet is down |
| 🔒 Power | Lock, shutdown, restart PC with voice confirmation |

---

## 🖥️ GUI Screenshots

```
┌─────────────────────────────────────────────────────┐
│  J.A.R.V.I.S HUD  ── Iron Man style dark interface  │
│  ┌─────────────┐  ┌──────────────────┐  ┌─────────┐ │
│  │ Camera Feed │  │   Chat / AI      │  │  Stats  │ │
│  │ + HUD modes │  │   Interface      │  │  Radar  │ │
│  └─────────────┘  └──────────────────┘  └─────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## ⚡ Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/pk6861172-lab/J.A.R.V.I.S.git
cd J.A.R.V.I.S
```

### 2. Install dependencies

**Windows (recommended):**
```bash
setup_windows.bat
```

**Manual:**
```bash
pip install -r requirements.txt
```

> ⚠️ **Python 3.10.x recommended.** Python 3.12 will break `dlib` / `face_recognition`.

---

### 3. Configure JARVIS

Copy `jarvis_config.template.json` → rename to `jarvis_config.json` and fill in:

```json
{
  "user_name": "YourName",
  "groq_api_key": "get from console.groq.com — FREE",
  "openweather_api_key": "free at openweathermap.org",
  "news_api_key": "free at newsapi.org",
  "email": "your@gmail.com",
  "email_password": "Gmail App Password (NOT your login password)",
  "telegram_bot_token": "get from @BotFather on Telegram",
  "telegram_allowed_user_id": 0
}
```

> Important: `jarvis_config.json` is a private local file. It must never be uploaded to GitHub. This repository tracks only `jarvis_config.template.json`, which contains placeholders and safe defaults.

#### Get API Keys (all free):
| Service | Link |
|---|---|
| Groq AI | [console.groq.com](https://console.groq.com) |
| OpenWeatherMap | [openweathermap.org/api](https://openweathermap.org/api) |
| NewsAPI | [newsapi.org](https://newsapi.org) |
| Telegram Bot | Message `@BotFather` on Telegram |

### Safety First

JARVIS is designed to be safe to share as source code, but each user must configure their own private runtime files before using it:

- Keep `jarvis_config.json` and `.env` local. They are ignored by Git because they can contain API keys, passwords, Telegram tokens, email app passwords, and personal settings.
- Use `jarvis_config.template.json` and `.env.example` as examples only. Do not paste real secrets into template/example files.
- Set a strong `web_api_token` or `JARVIS_WEB_TOKEN` before exposing the web/PWA bridge on your Wi-Fi or the internet. Weak defaults like `jarvis` or `1234` are rejected.
- Telegram control is owner-only. Set `telegram_allowed_user_id` to your own Telegram user ID.
- Non-owner secretary replies use static safe replies by default. AI auto-replies for other people are disabled unless you explicitly enable them in your private config.
- Self-improvement requests are guarded. JARVIS can queue feature requests, but security bypasses, secret-reading, covert surveillance, and always-on camera monitoring are blocked.
- Camera, screen, email, WhatsApp, Telegram, and system-control features should be enabled only on a computer you own and consent to operate.

If you fork this project, create your own config from the templates and rotate any secret that was ever committed, pasted into chat, or shown publicly.

#### Repository Credential Check

The public repository should contain no real API keys, passwords, Telegram bot tokens, email app passwords, OAuth tokens, private certificates, browser sessions, face images, or generated runtime state. Before publishing your own fork, run a secret scan and confirm these files stay local only:

- `jarvis_config.json`
- `.env`
- `jarvis_mobile_settings.json`
- `.jarvis_runtime/`
- `owner_faces/`
- `jarvis_photos/`
- `uploads/`
- `scripts/backend/certs/`

#### Gmail App Password:
1. myaccount.google.com → Security
2. Enable 2-Step Verification
3. App Passwords → Generate for "Mail"
4. Paste 16-char password in config

---

### 4. Run JARVIS

```bash
# GUI mode (recommended) — Iron Man HUD interface
python jarvis_gui.py

# Hybrid mode (voice + text fallback)
python jarvis.py --mode hybrid

# Text only (no microphone needed)
python jarvis.py --mode text

# Telegram bot only (control from phone)
python run_jarvis_bot.py

# Web/PWA interface on this computer
python jarvis_web.py --host 127.0.0.1 --port 8765
```

Open: http://localhost:8765

For phone access on the same Wi-Fi, set a LAN token and run the web bridge on all interfaces:

```powershell
$env:JARVIS_WEB_TOKEN="choose-a-long-token"
python jarvis_web.py --host 0.0.0.0 --port 8765
```

Then open `http://YOUR-PC-LAN-IP:8765` on the phone, save the token in the web UI, and install it as a PWA from the browser menu.

---

## 🌐 Cross-Platform Builds

JARVIS now has three deployable surfaces:

| Target | What to use | Output |
|---|---|---|
| Web / PWA | `jarvis_web.py` + `web/` | Browser app, installable PWA |
| Windows desktop | `scripts/build_windows_exe.ps1` | `.exe` in `dist/` |
| macOS desktop | `scripts/build_macos_app.sh` on macOS | `.app` in `dist/` |
| Android | `mobile/android` + Buildozer | `.apk` in `mobile/android/bin/` |
| iOS | PWA now, native build requires macOS + Xcode | Installable web app or signed native app |

### Build Windows EXE

```powershell
.\scripts\build_windows_exe.ps1 -Target all
```

Outputs:
- `dist/JARVIS/` for the desktop GUI build
- `dist/JARVIS-Web.exe` for the web bridge build

### Build Android APK

Buildozer needs Linux or WSL:

```bash
./scripts/build_android_apk.sh
```

The Android app is a companion controller. Keep JARVIS running on the PC with `jarvis_web.py`, then set the mobile app server URL to `http://YOUR-PC-LAN-IP:8765`.
If the first build needs system packages, install `python3-venv`, `openjdk-17-jdk`, `zip`, `unzip`, and `git` inside WSL/Linux, then rerun the script.

### Build macOS App

Run this on a Mac:

```bash
./scripts/build_macos_app.sh
```

Apple signing/notarization and iOS device builds must be done from macOS with Xcode.

---

## 🎙️ Voice Commands

### System Control
| Say | Action |
|---|---|
| "Open Chrome / VS Code / Kali..." | Launches any of 92+ apps |
| "System status" | CPU, RAM, disk, battery |
| "Take a screenshot" | Saves to Pictures |
| "Set volume to 70" | Sets system volume |
| "Lock the screen" | Locks PC |
| "Shutdown / Restart" | Power control with confirmation |
| "Find file [name]" | Search entire file system |

### Email & Communication
| Say | Action |
|---|---|
| "Check my emails" | Reads unread Gmail |
| "Send email to [name]" | Guided email composition |
| "Send WhatsApp to [contact]" | Sends WhatsApp message |

### Info & Productivity
| Say | Action |
|---|---|
| "What's the weather" | Current weather |
| "Top news today" | Latest headlines |
| "News about AI" | Topic-specific news |
| "Take a note: [text]" | Saves voice note |
| "Remind me in 10 minutes" | Timed reminder |
| "Read my screen" | OCR screen content |

### Camera & Vision
| Say | Action |
|---|---|
| "Start camera" | Live feed with HUD |
| "Capture photo" | Saves frame |
| "Describe what you see" | AI vision analysis |

### AI Conversation
Anything else goes directly to Claude AI:
- "Explain recursion to me"
- "Help me write a Python function"
- "What's the difference between TCP and UDP?"
- "Solve this JEE Math problem..."

---

## 📱 Telegram Bot Control

Control JARVIS remotely from your phone:

1. Create bot via `@BotFather` → get token
2. Get your ID via `@userinfobot`
3. Add both to `jarvis_config.json`
4. Run `python run_jarvis_bot.py`

| Telegram Command | Action |
|---|---|
| `/start` | Show available commands |
| `/screenshot` | Get live PC screenshot |
| `system status` | Hardware report |
| `open chrome` | Launch app remotely |
| `weather` | Current weather |
| Any text | Full JARVIS AI response |

---

## 🗂️ File Structure

```
J.A.R.V.I.S/
├── jarvis.py                  ← Core AI engine
├── jarvis_gui.py              ← Iron Man HUD GUI
├── jarvis_gui_perf.py         ← Performance-optimized GUI
├── run_jarvis_bot.py          ← Telegram bot runner
├── jarvis_config.template.json← Config template (safe to share)
├── requirements.txt           ← Python dependencies
├── setup_windows.bat          ← Windows auto-installer
├── contacts.csv               ← Contact list for WhatsApp
├── .gitignore                 ← Protects your API keys
├── .env.example               ← Environment vars template
│
├── ANDROID/                   ← Mobile app (Kivy)
│   ├── main.py
│   └── buildozer.spec
│
└── assets/                    ← Icons, sounds (optional)
    └── jarvis.ico
```

---

## 🛠️ Adding Custom Apps

In `jarvis_config.json`:

```json
"custom_apps": {
  "pycharm":    "pycharm",
  "kali":       "wsl -d kali-linux",
  "burpsuite":  "C:\\BurpSuite\\burpsuite_community.exe",
  "obs":        "obs"
}
```

Then say: *"JARVIS, open Burpsuite"* ✓

---

## 🔧 Troubleshooting

| Problem | Fix |
|---|---|
| PyAudio install fails | `pip install pipwin` then `pipwin install pyaudio` |
| Microphone not detected | Settings → Privacy → Microphone → Allow apps |
| JSON config error | Check for single `\` in file paths — use `\\` |
| face_recognition install fails | Use Python 3.10, not 3.12. Install dlib first |
| Telegram bot not responding | Check token and allowed_user_id in config |
| OCR not working | Install Tesseract from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki) and add to PATH |
| Offline STT not working | Download Vosk model, set path in config |

---

## 🔒 Security Notes

- **Never commit** `jarvis_config.json` — it contains your API keys
- Use `jarvis_config.template.json` as a safe shareable version
- `.gitignore` already excludes sensitive files
- Rotate your API keys periodically

---

## 📦 Tech Stack

```
AI:        Claude AI (Anthropic) + Groq
GUI:       Python Tkinter + OpenCV
Voice:     SpeechRecognition + pyttsx3 + OpenWakeWord + Vosk
Camera:    OpenCV + face_recognition
APIs:      OpenWeatherMap + NewsAPI + pywhatkit
Remote:    python-telegram-bot + Flask
Offline:   Ollama (local LLM)
```

---

## 🚀 Roadmap

- [x] Voice control + wake word
- [x] Gmail integration
- [x] Weather + News APIs
- [x] Camera + HUD + vision modes
- [x] WhatsApp messaging
- [x] Telegram bot
- [x] Mobile app (Kivy)
- [x] Offline STT (Vosk)
- [x] Face recognition
- [x] Ollama offline LLM
- [ ] Custom trained wake word
- [ ] Emotion detection (librosa)
- [ ] Windows EXE package
- [ ] Android APK release
- [ ] Screen reader (OCR full)

---

## 👨‍💻 About

Built by **Prashant Bhagat** — Class 11 student from Bihar, India.  
Aspiring AI/ML Engineer | Ethical Hacker | JEE 2027

[![GitHub](https://img.shields.io/badge/GitHub-pk6861172--lab-black?logo=github)](https://github.com/pk6861172-lab)

---

*"I am JARVIS — Just A Rather Very Intelligent System."*
