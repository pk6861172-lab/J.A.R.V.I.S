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
import json
import mimetypes
import os
import platform
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from jarvis import JARVIS, load_config


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"

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


def _json_bytes(payload: dict, status: int = 200) -> tuple[int, bytes]:
    return status, json.dumps(payload, ensure_ascii=True).encode("utf-8")


def _local_ips() -> list[str]:
    ips = {"127.0.0.1", "::1", "localhost"}
    try:
        hostname = socket.gethostname()
        ips.add(socket.gethostbyname(hostname))
    except OSError:
        pass
    return sorted(ips)


def _configured_token() -> str:
    env_token = os.environ.get("JARVIS_WEB_TOKEN", "").strip()
    if env_token:
        return env_token
    try:
        cfg = load_config()
    except Exception:
        return ""
    return str(cfg.get("web_api_token", "")).strip()


def _is_loopback(address: str) -> bool:
    return address.startswith("127.") or address == "::1" or address == "localhost"


def _get_jarvis() -> JARVIS:
    global _jarvis
    with _jarvis_lock:
        if _jarvis is None:
            _jarvis = JARVIS()
            _jarvis.text_mode = True
        return _jarvis


def _looks_interactive(command: str) -> bool:
    lowered = command.lower()
    return any(pattern in lowered for pattern in FOLLOW_UP_PATTERNS)


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
            return jarvis.handle(command.strip()) or ""
        finally:
            jarvis.voice.speak = original_speak


class JarvisWebHandler(BaseHTTPRequestHandler):
    server_version = "JARVISWeb/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Jarvis-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        code, body = _json_bytes(payload, status)
        self._send(code, body)

    def _authorized(self) -> bool:
        token = getattr(self.server, "api_token", "")
        if not token and _is_loopback(self.client_address[0]):
            return True
        if not token:
            return False

        auth = self.headers.get("Authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        header_token = self.headers.get("X-Jarvis-Token", "").strip()
        return token in (bearer, header_token)

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

        if route == "/api/status":
            if not self._authorized():
                self._send_json({"ok": False, "error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            try:
                jarvis = _get_jarvis()
                self._send_json(
                    {
                        "ok": True,
                        "hardware": jarvis.system.hardware_snapshot(),
                        "location": jarvis.location.get_str(),
                    }
                )
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self._serve_static(route)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
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
    server = ThreadingHTTPServer((args.host, args.port), JarvisWebHandler)
    server.api_token = token

    url_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    print(f"J.A.R.V.I.S web interface: http://{url_host}:{args.port}")
    if args.host == "0.0.0.0":
        print(f"LAN addresses: {', '.join(_local_ips())}")
        if not token:
            print("Remote API commands are blocked until JARVIS_WEB_TOKEN or web_api_token is set.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping J.A.R.V.I.S web bridge...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
