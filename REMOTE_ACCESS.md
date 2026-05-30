# Remote Android Access

Use this when you want the JARVIS Android app to connect from anywhere, even when the phone and laptop are not on the same Wi-Fi.

## What Must Stay Running

Your laptop must be:

- Powered on
- Connected to the internet
- Not asleep
- Running JARVIS web
- Running a tunnel

The phone connects like this:

```text
Android app -> HTTPS tunnel URL -> laptop JARVIS web server
```

## Recommended: Cloudflare Quick Tunnel

Cloudflare Quick Tunnel is the recommended free ngrok alternative for quick remote testing. It does not need a Cloudflare account or domain.

Install cloudflared once:

```powershell
winget install --id Cloudflare.cloudflared -e
```

Start normal JARVIS remote access:

```powershell
.\scripts\start_cloudflare_remote_access.ps1
```

Start Shreya JARVIS remote access:

```powershell
.\scripts\start_cloudflare_remote_access.ps1 -Shreya
```

The script prints:

```text
Server URL: https://....trycloudflare.com
API token : ....
```

Put those two values into the Android app settings.

Quick Tunnel URLs can change after restart. If the URL changes, update the app settings or rebuild the APK with the new default URL.

## Stop Remote Access

```powershell
.\scripts\stop_remote_access.ps1
```

## Older Option: Ngrok

Ngrok is still available through the older script, but free accounts can hit monthly limits.

One-time setup:

```powershell
.\scripts\start_remote_access.ps1 -NgrokAuthtoken "PASTE_YOUR_NGROK_AUTHTOKEN_HERE"
```

After the first time:

```powershell
.\scripts\start_remote_access.ps1
```

## Notes

- Keep the API token private.
- `.jarvis_runtime/web_token.txt` is local-only and ignored by Git.
- Cloudflare Quick Tunnel is remote/public HTTPS, but it is temporary.
- For a fixed permanent URL later, use Cloudflare Named Tunnel with a Cloudflare account/domain.
