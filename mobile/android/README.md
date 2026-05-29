# JARVIS Mobile Android

This folder now contains a clean Android WebView companion app for JARVIS.

## What It Does

- Loads the premium glassmorphic mobile UI from local WebView assets.
- Stores the PC server URL and API token locally on the phone.
- Sends commands to the laptop JARVIS brain through `jarvis_web.py`.
- Supports Android speech input, Android TTS, dashboard stats, quick actions, and image upload.
- Supports an explicit live companion mode for camera frames, microphone audio chunks, and location updates.
- Keeps existing APKs under `bin/` untouched.

## PC Setup

Run the web bridge on the laptop so the phone can reach it on the same Wi-Fi:

```powershell
$env:JARVIS_WEB_TOKEN="choose-a-long-token"
python jarvis_web.py --host 0.0.0.0 --port 8765
```

Then open the APK and set:

```text
Server URL: http://YOUR-PC-LAN-IP:8765
API token:  the same JARVIS_WEB_TOKEN
```

## Ngrok / HTTPS Companion Mode

For remote access, expose the laptop server through an HTTPS Ngrok URL and enter that URL in the app settings:

```text
Server URL: https://your-ngrok-url.ngrok-free.app
API token:  the same JARVIS_WEB_TOKEN
```

Live companion mode is transparent:

- The user taps **Grant permissions** and Android shows normal permission dialogs.
- The user taps **Connect live** before camera, microphone, or location sharing starts.
- Android starts a foreground service with a permanent notification: **JARVIS companion is live**.
- If the app is left in Recents or moved away from, sharing can continue through that visible foreground service.
- The app shows a visible **Connected/Disconnected** status.
- The user can tap **Disconnect** in the app or notification to stop camera, microphone, frame sending, and location watching.
- No hidden background service is used; Android always shows the live-sharing notification.

### Optional Full File Access

File system sync is separate from camera/microphone/location sharing:

- Tap **All files access** in the app.
- Android settings opens. Manually allow JARVIS under **All files access**.
- Return to JARVIS and tap **File sync ON**.
- File sync runs only while the foreground companion service is live.
- The laptop receives a file index plus a few recent small files.
- Tap **File sync OFF**, **Disconnect**, or the notification **Disconnect** action to stop it.

The app scans common user-owned roots such as Downloads, DCIM, Documents, Pictures, Movies, Music, and WhatsApp Media. It does not silently run without the foreground notification.

The laptop receives latest snapshots under:

```text
.jarvis_runtime/mobile_companion/
```

That folder is local runtime data and is ignored by Git.

## Custom Opening Video

Put your video at:

```text
mobile/android/app/src/main/assets/mobile/assets/intro.mp4
```

If `intro.mp4` is missing, the app uses the built-in animated intro.

## Build

Open `mobile/android` in Android Studio and build the `app` module, or use Gradle if installed:

```bash
gradle assembleDebug
```

The old Buildozer APKs in `bin/` remain unchanged.
