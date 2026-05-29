# Remote Android Access With Ngrok

Use this when you want the JARVIS Android app to connect from anywhere, even when the phone and laptop are not on the same Wi-Fi.

## What Must Stay Running

Your laptop must be:

- Powered on
- Connected to the internet
- Not asleep
- Running JARVIS web
- Running Ngrok

The phone connects like this:

```text
Android app -> HTTPS Ngrok URL -> laptop JARVIS web server
```

## One-Time Ngrok Setup

Ngrok requires a verified account and authtoken.

1. Create/login to Ngrok.
2. Copy your authtoken from the Ngrok dashboard.
3. Run this from the project folder:

```powershell
.\scripts\start_remote_access.ps1 -NgrokAuthtoken "PASTE_YOUR_NGROK_AUTHTOKEN_HERE"
```

After the first time, you can run:

```powershell
.\scripts\start_remote_access.ps1
```

## Android App Settings

The script prints:

```text
Server URL: https://....ngrok-free.app
API token : ....
```

Put those two values into the Android app settings.

## Stop Remote Access

```powershell
.\scripts\stop_remote_access.ps1
```

## Notes

- Free Ngrok URLs can change after restart.
- Keep the API token private.
- `.jarvis_runtime/web_token.txt` is local-only and ignored by Git.
