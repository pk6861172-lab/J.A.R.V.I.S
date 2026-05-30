#!/usr/bin/env python3
"""
J.A.R.V.I.S web/PWA bridge.

Run:
  python jarvis_web.py --host 127.0.0.1 --port 8765

For phone access on the same Wi-Fi:
  set JARVIS_WEB_TOKEN=choose-a-long-token
  python jarvis_web.py --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import argparse
import asyncio
import enum
import hmac
import json
import mimetypes
import os
import platform
import queue
import socket
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from jarvis import JARVIS, load_config
from jarvis_whatsapp_bridge import get_bridge
try:
    from jarvis_modules.elevenlabs_tts import DEFAULT_VOICE_ID, synthesize_speech
except Exception:
    DEFAULT_VOICE_ID = "HH8sIQq8WOcER3Nu118i"
    synthesize_speech = None
try:
    from jarvis import PHOTOS_DIR
except ImportError:
    PHOTOS_DIR = Path.home() / "Pictures"

import subprocess
import datetime
import base64
import uuid

_reminders = []
_esp_button_lock = threading.Lock()
_esp_button_state = {
    "last_triggered_at": 0.0,
    "last_source": "",
    "last_status": "never",
    "last_error": "",
}

# Optional local face recognition dependencies
try:
    import cv2
    import numpy as np
    FACE_LIB_AVAILABLE = True
    # initialize cascade when cv2 available
    try:
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    except Exception:
        face_cascade = None
except Exception:
    cv2 = None
    np = None
    FACE_LIB_AVAILABLE = False
    face_cascade = None

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
TASKS_FILE = BASE_DIR / "jarvis_tasks.json"
MOBILE_COMPANION_DIR = BASE_DIR / ".jarvis_runtime" / "mobile_companion"
MOBILE_TO_PHONE_DIR = MOBILE_COMPANION_DIR / "to_phone"
MOBILE_PUBLIC_VIDEOS_DIR = Path.home() / "Videos" / "JARVIS"
_system_stats_net_lock = threading.Lock()
_system_stats_net_state = {
    "time": 0.0,
    "sent": None,
    "recv": None,
}
_system_stats_gpu_cache = {
    "time": 0.0,
    "value": (0.0, 0.0),
}
_system_stats_process_cache = {
    "time": 0.0,
    "value": [],
}
_process_list_cache = {
    "time": 0.0,
    "value": [],
}
_system_stats_refresh_lock = threading.Lock()
_system_stats_gpu_refreshing = False
_system_stats_process_refreshing = False
_process_list_refreshing = False

# Legacy master passcodes are intentionally disabled. Use JARVIS_WEB_TOKEN or
# web_api_token so every install has its own secret.
MIN_WEB_TOKEN_LENGTH = 24

_jarvis: JARVIS | None = None
_jarvis_lock = threading.RLock()

FOLLOW_UP_PATTERNS = (
    "send email",
    "send mail",
    "send whatsapp",
    "send message",
    "add event",
    "create event",
    "remind me",
    "set reminder",
    "shutdown",
)


def _make_json_safe(obj):
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        if hasattr(obj, "_asdict"):
            return _make_json_safe(obj._asdict())
        return [_make_json_safe(x) for x in obj]
    elif isinstance(obj, enum.Enum):
        return obj.value
    elif hasattr(obj, "__dict__"):
        return _make_json_safe(obj.__dict__)
    elif isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    else:
        return str(obj)


def _json_bytes(payload: dict, status: int = 200) -> tuple[int, bytes]:
    safe_payload = _make_json_safe(payload)
    return status, json.dumps(safe_payload, ensure_ascii=True).encode("utf-8")


def _decode_data_url(value: str) -> tuple[bytes, str]:
    raw = str(value or "")
    if "," in raw and raw.startswith("data:"):
        header, b64 = raw.split(",", 1)
        mime = header[5:].split(";", 1)[0] or "application/octet-stream"
    else:
        b64 = raw
        mime = "application/octet-stream"
    import base64

    return base64.b64decode(b64), mime


def _write_mobile_companion_json(name: str, payload: dict) -> None:
    MOBILE_COMPANION_DIR.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body["server_received_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (MOBILE_COMPANION_DIR / name).write_text(json.dumps(_make_json_safe(body), indent=2), encoding="utf-8")


def _read_mobile_companion_json(name: str) -> dict | None:
    path = MOBILE_COMPANION_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"error": str(exc), "path": str(path)}


def _mobile_safe_rel_parts(rel: str) -> list[str]:
    safe_parts = []
    for part in str(rel or "").replace("\\", "/").split("/"):
        clean = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in part).strip()
        if clean and clean not in {".", ".."}:
            safe_parts.append(clean[:120])
    return safe_parts or ["mobile_file.bin"]


def _mobile_uploaded_file_path(rel: str) -> Path:
    files_dir = (MOBILE_COMPANION_DIR / "files").resolve()
    target = files_dir.joinpath(*_mobile_safe_rel_parts(rel)).resolve()
    if not str(target).startswith(str(files_dir)):
        raise ValueError("Invalid mobile file path")
    return target


def _read_mobile_json_list(name: str) -> list[dict]:
    data = _read_mobile_companion_json(name)
    return data if isinstance(data, list) else []


def _write_mobile_json_list(name: str, rows: list[dict]) -> None:
    MOBILE_COMPANION_DIR.mkdir(parents=True, exist_ok=True)
    (MOBILE_COMPANION_DIR / name).write_text(json.dumps(_make_json_safe(rows), indent=2), encoding="utf-8")


def _mobile_pending_file_requests() -> list[dict]:
    return [row for row in _read_mobile_json_list("pending_file_requests.json") if not row.get("completed_at")]


def _mobile_to_phone_queue(include_content: bool = False) -> list[dict]:
    rows = [row for row in _read_mobile_json_list("to_phone_queue.json") if not row.get("completed_at")]
    result = []
    for row in rows:
        item = dict(row)
        if include_content and item.get("stored_path"):
            path = Path(str(item.get("stored_path")))
            if path.exists() and path.is_file() and path.stat().st_size <= 8_500_000:
                mime = item.get("mime") or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                item["content"] = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        item.pop("stored_path", None)
        result.append(item)
    return result


def _mobile_companion_status() -> dict:
    session = _read_mobile_companion_json("session.json")
    location = _read_mobile_companion_json("latest_location.json")
    frame = _read_mobile_companion_json("latest_frame.json")
    audio = _read_mobile_companion_json("latest_audio.json")
    file_index = _read_mobile_companion_json("latest_file_index.json")
    latest_file = _read_mobile_companion_json("latest_file.json")
    latest_video = _read_mobile_companion_json("latest_video.json")

    frame_data_url = ""
    if frame and frame.get("path"):
        frame_path = Path(str(frame.get("path")))
        try:
            if frame_path.exists() and frame_path.is_file() and frame_path.stat().st_size <= 2_500_000:
                mime = frame.get("mime") or mimetypes.guess_type(str(frame_path))[0] or "image/jpeg"
                frame_data_url = f"data:{mime};base64,{base64.b64encode(frame_path.read_bytes()).decode('ascii')}"
        except Exception as exc:
            frame = dict(frame)
            frame["preview_error"] = str(exc)

    files = []
    folders = []
    if file_index and isinstance(file_index.get("files"), list):
        files = file_index.get("files", [])
    if file_index and isinstance(file_index.get("folders"), list):
        folders = file_index.get("folders", [])
    file_index_public = dict(file_index or {})
    if file_index_public:
        file_index_public["files"] = files
        file_index_public["folders"] = folders
        file_index_public["displayed_files"] = len(files)
        file_index_public["displayed_folders"] = len(folders)

    map_url = ""
    if location and location.get("latitude") is not None and location.get("longitude") is not None:
        map_url = f"https://www.google.com/maps?q={location.get('latitude')},{location.get('longitude')}"

    return {
        "ok": True,
        "available": MOBILE_COMPANION_DIR.exists(),
        "runtime_dir": str(MOBILE_COMPANION_DIR),
        "session": session,
        "location": location,
        "map_url": map_url,
        "frame": frame,
        "frame_data_url": frame_data_url,
        "audio": audio,
        "latest_video": latest_video,
        "file_index": file_index_public or None,
        "latest_file": latest_file,
        "files": files,
        "folders": folders,
        "pending_file_requests": _mobile_pending_file_requests(),
        "to_phone_queue": _mobile_to_phone_queue(False),
    }


def _local_ips() -> list[str]:
    ips = {"127.0.0.1", "::1", "localhost"}
    try:
        hostname = socket.gethostname()
        ips.add(socket.gethostbyname(hostname))
    except OSError:
        pass
    return sorted(ips)


def _wake_windows_display() -> bool:
    if platform.system().lower() != "windows":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        HWND_BROADCAST = 0xFFFF
        WM_SYSCOMMAND = 0x0112
        SC_MONITORPOWER = 0xF170
        KEYEVENTF_KEYUP = 0x0002
        VK_SHIFT = 0x10
        user32.SendMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, -1)
        user32.keybd_event(VK_SHIFT, 0, 0, 0)
        user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False


def _open_jarvis_web_surface(cfg: dict) -> bool:
    target = str(cfg.get("esp_button_open_url") or cfg.get("web_open_url") or "http://localhost:8765").strip()
    if not target:
        return False
    try:
        if platform.system().lower() == "windows":
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _process_esp_button_event(source: str) -> None:
    cfg = load_config()
    message = str(
        cfg.get(
            "esp_button_notify_text",
            "Bhai ESP button se JARVIS wake request aayi hai. Main ready hoon.",
        )
        or ""
    ).strip()
    wake_ok = _wake_windows_display()
    open_ok = _open_jarvis_web_surface(cfg) if bool(cfg.get("esp_button_open_jarvis", True)) else False
    try:
        jarvis = _get_jarvis()
        if message:
            jarvis.voice.speak(message)
    except Exception as exc:
        with _esp_button_lock:
            _esp_button_state["last_error"] = f"{type(exc).__name__}: {exc}"
    with _esp_button_lock:
        _esp_button_state.update(
            {
                "last_source": source,
                "last_status": "handled",
                "last_error": _esp_button_state.get("last_error", ""),
                "display_wake_attempted": wake_ok,
                "open_jarvis_attempted": open_ok,
            }
        )


def _esp_button_status() -> dict:
    with _esp_button_lock:
        state = dict(_esp_button_state)
    state["last_triggered"] = (
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(state.get("last_triggered_at") or 0)))
        if state.get("last_triggered_at")
        else ""
    )
    return state


def _queue_esp_button_event(source: str) -> tuple[bool, str, dict]:
    cfg = load_config()
    if not bool(cfg.get("esp_button_enabled", True)):
        return False, "ESP button trigger is disabled.", _esp_button_status()
    cooldown = float(cfg.get("esp_button_cooldown_sec", 3) or 3)
    now = time.time()
    with _esp_button_lock:
        last = float(_esp_button_state.get("last_triggered_at") or 0.0)
        if now - last < cooldown:
            _esp_button_state["last_status"] = "cooldown"
            return False, "ESP button ignored due to cooldown.", _esp_button_status()
        _esp_button_state.update(
            {
                "last_triggered_at": now,
                "last_source": source,
                "last_status": "queued",
                "last_error": "",
            }
        )
    threading.Thread(target=_process_esp_button_event, args=(source,), daemon=True).start()
    return True, "ESP button wake request queued.", _esp_button_status()


SECRET_CONFIG_KEYS = {
    "openrouter_api_key",
    "groq_api_key",
    "openweather_api_key",
    "news_api_key",
    "google_maps_api_key",
    "gemini_api_key",
    "email_password",
    "telegram_bot_token",
    "web_api_token",
}


def _has_secret(value) -> bool:
    value = str(value or "").strip()
    return bool(value and value.upper() not in {"YOUR_OPENROUTER_KEY_HERE", "YOUR_GROQ_KEY_HERE", "YOUR_API_KEY"})


def _configured_token() -> str:
    env_token = os.environ.get("JARVIS_WEB_TOKEN", "").strip()
    if env_token:
        return env_token
    try:
        cfg = load_config()
    except Exception:
        return ""
    return str(cfg.get("web_api_token", "")).strip()


def _token_is_strong(token: str) -> bool:
    token = str(token or "").strip()
    if len(token) < MIN_WEB_TOKEN_LENGTH:
        return False
    weak_values = {"jarvis", "1234", "password", "changeme", "admin", "token"}
    if token.lower() in weak_values:
        return False
    return True


def _secure_token_equal(expected: str, provided: str) -> bool:
    expected = str(expected or "").strip()
    provided = str(provided or "").strip()
    return bool(_token_is_strong(expected) and provided and hmac.compare_digest(expected, provided))


def _is_loopback(address: str) -> bool:
    return address.startswith("127.") or address == "::1" or address == "localhost"


def _origin_allowed(origin: str, host_header: str) -> bool:
    origin = str(origin or "").strip()
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    origin_host = parsed.netloc.lower()
    request_host = str(host_header or "").split(",", 1)[0].strip().lower()
    allowed = {
        request_host,
        "localhost",
        "localhost:8765",
        "127.0.0.1",
        "127.0.0.1:8765",
        "[::1]",
        "[::1]:8765",
    }
    return bool(origin_host and origin_host in allowed)


def _get_jarvis() -> JARVIS:
    global _jarvis
    with _jarvis_lock:
        if _jarvis is None:
            disable_telegram = not bool(load_config().get("web_enable_telegram_bot", False))
            old_disable = os.environ.get("JARVIS_DISABLE_TELEGRAM")
            if disable_telegram:
                os.environ["JARVIS_DISABLE_TELEGRAM"] = "1"
            try:
                _jarvis = JARVIS()
            finally:
                if disable_telegram:
                    if old_disable is None:
                        os.environ.pop("JARVIS_DISABLE_TELEGRAM", None)
                    else:
                        os.environ["JARVIS_DISABLE_TELEGRAM"] = old_disable
            _jarvis.text_mode = True
        return _jarvis


def _looks_interactive(command: str) -> bool:
    lowered = command.lower()
    return (
        lowered.strip().startswith(("/cowork ", "/computer "))
        or any(pattern in lowered for pattern in FOLLOW_UP_PATTERNS)
    )


def _looks_like_action_json(reply: str) -> bool:
    try:
        data = json.loads(str(reply or "").strip())
        return isinstance(data, dict) and str(data.get("action", "")).lower() in {
            "screenshot",
            "click",
            "type",
            "press",
            "hotkey",
            "drag",
            "wait",
        }
    except Exception:
        return False


def _run_command(command: str, speak: bool, allow_interactive: bool) -> str:
    if not command.strip():
        return "Type a command first."
    if not allow_interactive and _looks_interactive(command):
        return (
            "That command needs a follow-up prompt. Use the desktop GUI or voice mode "
            "for multi-step actions."
        )

    with _jarvis_lock:
        jarvis = _get_jarvis()
        original_speak = jarvis.voice.speak
        if not speak:
            jarvis.voice.speak = lambda _text: None
        try:
            reply = jarvis.handle(command.strip()) or ""
            if not allow_interactive and _looks_like_action_json(reply):
                return (
                    "Screen-control JSON was blocked in normal web chat. "
                    "Use /cowork before the command if you want desktop control."
                )
            return reply
        finally:
            jarvis.voice.speak = original_speak


def _load_tasks() -> list[dict]:
    try:
        if TASKS_FILE.exists():
            data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_tasks(tasks: list[dict]) -> None:
    TASKS_FILE.write_text(json.dumps(tasks, indent=2), encoding="utf-8")


def _round_gb(value: float) -> float:
    return round(float(value or 0) / (1024 ** 3), 1)


def _read_cpu_temp() -> float:
    try:
        import psutil

        temps = psutil.sensors_temperatures(fahrenheit=False) or {}
        for entries in temps.values():
            for entry in entries:
                current = getattr(entry, "current", None)
                if current is not None:
                    return float(round(current, 1))
    except Exception:
        pass
    return 0.0


def _compute_gpu_stats() -> tuple[float, float]:
    try:
        import GPUtil

        gpus = GPUtil.getGPUs()
        if not gpus:
            return 0.0, 0.0
        gpu = max(gpus, key=lambda item: float(getattr(item, "load", 0.0) or 0.0))
        gpu_percent = float(getattr(gpu, "load", 0.0) or 0.0) * 100.0
        gpu_temp = float(getattr(gpu, "temperature", 0.0) or 0.0)
        return round(gpu_percent, 1), round(gpu_temp, 1)
    except Exception:
        return 0.0, 0.0


def _refresh_gpu_stats() -> None:
    global _system_stats_gpu_refreshing
    try:
        value = _compute_gpu_stats()
        _system_stats_gpu_cache.update({"time": time.time(), "value": value})
    finally:
        with _system_stats_refresh_lock:
            _system_stats_gpu_refreshing = False


def _read_gpu_stats() -> tuple[float, float]:
    global _system_stats_gpu_refreshing
    now = time.time()
    cached_time = float(_system_stats_gpu_cache.get("time") or 0.0)
    if now - cached_time >= 8.0:
        with _system_stats_refresh_lock:
            if not _system_stats_gpu_refreshing:
                _system_stats_gpu_refreshing = True
                threading.Thread(target=_refresh_gpu_stats, daemon=True).start()
    return _system_stats_gpu_cache.get("value", (0.0, 0.0))


def _network_mbps() -> tuple[float, float]:
    try:
        import psutil

        counters = psutil.net_io_counters()
        now = time.time()
        with _system_stats_net_lock:
            last_time = float(_system_stats_net_state.get("time") or 0.0)
            last_sent = _system_stats_net_state.get("sent")
            last_recv = _system_stats_net_state.get("recv")
            _system_stats_net_state.update({
                "time": now,
                "sent": counters.bytes_sent,
                "recv": counters.bytes_recv,
            })
        if not last_time or last_sent is None or last_recv is None:
            return 0.0, 0.0
        elapsed = max(0.001, now - last_time)
        upload = max(0.0, (counters.bytes_sent - int(last_sent)) * 8 / elapsed / 1_000_000)
        download = max(0.0, (counters.bytes_recv - int(last_recv)) * 8 / elapsed / 1_000_000)
        return round(upload, 2), round(download, 2)
    except Exception:
        return 0.0, 0.0


def _compute_top_processes(limit: int = 5) -> list[dict]:
    try:
        import psutil

        rows = []
        cpu_count = max(1, int(psutil.cpu_count(logical=True) or 1))
        for proc in psutil.process_iter(["name", "cpu_percent", "memory_info"]):
            try:
                info = proc.info
                mem = info.get("memory_info")
                name = info.get("name") or f"PID {proc.pid}"
                if str(name).lower() in {"system idle process", "idle"}:
                    continue
                raw_cpu = float(info.get("cpu_percent") or 0.0)
                rows.append({
                    "name": name,
                    "cpu": round(min(100.0, raw_cpu / cpu_count), 1),
                    "ram_mb": round(float(getattr(mem, "rss", 0) or 0) / (1024 ** 2), 0),
                })
            except Exception:
                continue
        rows.sort(key=lambda item: item["cpu"], reverse=True)
        value = rows[:limit]
        _system_stats_process_cache.update({"time": time.time(), "value": value})
        return value
    except Exception:
        return []


def _refresh_top_processes() -> None:
    global _system_stats_process_refreshing
    try:
        value = _compute_top_processes(5)
        _system_stats_process_cache.update({"time": time.time(), "value": value})
    finally:
        with _system_stats_refresh_lock:
            _system_stats_process_refreshing = False


def _top_processes(limit: int = 5) -> list[dict]:
    global _system_stats_process_refreshing
    now = time.time()
    cached_time = float(_system_stats_process_cache.get("time") or 0.0)
    if now - cached_time >= 6.0:
        with _system_stats_refresh_lock:
            if not _system_stats_process_refreshing:
                _system_stats_process_refreshing = True
                threading.Thread(target=_refresh_top_processes, daemon=True).start()
    cached_value = _system_stats_process_cache.get("value") or []
    return cached_value[:limit]


def _compute_process_list(limit: int = 25) -> list[dict]:
    try:
        import psutil

        procs = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
            try:
                procs.append(proc.info)
            except Exception:
                pass
        procs.sort(key=lambda item: float(item.get("cpu_percent") or 0), reverse=True)
        return procs[:limit]
    except Exception:
        return []


def _refresh_process_list() -> None:
    global _process_list_refreshing
    try:
        value = _compute_process_list(25)
        _process_list_cache.update({"time": time.time(), "value": value})
    finally:
        with _system_stats_refresh_lock:
            _process_list_refreshing = False


def _process_list(limit: int = 25) -> list[dict]:
    global _process_list_refreshing
    now = time.time()
    cached_time = float(_process_list_cache.get("time") or 0.0)
    if now - cached_time >= 6.0:
        with _system_stats_refresh_lock:
            if not _process_list_refreshing:
                _process_list_refreshing = True
                threading.Thread(target=_refresh_process_list, daemon=True).start()
    cached_value = _process_list_cache.get("value") or []
    return cached_value[:limit]


def _system_stats_payload() -> dict:
    try:
        import psutil
    except Exception as exc:
        raise RuntimeError("psutil is required for /api/system-stats") from exc

    cpu_percent = float(psutil.cpu_percent(interval=0.1))
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home().anchor or BASE_DIR.anchor or "/"))
    battery = psutil.sensors_battery()
    gpu_percent, gpu_temp = _read_gpu_stats()
    net_upload, net_download = _network_mbps()
    battery_percent = float(getattr(battery, "percent", 0.0) or 0.0) if battery else 0.0
    battery_plugged = bool(getattr(battery, "power_plugged", False)) if battery else False

    return {
        "cpu_percent": round(cpu_percent, 1),
        "ram_percent": round(float(ram.percent or 0.0), 1),
        "ram_used_gb": _round_gb(ram.used),
        "ram_total_gb": _round_gb(ram.total),
        "disk_percent": round(float(disk.percent or 0.0), 1),
        "disk_used_gb": _round_gb(disk.used),
        "disk_total_gb": _round_gb(disk.total),
        "gpu_percent": gpu_percent,
        "gpu_temp": gpu_temp,
        "cpu_temp": _read_cpu_temp(),
        "battery_percent": round(battery_percent, 1),
        "battery_plugged": battery_plugged,
        "net_upload_mbps": net_upload,
        "net_download_mbps": net_download,
        "top_processes": _top_processes(5),
    }


def _edge_tts_audio(text: str, cfg: dict) -> tuple[bytes, str]:
    try:
        import edge_tts
    except Exception as exc:
        raise RuntimeError("edge-tts is not installed. Run: pip install edge-tts") from exc

    voice = cfg.get("edge_tts_voice", "hi-IN-MadhurNeural")

    async def _generate() -> bytes:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        path = tmp.name
        tmp.close()
        try:
            await edge_tts.Communicate(text, voice).save(path)
            return Path(path).read_bytes()
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    return asyncio.run(_generate()), "audio/mpeg"


class JarvisWebHandler(BaseHTTPRequestHandler):
    server_version = "JARVISWeb/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str = "application/json", extra_headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin", "")
        if _origin_allowed(origin, self.headers.get("Host", "")):
            self.send_header("Access-Control-Allow-Origin", origin or "http://localhost:8765")
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Jarvis-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        code, body = _json_bytes(payload, status)
        self._send(code, body)

    def _authorized(self) -> bool:
        # First check for an active session cookie
        try:
            cookie = self.headers.get("Cookie", "")
            session_id = None
            for part in cookie.split(";"):
                part = part.strip()
                if part.startswith("Jarvis-Session="):
                    session_id = part.split("=", 1)[1]
                    break
            sessions = getattr(self.server, "sessions", {})
            if session_id and session_id in sessions:
                sess = sessions.get(session_id)
                if sess and sess.get("expires", 0) > time.time():
                    return True
        except Exception:
            pass

        token = getattr(self.server, "api_token", "")
        if not _token_is_strong(token):
            return False

        auth = self.headers.get("Authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        header_token = self.headers.get("X-Jarvis-Token", "").strip()
        return _secure_token_equal(token, bearer) or _secure_token_equal(token, header_token)

    def _esp_authorized(self) -> bool:
        cfg = load_config()
        if not bool(cfg.get("esp_button_require_token", True)):
            return True
        expected = str(cfg.get("esp_button_token") or _configured_token()).strip()
        if not _token_is_strong(expected):
            return False
        parsed = urlparse(self.path)
        query_token = ""
        try:
            query_token = str(parse_qs(parsed.query).get("token", [""])[0] or "").strip()
        except Exception:
            query_token = ""
        header_token = str(
            self.headers.get("X-ESP-Token", "")
            or self.headers.get("X-Jarvis-Token", "")
            or ""
        ).strip()
        auth = self.headers.get("Authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        return any(_secure_token_equal(expected, candidate) for candidate in (query_token, header_token, bearer))

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _serve_static(self, route: str) -> None:
        if route in ("", "/"):
            route = "/index.html"
        safe = unquote(route).lstrip("/")
        target = (WEB_DIR / safe).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            self._send_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, target.read_bytes(), content_type)

    def do_OPTIONS(self) -> None:
        self._send(HTTPStatus.NO_CONTENT, b"")

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "name": "J.A.R.V.I.S",
                    "platform": platform.platform(),
                    "python": platform.python_version(),
                    "local_ips": _local_ips(),
                    "token_required": bool(getattr(self.server, "api_token", "")),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            return

        if route == "/api/esp/button/status":
            if not self._esp_authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            self._send_json({"ok": True, "esp_button": _esp_button_status()})
            return

        if route == "/api/esp/button":
            if not self._esp_authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            source = str(query.get("source", ["esp8266"])[0] or "esp8266").strip()
            queued, message, status = _queue_esp_button_event(source or self.client_address[0])
            self._send_json({"ok": True, "queued": queued, "message": message, "esp_button": status})
            return

        if route == "/api/status":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                jarvis = _get_jarvis()
                status_errors = []
                try:
                    hardware = jarvis.system.hardware_snapshot()
                except Exception as exc:
                    hardware = {"available": False, "error": str(exc)}
                    status_errors.append(f"hardware: {exc}")
                
                # Import psutil dynamically to add network statistics if available
                net_io = {}
                active_threads = threading.active_count()
                cpu_count = 1
                try:
                    import psutil as pu
                    io = pu.net_io_counters()
                    net_io = {"bytes_sent": io.bytes_sent, "bytes_recv": io.bytes_recv}
                    cpu_count = pu.cpu_count(logical=True)
                except Exception:
                    pass

                self._send_json(
                    {
                        "ok": True,
                        "hardware": hardware,
                        "network_io": net_io,
                        "threads": active_threads,
                        "cpu_count": cpu_count,
                        "location": jarvis.location.get_str(),
                        "errors": status_errors,
                    }
                )
            except Exception as exc:
                self._send_json(
                    {
                        "ok": True,
                        "degraded": True,
                        "error": str(exc),
                        "hardware": {"available": False, "error": str(exc)},
                        "network_io": {},
                        "threads": threading.active_count(),
                        "cpu_count": 1,
                        "location": "Location unavailable",
                    }
                )
            return

        if route == "/api/system-stats":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                self._send_json(_system_stats_payload())
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/whatsapp/status":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                bridge = get_bridge(_get_jarvis)
                self._send_json({"ok": True, "whatsapp": bridge.status()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/whatsapp/calls":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                bridge = get_bridge(_get_jarvis)
                self._send_json(
                    {
                        "ok": True,
                        "calls": bridge.active_calls(),
                        "whatsapp": bridge.status(),
                    }
                )
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/weather":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                jarvis = _get_jarvis()
                self._send_json({"ok": True, "weather": jarvis.weather.current()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/location":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                jarvis = _get_jarvis()
                if "refresh=1" in urlparse(self.path).query:
                    jarvis.location.refresh()
                    time.sleep(0.25)
                coords = jarvis.location.get_coords()
                self._send_json({
                    "ok": True,
                    "label": jarvis.location.get_str(),
                    "coords": coords,
                    "map_url": jarvis.location.get_map_url(),
                    "static_map_url": "",
                    "static_map_available": bool(jarvis.location.get_static_map_url()),
                    "raw": jarvis.location.get(),
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/status":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                self._send_json(_mobile_companion_status())
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/file/download":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                query = parse_qs(urlparse(self.path).query)
                rel = str(query.get("path", [""])[0] or "")
                target = _mobile_uploaded_file_path(rel)
                if not target.exists() or not target.is_file():
                    self._send_json({"ok": False, "error": "File is indexed but not uploaded to laptop yet."}, HTTPStatus.NOT_FOUND)
                    return
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                name = target.name.replace('"', "")
                self._send(
                    HTTPStatus.OK,
                    target.read_bytes(),
                    content_type,
                    {"Content-Disposition": f'attachment; filename="{name}"'},
                )
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if route == "/api/mobile/file_request/pending":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            self._send_json({"ok": True, "requests": _mobile_pending_file_requests()[:10]})
            return

        if route == "/api/mobile/to_phone/pending":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            self._send_json({"ok": True, "files": _mobile_to_phone_queue(True)[:5]})
            return

        if route == "/api/tasks":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            self._send_json({"ok": True, "tasks": _load_tasks()})
            return

        if route == "/api/news":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                jarvis = _get_jarvis()
                self._send_json({"ok": True, "news": jarvis.news.headlines()})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/features":
            # Return a list of capabilities the frontend can map to UI controls
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                jarvis = _get_jarvis()
                features = {}
                try:
                    if hasattr(jarvis, 'capabilities'):
                        features = jarvis.capabilities()
                except Exception:
                    features = {}
                if not features:
                    features = {
                        "status": True,
                        "weather": True,
                        "news": True,
                        "send_whatsapp": True,
                        "open_app": True,
                        "start_cowork": True,
                        "execute_command": True
                    }
                self._send_json({"ok": True, "features": features})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/settings":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                cfg = load_config()
                self._send_json({
                    "ok": True,
                    "config": {
                        "openrouter_api_key": "",
                        "groq_api_key": "",
                        "openweather_api_key": "",
                        "news_api_key": "",
                        "has_openrouter_api_key": _has_secret(cfg.get("openrouter_api_key", "")),
                        "has_groq_api_key": _has_secret(cfg.get("groq_api_key", "")),
                        "has_openweather_api_key": _has_secret(cfg.get("openweather_api_key", "")),
                        "has_news_api_key": _has_secret(cfg.get("news_api_key", "")),
                        "has_google_maps_api_key": _has_secret(cfg.get("google_maps_api_key", "")),
                        "has_gemini_api_key": _has_secret(cfg.get("gemini_api_key", "")),
                        "has_elevenlabs_api_key": _has_secret(os.environ.get("ELEVENLABS_API_KEY", "") or cfg.get("elevenlabs_api_key", "")),
                        "ollama_model": cfg.get("ollama_model", "llama3.2"),
                        "response_style": cfg.get("response_style", "Concise"),
                        "temperature": cfg.get("temperature", 0.7),
                        "always_listen": cfg.get("always_listen", False),
                        "camera_index": cfg.get("camera_index", 0),
                        "hud_style": cfg.get("hud_style", "mark50"),
                        "face_tracking": cfg.get("face_tracking", True),
                        "matrix_overlay": cfg.get("matrix_overlay", True),
                        "tts_rate": cfg.get("tts_rate", 172),
                        "tts_volume": cfg.get("tts_volume", 0.95),
                        "tts_backend": cfg.get("tts_backend", "elevenlabs"),
                        "edge_tts_voice": cfg.get("edge_tts_voice", "hi-IN-MadhurNeural"),
                        "elevenlabs_enabled": cfg.get("elevenlabs_enabled", True),
                        "elevenlabs_api_key": "",
                        "elevenlabs_voice_id": cfg.get("elevenlabs_voice_id", DEFAULT_VOICE_ID),
                        "elevenlabs_model_id": cfg.get("elevenlabs_model_id", "eleven_multilingual_v2"),
                        "wake_words": ", ".join(cfg.get("wake_words", ["jarvis", "hey jarvis"])),
                        "voice_mode": cfg.get("voice_mode", "auto")
                    }
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/processes":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                self._send_json({"ok": True, "processes": _process_list(25)})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/notes":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                with _jarvis_lock:
                    jarvis = _get_jarvis()
                    notes = getattr(jarvis.notes, "notes", []) or []
                self._send_json({"ok": True, "notes": notes})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/calendar":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                with _jarvis_lock:
                    jarvis = _get_jarvis()
                    events = getattr(jarvis.calendar, "events", []) or []
                self._send_json({"ok": True, "events": events})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/reminders":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                now = time.time()
                active = []
                for r in _reminders:
                    if r.get("cancelled"):
                        continue
                    remaining = int(r["end"] - now)
                    if remaining > 0:
                        active.append({
                            "text": r["text"],
                            "end": r["end"],
                            "remaining": remaining
                        })
                self._send_json({"ok": True, "reminders": active})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/security":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                with _jarvis_lock:
                    jarvis = _get_jarvis()
                    d = jarvis.location.get() if hasattr(jarvis, "location") else {}
                
                local_ip = ""
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    s.close()
                except Exception:
                    try:
                        local_ip = socket.gethostbyname(socket.gethostname())
                    except Exception:
                        local_ip = "127.0.0.1"

                conns = []
                try:
                    import psutil
                    raw_conns = psutil.net_connections(kind="inet")
                    conns = [
                        {
                            "status": c.status,
                            "local": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "-",
                            "remote": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-",
                            "pid": c.pid
                        }
                        for c in raw_conns[:25]
                    ]
                except Exception as e:
                    conns = [{"error": str(e)}]

                defender = "Defender status: unavailable on non-Windows."
                try:
                    if platform.system().lower() == "windows":
                        import subprocess
                        cmd = [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            "Get-MpComputerStatus | Select-Object -Property AntivirusEnabled,RealTimeProtectionEnabled,AntispywareEnabled,BehaviorMonitorEnabled | ConvertTo-Json -Compress",
                        ]
                        out = subprocess.check_output(cmd, text=True, timeout=5, encoding="utf-8", errors="ignore").strip()
                        data = json.loads(out) if out else {}
                        av = "ON" if data.get("AntivirusEnabled") else "OFF"
                        rtp = "ON" if data.get("RealTimeProtectionEnabled") else "OFF"
                        defender = f"Defender: AV {av} | RTP {rtp}"
                except Exception as e:
                    defender = f"Defender status unavailable: {e}"

                self._send_json({
                    "ok": True,
                    "public_ip": d.get("ip", ""),
                    "local_ip": local_ip,
                    "isp": d.get("isp", ""),
                    "location": f"{d.get('city', '')}, {d.get('region', '')}, {d.get('country', '')}",
                    "connections": conns,
                    "defender": defender
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/files":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                from pathlib import Path
                import datetime
                roots = [Path.home() / "Desktop", Path.home() / "Downloads", Path.home() / "Documents"]
                items = []
                for r in roots:
                    if not r.exists():
                        continue
                    try:
                        for p in r.glob("*"):
                            if p.is_file():
                                items.append({
                                    "name": p.name,
                                    "path": str(p),
                                    "mtime": p.stat().st_mtime,
                                    "mtime_str": datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
                                })
                    except Exception:
                        continue
                items.sort(key=lambda x: x["mtime"], reverse=True)
                self._send_json({"ok": True, "recent_files": items[:25]})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._serve_static(route)

    def do_POST(self) -> None:
        route = urlparse(self.path).path

        if route == "/api/esp/button":
            if not self._esp_authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                source = str(payload.get("source") or self.client_address[0] or "esp8266").strip()
                queued, message, status = _queue_esp_button_event(source)
                self._send_json({"ok": True, "queued": queued, "message": message, "esp_button": status})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/session":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                status = str(payload.get("status") or "unknown").strip().lower()
                if status not in {"connected", "disconnected", "paused", "unknown"}:
                    self._send_json({"ok": False, "error": "Invalid mobile session status"}, HTTPStatus.BAD_REQUEST)
                    return
                previous = _read_mobile_companion_json("session.json") or {}
                def keep_value(key: str):
                    value = payload.get(key)
                    return previous.get(key) if value is None else value
                _write_mobile_companion_json("session.json", {
                    "status": status,
                    "client": self.client_address[0],
                    "connected_at": payload.get("connected_at"),
                    "disconnected_at": payload.get("disconnected_at"),
                    "app_build": keep_value("app_build"),
                    "video_status": keep_value("video_status"),
                    "video_error": keep_value("video_error"),
                    "video_back": keep_value("video_back"),
                    "video_front": keep_value("video_front"),
                })
                self._send_json({"ok": True, "status": status})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/location":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                lat = float(payload.get("latitude"))
                lon = float(payload.get("longitude"))
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    self._send_json({"ok": False, "error": "Invalid coordinates"}, HTTPStatus.BAD_REQUEST)
                    return
                _write_mobile_companion_json("latest_location.json", {
                    "latitude": lat,
                    "longitude": lon,
                    "accuracy_m": payload.get("accuracy_m"),
                    "altitude_m": payload.get("altitude_m"),
                    "speed_mps": payload.get("speed_mps"),
                    "heading_deg": payload.get("heading_deg"),
                    "captured_at": payload.get("captured_at"),
                    "client": self.client_address[0],
                })
                self._send_json({"ok": True})
            except (TypeError, ValueError):
                self._send_json({"ok": False, "error": "latitude and longitude are required"}, HTTPStatus.BAD_REQUEST)
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/frame":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                img_bytes, mime = _decode_data_url(str(payload.get("image") or ""))
                if not img_bytes or len(img_bytes) > 2_500_000:
                    self._send_json({"ok": False, "error": "Invalid or oversized frame"}, HTTPStatus.BAD_REQUEST)
                    return
                MOBILE_COMPANION_DIR.mkdir(parents=True, exist_ok=True)
                suffix = ".jpg" if "jpeg" in mime or "jpg" in mime else ".bin"
                frame_path = MOBILE_COMPANION_DIR / f"latest_frame{suffix}"
                frame_path.write_bytes(img_bytes)
                _write_mobile_companion_json("latest_frame.json", {
                    "path": str(frame_path),
                    "mime": mime,
                    "bytes": len(img_bytes),
                    "width": payload.get("width"),
                    "height": payload.get("height"),
                    "captured_at": payload.get("captured_at"),
                    "client": self.client_address[0],
                })
                self._send_json({"ok": True, "bytes": len(img_bytes)})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/audio":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                audio_bytes, mime = _decode_data_url(str(payload.get("audio") or ""))
                if not audio_bytes or len(audio_bytes) > 3_500_000:
                    self._send_json({"ok": False, "error": "Invalid or oversized audio chunk"}, HTTPStatus.BAD_REQUEST)
                    return
                MOBILE_COMPANION_DIR.mkdir(parents=True, exist_ok=True)
                suffix = ".webm" if "webm" in mime else ".bin"
                audio_path = MOBILE_COMPANION_DIR / f"latest_audio{suffix}"
                audio_path.write_bytes(audio_bytes)
                _write_mobile_companion_json("latest_audio.json", {
                    "path": str(audio_path),
                    "mime": mime,
                    "bytes": len(audio_bytes),
                    "captured_at": payload.get("captured_at"),
                    "client": self.client_address[0],
                })
                self._send_json({"ok": True, "bytes": len(audio_bytes)})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/video":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                video_bytes, mime = _decode_data_url(str(payload.get("video") or ""))
                if not video_bytes or len(video_bytes) > 250_000_000:
                    self._send_json({"ok": False, "error": "Invalid or oversized video"}, HTTPStatus.BAD_REQUEST)
                    return
                camera = str(payload.get("camera") or "unknown").strip().lower()
                if camera not in {"front", "back", "unknown"}:
                    camera = "unknown"
                MOBILE_COMPANION_DIR.mkdir(parents=True, exist_ok=True)
                videos_dir = MOBILE_COMPANION_DIR / "videos"
                videos_dir.mkdir(parents=True, exist_ok=True)
                safe_stamp = time.strftime("%Y%m%d_%H%M%S")
                suffix = ".mp4" if "mp4" in mime or "mpeg" in mime else ".webm" if "webm" in mime else ".bin"
                video_path = videos_dir / f"{camera}_{safe_stamp}{suffix}"
                video_path.write_bytes(video_bytes)
                public_path = None
                try:
                    MOBILE_PUBLIC_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
                    public_path = MOBILE_PUBLIC_VIDEOS_DIR / video_path.name
                    public_path.write_bytes(video_bytes)
                except Exception:
                    public_path = None
                meta = {
                    "path": str(video_path),
                    "public_path": str(public_path) if public_path else "",
                    "camera": camera,
                    "mime": mime,
                    "bytes": len(video_bytes),
                    "started_at": payload.get("started_at"),
                    "finished_at": payload.get("finished_at"),
                    "duration_ms": payload.get("duration_ms"),
                    "width": payload.get("width"),
                    "height": payload.get("height"),
                    "client": self.client_address[0],
                }
                _write_mobile_companion_json(f"latest_video_{camera}.json", meta)
                _write_mobile_companion_json("latest_video.json", meta)
                self._send_json({
                    "ok": True,
                    "path": str(video_path),
                    "public_path": str(public_path) if public_path else "",
                    "bytes": len(video_bytes),
                })
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/file_request":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                rel = str(payload.get("path") or payload.get("relative_path") or "").strip()
                if not rel:
                    self._send_json({"ok": False, "error": "path is required"}, HTTPStatus.BAD_REQUEST)
                    return
                request_id = str(uuid.uuid4())
                rows = _mobile_pending_file_requests()
                if not any(str(row.get("relative_path")) == rel for row in rows):
                    rows.append({
                        "id": request_id,
                        "relative_path": rel,
                        "requested_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    _write_mobile_json_list("pending_file_requests.json", rows)
                self._send_json({"ok": True, "queued": True, "requests": rows})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/file_request/ack":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                req_id = str(payload.get("id") or "").strip()
                rel = str(payload.get("relative_path") or "").strip()
                rows = _read_mobile_json_list("pending_file_requests.json")
                changed = False
                for row in rows:
                    if (req_id and row.get("id") == req_id) or (rel and row.get("relative_path") == rel):
                        row["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        row["status"] = str(payload.get("status") or "done")
                        row["message"] = str(payload.get("message") or "")
                        changed = True
                if changed:
                    _write_mobile_json_list("pending_file_requests.json", rows)
                self._send_json({"ok": True, "changed": changed})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/to_phone":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                content, mime = _decode_data_url(str(payload.get("content") or ""))
                if not content or len(content) > 8_500_000:
                    self._send_json({"ok": False, "error": "Invalid or oversized upload"}, HTTPStatus.BAD_REQUEST)
                    return
                rel = str(payload.get("name") or payload.get("relative_path") or "jarvis_upload.bin")
                safe_parts = _mobile_safe_rel_parts(rel)
                queue_id = str(uuid.uuid4())
                MOBILE_TO_PHONE_DIR.mkdir(parents=True, exist_ok=True)
                target = (MOBILE_TO_PHONE_DIR / f"{queue_id}_{safe_parts[-1]}").resolve()
                if not str(target).startswith(str(MOBILE_TO_PHONE_DIR.resolve())):
                    self._send_json({"ok": False, "error": "Invalid upload path"}, HTTPStatus.BAD_REQUEST)
                    return
                target.write_bytes(content)
                rows = _read_mobile_json_list("to_phone_queue.json")
                item = {
                    "id": queue_id,
                    "name": safe_parts[-1],
                    "relative_path": "/".join(safe_parts),
                    "target_dir": "/".join(_mobile_safe_rel_parts(payload.get("target_dir") or "Download/JARVIS Inbox")),
                    "bytes": len(content),
                    "mime": mime,
                    "stored_path": str(target),
                    "queued_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                rows.append(item)
                _write_mobile_json_list("to_phone_queue.json", rows)
                public_item = dict(item)
                public_item.pop("stored_path", None)
                self._send_json({"ok": True, "file": public_item})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/to_phone/ack":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                queue_id = str(payload.get("id") or "").strip()
                rows = _read_mobile_json_list("to_phone_queue.json")
                changed = False
                for row in rows:
                    if queue_id and row.get("id") == queue_id:
                        row["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        row["status"] = str(payload.get("status") or "saved")
                        row["message"] = str(payload.get("message") or "")
                        changed = True
                if changed:
                    _write_mobile_json_list("to_phone_queue.json", rows)
                self._send_json({"ok": True, "changed": changed})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/file_index":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                files = payload.get("files")
                if not isinstance(files, list):
                    self._send_json({"ok": False, "error": "files list is required"}, HTTPStatus.BAD_REQUEST)
                    return
                _write_mobile_companion_json("latest_file_index.json", {
                    "indexed_at": payload.get("indexed_at"),
                    "root": payload.get("root"),
                    "file_count": payload.get("file_count"),
                    "folder_count": payload.get("folder_count"),
                    "uploaded_recent_files": payload.get("uploaded_recent_files"),
                    "folders": payload.get("folders") if isinstance(payload.get("folders"), list) else [],
                    "files": files,
                    "client": self.client_address[0],
                })
                self._send_json({"ok": True, "indexed": len(files)})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/mobile/file":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                content, mime = _decode_data_url(str(payload.get("content") or ""))
                if not content or len(content) > 8_500_000:
                    self._send_json({"ok": False, "error": "Invalid or oversized file"}, HTTPStatus.BAD_REQUEST)
                    return
                rel = str(payload.get("relative_path") or payload.get("name") or "mobile_file.bin")
                safe_parts = []
                for part in rel.replace("\\", "/").split("/"):
                    clean = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in part).strip()
                    if clean and clean not in {".", ".."}:
                        safe_parts.append(clean[:120])
                if not safe_parts:
                    safe_parts = ["mobile_file.bin"]
                files_dir = MOBILE_COMPANION_DIR / "files"
                target = (files_dir.joinpath(*safe_parts)).resolve()
                if not str(target).startswith(str(files_dir.resolve())):
                    self._send_json({"ok": False, "error": "Invalid file path"}, HTTPStatus.BAD_REQUEST)
                    return
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                _write_mobile_companion_json("latest_file.json", {
                    "path": str(target),
                    "relative_path": "/".join(safe_parts),
                    "mime": mime,
                    "bytes": len(content),
                    "modified_at": payload.get("modified_at"),
                    "client": self.client_address[0],
                })
                rows = _read_mobile_json_list("pending_file_requests.json")
                changed = False
                safe_rel = "/".join(safe_parts)
                for row in rows:
                    if not row.get("completed_at") and row.get("relative_path") == safe_rel:
                        row["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        row["status"] = "uploaded"
                        changed = True
                if changed:
                    _write_mobile_json_list("pending_file_requests.json", rows)
                self._send_json({"ok": True, "path": str(target), "bytes": len(content)})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/whatsapp/incoming":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                cfg = load_config()
                if not bool(cfg.get("whatsapp_bridge_enabled", False)):
                    self._send_json({"ok": False, "error": "WhatsApp bridge is disabled."}, HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                event_type = str(payload.get("event_type") or "message").strip().lower()
                sender_id = str(payload.get("from") or "").strip()
                message = str(payload.get("message") or "").strip()
                if event_type == "call":
                    if not sender_id or not str(payload.get("id") or "").strip():
                        self._send_json({"ok": False, "error": "Both sender and call id are required."}, HTTPStatus.BAD_REQUEST)
                        return
                    if bool(cfg.get("whatsapp_bridge_call_ignore_groups", True)) and bool(payload.get("is_group", False)):
                        self._send_json({"ok": True, "ignored": True, "reason": "group_call"})
                        return
                elif not sender_id or not message:
                    self._send_json({"ok": False, "error": "Both sender and message are required."}, HTTPStatus.BAD_REQUEST)
                    return
                if bool(cfg.get("whatsapp_bridge_ignore_groups", True)) and "@g.us" in sender_id:
                    self._send_json({"ok": True, "ignored": True, "reason": "group"})
                    return
                bridge = get_bridge(_get_jarvis)
                queued = bridge.enqueue(payload)
                self._send_json({"ok": True, "queued": queued})
            except queue.Full:
                self._send_json({"ok": False, "error": "WhatsApp bridge queue is full."}, HTTPStatus.TOO_MANY_REQUESTS)
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route in ("/api/whatsapp/mode", "/api/whatsapp/online", "/api/whatsapp/offline"):
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                if route == "/api/whatsapp/online":
                    mode = "notify_only"
                elif route == "/api/whatsapp/offline":
                    mode = "ask_first"
                else:
                    payload = self._read_json()
                    mode = str(payload.get("mode", "ask_first") or "ask_first")
                bridge = get_bridge(_get_jarvis)
                self._send_json({"ok": True, "mode": bridge.set_mode(mode), "whatsapp": bridge.status()})
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/whatsapp/calls/action":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                bridge = get_bridge(_get_jarvis)
                result = bridge.handle_call_action(
                    str(payload.get("call_id") or payload.get("id") or ""),
                    str(payload.get("action") or ""),
                    str(payload.get("text") or payload.get("message") or ""),
                )
                status = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_GATEWAY
                self._send_json(result, status)
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/camera_process":
            try:
                payload = self._read_json()
                image_data = payload.get("image")  # data URL
                face_tracking = bool(payload.get("face_tracking", True))
                
                if not image_data:
                    self._send_json({"ok": False, "error": "No image data"}, HTTPStatus.BAD_REQUEST)
                    return
                
                faces_data = []
                if FACE_LIB_AVAILABLE:
                    # Decode base64 image
                    header, b64 = image_data.split(',', 1) if ',' in image_data else (None, image_data)
                    import base64
                    img_bytes = base64.b64decode(b64)
                    arr = np.frombuffer(img_bytes, np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    
                    if img is not None:
                        family_faces = []
                        if face_tracking:
                            try:
                                jarvis = _get_jarvis()
                                recognizer = getattr(jarvis, "family_faces", None)
                                if recognizer:
                                    family_faces = recognizer.identify_bgr(img, max_faces=5)
                            except Exception as exc:
                                print(f"[WebFaceRec] family recognition unavailable: {exc}")

                        if family_faces:
                            for face in family_faces:
                                x = int(face.get("x", 0))
                                y = int(face.get("y", 0))
                                w = int(face.get("w", 0))
                                h = int(face.get("h", 0))
                                # Estimate distance and threat level
                                img_h, img_w = img.shape[:2]
                                rel = max(1.0, (w * h) / float(img_w * img_h))
                                distance_m = max(0.4, min(6.0, 1.6 / (rel ** 0.5)))
                                threat = "LOW" if distance_m > 2.5 else "MED" if distance_m > 1.4 else "HIGH"
                                
                                faces_data.append({
                                    "x": int(x),
                                    "y": int(y),
                                    "w": int(w),
                                    "h": int(h),
                                    "name": str(face.get("name") or "UNKNOWN"),
                                    "recognized": bool(face.get("recognized")),
                                    "threat": threat,
                                    "distance": round(distance_m, 2),
                                    "match_score": face.get("distance_score")
                                })
                        else:
                            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                            if face_cascade is not None:
                                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
                                for idx, (x, y, w, h) in enumerate(faces[:3]):
                                    img_h, img_w = img.shape[:2]
                                    rel = max(1.0, (w * h) / float(img_w * img_h))
                                    distance_m = max(0.4, min(6.0, 1.6 / (rel ** 0.5)))
                                    threat = "LOW" if distance_m > 2.5 else "MED" if distance_m > 1.4 else "HIGH"

                                    faces_data.append({
                                        "x": int(x),
                                        "y": int(y),
                                        "w": int(w),
                                        "h": int(h),
                                        "name": "UNKNOWN",
                                        "recognized": False,
                                        "threat": threat,
                                        "distance": round(distance_m, 2)
                                    })
                
                self._send_json({
                    "ok": True, 
                    "faces": faces_data,
                    "face_lib_available": FACE_LIB_AVAILABLE
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        # Authentication endpoint for the web client to validate tokens/passcodes
        if route == "/api/auth":
            try:
                payload = self._read_json()
                provided = str(payload.get("token", "")).strip()
                face_flag = bool(payload.get("face", False))
                image_data = payload.get("image")  # optional data URL
                save_template = bool(payload.get("save_template", False))
                token = getattr(self.server, "api_token", "")

                if save_template and image_data:
                    if not self._authorized():
                        self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                        return
                    try:
                        import base64
                        owner_dir = BASE_DIR / "owner_faces"
                        owner_dir.mkdir(exist_ok=True)
                        _header, b64 = image_data.split(",", 1) if "," in image_data else ("", image_data)
                        path = owner_dir / f"web_template_{int(time.time())}.jpg"
                        path.write_bytes(base64.b64decode(b64))
                        self._send_json({"ok": True, "message": "Face template saved.", "path": str(path)})
                        return
                    except Exception as exc:
                        self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                        return

                ok = False
                # Accept if provided matches configured server token
                if _secure_token_equal(token, provided):
                    ok = True
                # If an image is provided, attempt server-side recognition
                elif image_data and FACE_LIB_AVAILABLE:
                    def _recognize_image(dataurl: str) -> bool:
                        try:
                            header, b64 = dataurl.split(',', 1) if ',' in dataurl else (None, dataurl)
                            import base64
                            img_bytes = base64.b64decode(b64)
                            arr = np.frombuffer(img_bytes, np.uint8)
                            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if img is None:
                                return False
                            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                            if face_cascade is not None:
                                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
                                if len(faces) > 0:
                                    x, y, w, h = faces[0]
                                    roi = gray[y:y+h, x:x+w]
                                else:
                                    roi = cv2.resize(gray, (100, 100))
                            else:
                                roi = cv2.resize(gray, (100, 100))
                            roi = cv2.resize(roi, (100, 100))

                            # Load owner templates
                            templates = []
                            owner_dir = BASE_DIR / 'owner_faces'
                            if owner_dir.exists():
                                for p in owner_dir.iterdir():
                                    if p.suffix.lower() in ('.jpg', '.jpeg', '.png'):
                                        try:
                                            timg = cv2.imread(str(p))
                                            tgray = cv2.cvtColor(timg, cv2.COLOR_BGR2GRAY)
                                            if face_cascade is not None:
                                                tf = face_cascade.detectMultiScale(tgray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
                                                if len(tf) > 0:
                                                    x2, y2, w2, h2 = tf[0]
                                                    troi = tgray[y2:y2+h2, x2:x2+w2]
                                                else:
                                                    troi = cv2.resize(tgray, (100, 100))
                                            else:
                                                troi = cv2.resize(tgray, (100, 100))
                                            troi = cv2.resize(troi, (100, 100))
                                            templates.append(troi)
                                        except Exception:
                                            continue

                            if not templates:
                                return False

                            # Compare with simple MSE threshold
                            for t in templates:
                                try:
                                    mse = float(np.mean((t.astype('float32') - roi.astype('float32')) ** 2))
                                    if mse < 2000.0:
                                        return True
                                except Exception:
                                    continue
                            return False
                        except Exception:
                            return False

                    if _recognize_image(image_data):
                        ok = True

                if ok:
                    # Create a short-lived session cookie
                    session_id = str(uuid.uuid4())
                    expires = time.time() + 3600  # 1 hour
                    if not hasattr(self.server, 'sessions'):
                        self.server.sessions = {}
                    self.server.sessions[session_id] = {"created": time.time(), "expires": expires}

                    body = json.dumps({"ok": True, "token_required": bool(token)}).encode('utf-8')
                    cookie = f"Jarvis-Session={session_id}; HttpOnly; Path=/; Max-Age=3600"
                    self._send(HTTPStatus.OK, body, "application/json", extra_headers={"Set-Cookie": cookie})
                    return
                else:
                    self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/settings":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                cfg_path = BASE_DIR / "jarvis_config.json"
                if cfg_path.exists():
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                else:
                    cfg = {}

                for secret_key in ("openrouter_api_key", "groq_api_key", "openweather_api_key", "news_api_key", "elevenlabs_api_key"):
                    if secret_key in payload:
                        submitted = str(payload.get(secret_key, "") or "").strip()
                        if submitted:
                            cfg[secret_key] = submitted
                cfg["ollama_model"] = payload.get("ollama_model", cfg.get("ollama_model", "llama3.2"))
                cfg["response_style"] = payload.get("response_style", cfg.get("response_style", "Concise"))
                cfg["temperature"] = float(payload.get("temperature", cfg.get("temperature", 0.7)))
                cfg["always_listen"] = bool(payload.get("always_listen", cfg.get("always_listen", False)))
                cfg["camera_index"] = int(payload.get("camera_index", cfg.get("camera_index", 0)))
                cfg["hud_style"] = payload.get("hud_style", cfg.get("hud_style", "mark50"))
                cfg["face_tracking"] = bool(payload.get("face_tracking", cfg.get("face_tracking", True)))
                cfg["matrix_overlay"] = bool(payload.get("matrix_overlay", cfg.get("matrix_overlay", True)))
                cfg["tts_rate"] = int(payload.get("tts_rate", cfg.get("tts_rate", 172)))
                cfg["tts_volume"] = float(payload.get("tts_volume", cfg.get("tts_volume", 0.95)))
                cfg["tts_backend"] = payload.get("tts_backend", cfg.get("tts_backend", "elevenlabs"))
                cfg["edge_tts_voice"] = payload.get("edge_tts_voice", cfg.get("edge_tts_voice", "hi-IN-MadhurNeural"))
                cfg["elevenlabs_enabled"] = bool(payload.get("elevenlabs_enabled", cfg.get("elevenlabs_enabled", True)))
                cfg["elevenlabs_voice_id"] = payload.get("elevenlabs_voice_id", cfg.get("elevenlabs_voice_id", DEFAULT_VOICE_ID))
                cfg["elevenlabs_model_id"] = payload.get("elevenlabs_model_id", cfg.get("elevenlabs_model_id", "eleven_multilingual_v2"))
                
                ww = payload.get("wake_words", "")
                if ww:
                    cfg["wake_words"] = [w.strip() for w in ww.split(",") if w.strip()]

                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2)

                with _jarvis_lock:
                    jarvis = _get_jarvis()
                    if hasattr(jarvis, "load_config"):
                        jarvis.load_config()
                    try:
                        jarvis.voice.engine.setProperty('rate', cfg["tts_rate"])
                        jarvis.voice.engine.setProperty('volume', cfg["tts_volume"])
                    except Exception:
                        pass
                self._send_json({"ok": True, "message": "Settings updated successfully."})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/tts":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                text = str(payload.get("text", "") or "").strip()
                if not text:
                    self._send_json({"ok": False, "error": "Text required."}, HTTPStatus.BAD_REQUEST)
                    return
                cfg = load_config()
                backend = str(cfg.get("tts_backend", "edge_tts")).lower()
                if backend == "edge_tts":
                    audio, content_type = _edge_tts_audio(text, cfg)
                else:
                    if not synthesize_speech:
                        self._send_json({"ok": False, "error": "ElevenLabs TTS module unavailable."}, HTTPStatus.INTERNAL_SERVER_ERROR)
                        return
                    audio, content_type = synthesize_speech(text, cfg)
                self._send(HTTPStatus.OK, audio, content_type)
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/processes":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                pid = int(payload.get("pid", 0))
                if pid:
                    import psutil
                    psutil.Process(pid).terminate()
                    self._send_json({"ok": True, "message": f"Terminated process PID {pid}"})
                else:
                    self._send_json({"ok": False, "error": "Invalid PID"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/notes":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                action = payload.get("action", "add")
                if action == "add":
                    content = str(payload.get("content", "")).strip()
                    if content:
                        with _jarvis_lock:
                            jarvis = _get_jarvis()
                            reply = jarvis.notes.add(content)
                        self._send_json({"ok": True, "message": reply})
                    else:
                        self._send_json({"ok": False, "error": "Content cannot be empty"}, HTTPStatus.BAD_REQUEST)
                elif action == "delete":
                    idx = int(payload.get("index", -1))
                    with _jarvis_lock:
                        jarvis = _get_jarvis()
                        notes = getattr(jarvis.notes, "notes", []) or []
                        if 0 <= idx < len(notes):
                            notes.pop(idx)
                            jarvis.notes._save()
                            self._send_json({"ok": True, "message": "Note deleted successfully."})
                        else:
                            self._send_json({"ok": False, "error": "Invalid index"}, HTTPStatus.BAD_REQUEST)
                else:
                    self._send_json({"ok": False, "error": "Invalid action"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/calendar":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                action = payload.get("action", "add")
                if action == "add":
                    title = str(payload.get("title", "")).strip()
                    date = str(payload.get("date", "")).strip()
                    time_str = str(payload.get("time", "00:00")).strip()
                    if title and date:
                        with _jarvis_lock:
                            jarvis = _get_jarvis()
                            reply = jarvis.calendar.add(title, date, time_str)
                        self._send_json({"ok": True, "message": reply})
                    else:
                        self._send_json({"ok": False, "error": "Title and date required"}, HTTPStatus.BAD_REQUEST)
                elif action == "delete":
                    idx = int(payload.get("index", -1))
                    with _jarvis_lock:
                        jarvis = _get_jarvis()
                        events = getattr(jarvis.calendar, "events", []) or []
                        if 0 <= idx < len(events):
                            events.pop(idx)
                            jarvis.calendar._save()
                            self._send_json({"ok": True, "message": "Event deleted successfully."})
                        else:
                            self._send_json({"ok": False, "error": "Invalid index"}, HTTPStatus.BAD_REQUEST)
                else:
                    self._send_json({"ok": False, "error": "Invalid action"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/reminders":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                action = payload.get("action", "set")
                if action == "set":
                    text = str(payload.get("text", "")).strip()
                    mins = int(payload.get("minutes", 5))
                    if text:
                        end = time.time() + mins * 60
                        _reminders.append({"text": text, "end": end, "cancelled": False})
                        self._send_json({"ok": True, "message": f"Reminder set: {text} ({mins} min)"})
                    else:
                        self._send_json({"ok": False, "error": "Reminder text required"}, HTTPStatus.BAD_REQUEST)
                elif action == "cancel":
                    idx = int(payload.get("index", -1))
                    if 0 <= idx < len(_reminders):
                        _reminders[idx]["cancelled"] = True
                        self._send_json({"ok": True, "message": "Reminder cancelled."})
                    else:
                        self._send_json({"ok": False, "error": "Invalid index"}, HTTPStatus.BAD_REQUEST)
                else:
                    self._send_json({"ok": False, "error": "Invalid action"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/tasks":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                action = str(payload.get("action", "add")).strip().lower()
                tasks = _load_tasks()
                if action == "add":
                    text = str(payload.get("text", "")).strip()
                    if not text:
                        self._send_json({"ok": False, "error": "Task text required"}, HTTPStatus.BAD_REQUEST)
                        return
                    tasks.append({
                        "text": text,
                        "done": False,
                        "created": datetime.datetime.now().isoformat(timespec="seconds"),
                    })
                elif action == "toggle":
                    idx = int(payload.get("index", -1))
                    if not 0 <= idx < len(tasks):
                        self._send_json({"ok": False, "error": "Invalid index"}, HTTPStatus.BAD_REQUEST)
                        return
                    tasks[idx]["done"] = not bool(tasks[idx].get("done"))
                elif action == "delete":
                    idx = int(payload.get("index", -1))
                    if not 0 <= idx < len(tasks):
                        self._send_json({"ok": False, "error": "Invalid index"}, HTTPStatus.BAD_REQUEST)
                        return
                    tasks.pop(idx)
                else:
                    self._send_json({"ok": False, "error": "Invalid action"}, HTTPStatus.BAD_REQUEST)
                    return
                _save_tasks(tasks)
                self._send_json({"ok": True, "tasks": tasks})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/security":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                action = payload.get("action", "ping")
                if action == "ping":
                    import subprocess
                    out = subprocess.check_output(["ping", "-n", "1", "google.com"], text=True, timeout=4, encoding="utf-8", errors="ignore")
                    self._send_json({"ok": True, "output": out})
                elif action == "port_scan":
                    import socket
                    open_ports = []
                    ports = [80, 443, 3389, 8080, 8765]
                    for p in ports:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(0.3)
                        res = s.connect_ex(("127.0.0.1", p))
                        if res == 0:
                            open_ports.append(p)
                        s.close()
                    self._send_json({"ok": True, "open_ports": open_ports})
                else:
                    self._send_json({"ok": False, "error": "Invalid action"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route == "/api/files":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                payload = self._read_json()
                action = payload.get("action", "open")
                path_str = payload.get("path", "")
                if action == "open" and path_str:
                    from pathlib import Path
                    path = Path(path_str)
                    if path_str == "desktop":
                        path = Path.home() / "Desktop"
                    elif path_str == "downloads":
                        path = Path.home() / "Downloads"
                    elif path_str == "documents":
                        path = Path.home() / "Documents"
                    elif path_str == "photos":
                        path = PHOTOS_DIR

                    import os
                    os.startfile(str(path))
                    self._send_json({"ok": True, "message": f"Opened {path.name}"})
                else:
                    self._send_json({"ok": False, "error": "Path required"}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if route != "/api/command":
            self._send_json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        if not self._authorized():
            self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return

        try:
            payload = self._read_json()
            command = str(payload.get("command", "")).strip()
            speak = bool(payload.get("speak", False))
            allow_interactive = bool(payload.get("allow_interactive", False))
            reply = _run_command(command, speak=speak, allow_interactive=allow_interactive)
            self._send_json({"ok": True, "command": command, "reply": reply})
        except json.JSONDecodeError:
            self._send_json({"ok": False, "error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S web/PWA bridge")
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 for LAN/mobile access")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    token = _configured_token()
    if token and not _token_is_strong(token):
        print(
            f"[SECURITY] Ignoring weak web token. Use at least {MIN_WEB_TOKEN_LENGTH} characters "
            "via JARVIS_WEB_TOKEN or web_api_token."
        )
        token = ""
    server = ThreadingHTTPServer((args.host, args.port), JarvisWebHandler)
    server.api_token = token
    # Simple in-memory session store for authenticated web clients
    server.sessions = {}

    # Warm JARVIS in the background so Telegram polling starts immediately.
    threading.Thread(target=_get_jarvis, daemon=True).start()
    try:
        get_bridge(_get_jarvis)
    except Exception as exc:
        print(f"[WARN] WhatsApp bridge failed to initialize: {exc}")

    url_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    print(f"J.A.R.V.I.S web interface: http://{url_host}:{args.port}")
    if args.host == "0.0.0.0":
        print(f"LAN addresses: {', '.join(_local_ips())}")
        if not token:
            print("Remote API commands and login are blocked until a strong JARVIS_WEB_TOKEN or web_api_token is set.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping J.A.R.V.I.S web bridge...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
