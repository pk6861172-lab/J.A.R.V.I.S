#!/usr/bin/env python3
"""
J.A.R.V.I.S GUI v3.0

Modern HUD-style desktop interface for the existing JARVIS backend.
Features:
- real-time embedded camera feed
- capture live frame and use it as an AI reference image
- attach files and folders as context for AI chat
- attach project files with one click
- multimodal prompts routed through the existing OpenRouter backend
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
import math
import platform
import random
import re
import threading
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, scrolledtext, ttk, messagebox, simpledialog
import json
import socket
import subprocess
import calendar as pycalendar

try:
    import numpy as np
except Exception:
    np = None

try:
    import sounddevice as sd
    SD_OK = True
except Exception:
    sd = None
    SD_OK = False

try:
    from PIL import Image, ImageOps, ImageTk
    PIL_OK = True
except Exception:
    PIL_OK = False

try:
    from jarvis import Intent, JARVIS, PHOTOS_DIR, psutil, cv2, LocationModule
except ImportError as e:
    print(f"[!] Could not import jarvis.py: {e}")
    print("[!] Make sure jarvis_gui.py is in the same folder as jarvis.py")
    raise SystemExit(1)


BG = "#030608"
BG_PANEL = "#081018"
BG_PANEL_ALT = "#0b1118"
BG_INPUT = "#0a131c"
GOLD = "#FFB800"
GOLD_SOFT = "#d99c00"
GOLD_DIM = "#6b4b08"
CYAN = "#00D4FF"
CYAN_SOFT = "#00a8cc"
CYAN_DIM = "#0e4d63"
GREEN = GOLD
ORANGE = "#ff8d2a"
RED = "#FF2020"
RED_SOFT = "#b91515"
TEXT = "#f7e8bf"
TEXT_DIM = "#aa9062"
TEXT_FAINT = "#695844"
BORDER = "#3a2317"
GLOW = "#181108"

BUTTON_STYLES = {
    "primary": {
        "bg": GOLD,
        "fg": BG,
        "activebackground": GOLD_SOFT,
        "activeforeground": BG,
        "border": GOLD_DIM,
    },
    "danger": {
        "bg": RED,
        "fg": "#fff2ee",
        "activebackground": RED_SOFT,
        "activeforeground": "#fff2ee",
        "border": "#7d1313",
    },
    "arc": {
        "bg": CYAN,
        "fg": BG,
        "activebackground": CYAN_SOFT,
        "activeforeground": BG,
        "border": CYAN_DIM,
    },
    "ghost": {
        "bg": BG_INPUT,
        "fg": GOLD,
        "activebackground": "#171f27",
        "activeforeground": GOLD,
        "border": BORDER,
    },
}

# ── Iron Man Neon Suit Fonts ───────────────────────────────────
# Orbitron  → titles, headers, HUD labels  (futuristic Iron Man)
# Exo 2     → body text, chat, descriptions (premium sci-fi)
# JetBrains Mono → system data, code, metrics (hacker terminal)

FONT_ORBITRON  = "Orbitron"
FONT_EXO       = "Exo 2"
FONT_MONO      = "JetBrains Mono"

FONT_UI        = (FONT_EXO,      11)
FONT_SMALL     = (FONT_EXO,       9)
FONT_TITLE     = (FONT_ORBITRON, 10, "bold")
FONT_BIG       = (FONT_ORBITRON, 15, "bold")
FONT_HUGE      = (FONT_ORBITRON, 22, "bold")
FONT_MONO_SM   = (FONT_MONO,      9)
FONT_MONO_MD   = (FONT_MONO,     10)
FONT_CHAT      = (FONT_EXO,      10)
FONT_LABEL     = (FONT_EXO,       9)
FONT_METRIC    = (FONT_MONO,      9)
FONT_INPUT     = (FONT_EXO,      11)
FONT_BTN       = (FONT_ORBITRON,  9, "bold")

CAMERA_SIZE = (320, 196)
REFERENCE_SIZE = (360, 220)
DEFAULT_MAP_PREVIEW_PATH = Path(__file__).resolve().parent / "assets" / "map_preview.png"
VOICE_GREEN = "#00ff6a"


class VisionMode:
    MARK50 = "mark50"
    THERMAL = "thermal"
    TRON = "tron"
    PREDATOR = "predator"
    NEURAL = "neural"

    LABELS = {
        MARK50: "MARK 50",
        THERMAL: "THERMAL",
        TRON: "TRON",
        PREDATOR: "PREDATOR",
        NEURAL: "NEURAL",
    }

    ORDER = [MARK50, THERMAL, TRON, PREDATOR, NEURAL]


@dataclass(frozen=True)
class ActivityEvent:
    ts: datetime.datetime
    kind: str
    message: str


class ToastManager:
    STYLES = {
        "info": {"border": CYAN, "fg": TEXT, "bg": BG_PANEL_ALT},
        "success": {"border": GOLD, "fg": TEXT, "bg": BG_PANEL_ALT},
        "warning": {"border": ORANGE, "fg": TEXT, "bg": BG_PANEL_ALT},
        "alert": {"border": RED, "fg": "#fff2ee", "bg": BG_PANEL_ALT},
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.active: list[tk.Toplevel] = []
        self._lock = threading.Lock()

    def show(self, message: str, style: str = "info", duration_ms: int = 3000):
        msg = " ".join(str(message or "").split())
        if not msg:
            return
        palette = self.STYLES.get(style, self.STYLES["info"])

        def create():
            toast = tk.Toplevel(self.root)
            toast.withdraw()
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            try:
                toast.attributes("-alpha", 0.0)
            except Exception:
                pass

            body = tk.Frame(toast, bg=palette["bg"], highlightthickness=1, highlightbackground=palette["border"])
            body.pack(fill="both", expand=True)
            tk.Frame(body, bg=palette["border"], height=2).pack(fill="x", side="top")

            inner = tk.Frame(body, bg=palette["bg"])
            inner.pack(fill="both", expand=True, padx=10, pady=8)
            label = tk.Label(inner, text=msg, fg=palette["fg"], bg=palette["bg"], font=FONT_SMALL, justify="left", wraplength=320)
            label.pack(anchor="w")

            # Position (stack top-right)
            self.root.update_idletasks()
            toast.update_idletasks()
            tw = max(220, toast.winfo_reqwidth())
            th = max(52, toast.winfo_reqheight())

            x = self.root.winfo_rootx() + self.root.winfo_width() - tw - 24
            y0 = self.root.winfo_rooty() + 24
            with self._lock:
                y = y0 + sum(t.winfo_height() + 10 for t in self.active if t.winfo_exists())
                self.active.append(toast)

            # Slide-in from the right
            start_x = x + 40
            toast.geometry(f"{tw}x{th}+{start_x}+{y}")
            toast.deiconify()

            steps = 10
            def animate_in(step=0):
                if not toast.winfo_exists():
                    return
                t = step / steps
                cur_x = int(start_x + (x - start_x) * t)
                try:
                    toast.attributes("-alpha", min(1.0, t))
                except Exception:
                    pass
                toast.geometry(f"{tw}x{th}+{cur_x}+{y}")
                if step < steps:
                    toast.after(16, lambda: animate_in(step + 1))
                else:
                    toast.after(duration_ms, animate_out)

            def animate_out(step=0):
                if not toast.winfo_exists():
                    return
                t = step / steps
                cur_x = int(x + (x + 40 - x) * t)
                try:
                    toast.attributes("-alpha", max(0.0, 1.0 - t))
                except Exception:
                    pass
                toast.geometry(f"{tw}x{th}+{cur_x}+{y}")
                if step < steps:
                    toast.after(16, lambda: animate_out(step + 1))
                else:
                    self._destroy_toast(toast)

            animate_in()

        self.root.after(0, create)

    def _destroy_toast(self, toast: tk.Toplevel):
        try:
            toast.destroy()
        except Exception:
            pass
        with self._lock:
            self.active = [t for t in self.active if t.winfo_exists()]


class AudioMeter:
    """Best-effort RMS meter for mic and loopback (Windows)."""

    def __init__(self):
        self._level = 0.0
        self._stream = None
        self._lock = threading.Lock()
        self._last_update = time.time()

    def get_level(self) -> float:
        with self._lock:
            lvl = float(self._level)
            # decay if no recent updates
            age = time.time() - self._last_update
            if age > 0.25:
                lvl *= max(0.0, 1.0 - (age - 0.25) * 2.0)
            return max(0.0, min(1.0, lvl))

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
        self._stream = None

    def start_mic(self, device=None):
        if not SD_OK:
            return False
        self.stop()

        def cb(indata, _frames, _time, _status):
            try:
                if np is None:
                    return
                mono = indata.astype(np.float32)
                rms = float(np.sqrt(np.mean(mono * mono) + 1e-9))
                lvl = min(1.0, rms * 6.0)
                with self._lock:
                    self._level = lvl
                    self._last_update = time.time()
            except Exception:
                pass

        try:
            self._stream = sd.InputStream(
                channels=1,
                callback=cb,
                device=device,
                samplerate=16000,
                blocksize=512,
            )
            self._stream.start()
            return True
        except Exception:
            self._stream = None
            return False

    def start_loopback(self):
        """Attempt WASAPI loopback for speaker output (best-effort)."""
        if not (SD_OK and hasattr(sd, "WasapiSettings")):
            return False

        self.stop()

        # Some sounddevice builds don't accept the "loopback" kwarg.
        extra = None
        try:
            import inspect

            sig = inspect.signature(sd.WasapiSettings)
            if "loopback" in sig.parameters:
                extra = sd.WasapiSettings(loopback=True)
        except TypeError:
            # If signature introspection fails, fall back to a guarded call.
            try:
                extra = sd.WasapiSettings(loopback=True)
            except TypeError:
                extra = None
        except Exception:
            extra = None

        def cb(indata, _frames, _time, _status):
            try:
                if np is None:
                    return
                mono = indata.astype(np.float32)
                rms = float(np.sqrt(np.mean(mono * mono) + 1e-9))
                lvl = min(1.0, rms * 6.0)
                with self._lock:
                    self._level = lvl
                    self._last_update = time.time()
            except Exception:
                pass

        try:
            self._stream = sd.InputStream(
                channels=1,
                callback=cb,
                samplerate=16000,
                blocksize=512,
                extra_settings=extra,
            )
            self._stream.start()
            return True
        except Exception:
            self._stream = None
            return False


class AudioAnalyzer:
    """RMS + FFT analyzer (best-effort) for a live audio stream."""

    def __init__(self, mode: str):
        self.mode = mode  # "mic" | "loopback"
        self._stream = None
        self._lock = threading.Lock()
        self._level = 0.0
        self._last_update = time.time()
        self._ring = deque(maxlen=4096)
        self._sr = 16000

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
        self._stream = None

    def start(self) -> bool:
        if not (SD_OK and np is not None):
            return False
        self.stop()

        extra = None
        if self.mode == "loopback" and hasattr(sd, "WasapiSettings"):
            # Some sounddevice builds don't accept the "loopback" kwarg.
            try:
                import inspect

                sig = inspect.signature(sd.WasapiSettings)
                if "loopback" in sig.parameters:
                    extra = sd.WasapiSettings(loopback=True)
            except TypeError:
                try:
                    extra = sd.WasapiSettings(loopback=True)
                except TypeError:
                    extra = None
            except Exception:
                extra = None

        def cb(indata, _frames, _time, _status):
            try:
                mono = indata[:, 0].astype(np.float32)
                rms = float(np.sqrt(np.mean(mono * mono) + 1e-9))
                lvl = min(1.0, rms * 8.0)
                with self._lock:
                    self._level = lvl
                    self._last_update = time.time()
                    # store last samples for FFT/waveform
                    self._ring.extend(mono.tolist())
            except Exception:
                pass

        try:
            self._stream = sd.InputStream(
                channels=1,
                callback=cb,
                samplerate=self._sr,
                blocksize=512,
                extra_settings=extra,
            )
            self._stream.start()
            return True
        except Exception:
            self._stream = None
            return False

    def level(self) -> float:
        with self._lock:
            lvl = float(self._level)
            age = time.time() - self._last_update
            if age > 0.2:
                lvl *= max(0.0, 1.0 - (age - 0.2) * 2.5)
            return max(0.0, min(1.0, lvl))

    def fft_bands(self, bands: int = 40) -> list[float]:
        if np is None:
            return [0.0] * bands
        with self._lock:
            samples = list(self._ring)[-2048:]
        if len(samples) < 256:
            return [0.0] * bands
        x = np.array(samples, dtype=np.float32)
        x = x - float(np.mean(x))
        win = np.hanning(len(x)).astype(np.float32)
        x = x * win
        spec = np.abs(np.fft.rfft(x))
        # log-spaced bands from ~60Hz..(sr/2)
        freqs = np.fft.rfftfreq(len(x), d=1.0 / self._sr)
        fmin, fmax = 60.0, float(self._sr / 2)
        edges = np.geomspace(fmin, fmax, num=bands + 1)
        out = []
        for i in range(bands):
            lo, hi = edges[i], edges[i + 1]
            idx = np.where((freqs >= lo) & (freqs < hi))[0]
            if idx.size == 0:
                out.append(0.0)
                continue
            v = float(np.mean(spec[idx]))
            out.append(v)
        # normalize with soft knee
        mx = max(out) if out else 1.0
        if mx <= 1e-9:
            return [0.0] * bands
        norm = [min(1.0, (v / mx) ** 0.6) for v in out]
        return norm

    def waveform(self, points: int = 256) -> list[float]:
        if np is None:
            return [0.0] * points
        with self._lock:
            samples = list(self._ring)[-points:]
        if len(samples) < points:
            samples = ([0.0] * (points - len(samples))) + samples
        mx = max(1e-6, float(max(abs(s) for s in samples)))
        return [float(s) / mx for s in samples]


class LineChart(tk.Canvas):
    def __init__(self, parent, title: str, color: str = CYAN, height: int = 90, max_points: int = 60):
        super().__init__(parent, bg=BG_INPUT, height=height, highlightthickness=1, highlightbackground=BORDER, bd=0)
        self.title = title
        self.color = color
        self.max_points = max_points
        self.values: deque[float] = deque(maxlen=max_points)
        self._label = tk.Label(parent, text=title, fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL)

    def pack_with_label(self, **kwargs):
        self._label.pack(anchor="w", pady=(0, 4))
        self.pack(**kwargs)

    def push(self, value: float):
        try:
            self.values.append(float(value))
        except Exception:
            self.values.append(0.0)
        self._draw()

    def _draw(self):
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        if w <= 2 or h <= 2:
            self.after(50, self._draw)
            return
        self.delete("all")

        # grid
        for gx in range(0, w, 40):
            self.create_line(gx, 0, gx, h, fill=GLOW, width=1)
        for gy in range(0, h, 24):
            self.create_line(0, gy, w, gy, fill=GLOW, width=1)

        vals = list(self.values)
        if not vals:
            self.create_text(8, 8, anchor="nw", text="Awaiting data…", fill=TEXT_FAINT, font=FONT_SMALL)
            return

        vmin = min(vals)
        vmax = max(vals)
        if vmax - vmin < 1e-6:
            vmax = vmin + 1.0
        pad = 8
        xs = []
        ys = []
        for i, v in enumerate(vals):
            x = int(pad + (i / max(1, len(vals) - 1)) * (w - 2 * pad))
            t = (v - vmin) / (vmax - vmin)
            y = int((h - pad) - t * (h - 2 * pad))
            xs.append(x)
            ys.append(y)

        pts = []
        for x, y in zip(xs, ys):
            pts.extend([x, y])
        if len(pts) >= 4:
            self.create_line(*pts, fill=self.color, width=2)

        cur = vals[-1]
        self.create_text(w - 8, 8, anchor="ne", text=f"{cur:.1f}", fill=self.color, font=("JetBrains Mono", 9, "bold"))


def apply_button_style(button: tk.Button, style: str = "ghost") -> tk.Button:
    palette = BUTTON_STYLES.get(style, BUTTON_STYLES["ghost"])
    button.configure(
        bg=palette["bg"],
        fg=palette["fg"],
        activebackground=palette["activebackground"],
        activeforeground=palette["activeforeground"],
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=palette["border"],
        highlightcolor=palette["border"],
        disabledforeground=TEXT_FAINT,
        cursor="hand2",
    )
    button._hud_style = style
    return button


def enhance_hud_button(button: tk.Button):
    """Adds hover glow + click pulse to standard tk.Button."""
    try:
        base_style = getattr(button, "_hud_style", "ghost")
        palette = BUTTON_STYLES.get(base_style, BUTTON_STYLES["ghost"])

        def on_enter(_e=None):
            button.configure(highlightthickness=2, highlightbackground=GOLD, highlightcolor=GOLD)
            try:
                button.configure(bg=palette["activebackground"])
            except Exception:
                pass

        def on_leave(_e=None):
            button.configure(highlightthickness=1, highlightbackground=palette["border"], highlightcolor=palette["border"])
            try:
                button.configure(bg=palette["bg"])
            except Exception:
                pass

        def on_press(_e=None):
            # quick pulse
            try:
                button.configure(bg=GOLD_SOFT)
            except Exception:
                pass
            button.after(120, lambda: on_enter())

        button.bind("<Enter>", on_enter, add="+")
        button.bind("<Leave>", on_leave, add="+")
        button.bind("<ButtonPress-1>", on_press, add="+")
    except Exception:
        pass


def human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def short_path(path: str | Path, max_len: int = 56) -> str:
    text = str(path)
    if len(text) <= max_len:
        return text
    return "..." + text[-(max_len - 3):]


class HudCard(tk.Frame):
    def __init__(self, parent, title: str, subtitle: str = ""):
        super().__init__(parent, bg=BG_PANEL, highlightthickness=1, highlightbackground=BORDER)
        self.columnconfigure(0, weight=1)

        tk.Frame(self, bg=GOLD, height=2).grid(row=0, column=0, sticky="ew")

        header = tk.Frame(self, bg=BG_PANEL)
        header.grid(row=1, column=0, sticky="ew", padx=14, pady=(12, 8))
        header.columnconfigure(1, weight=1)

        tk.Label(
            header,
            text="◈",
            fg=GOLD,
            bg=BG_PANEL,
            font=("Orbitron", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        tk.Label(
            header,
            text=title,
            fg=GOLD,
            bg=BG_PANEL,
            font=FONT_TITLE,
        ).grid(row=0, column=1, sticky="w")

        if subtitle:
            tk.Label(
                header,
                text=subtitle,
                fg=TEXT_FAINT,
                bg=BG_PANEL,
                font=FONT_SMALL,
            ).grid(row=1, column=1, sticky="w", pady=(2, 0))

        body = tk.Frame(self, bg=BG_PANEL)
        body.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self.rowconfigure(2, weight=1)
        self.body = body


class MetricBar(tk.Frame):
    def __init__(self, parent, label: str, color: str):
        super().__init__(parent, bg=BG_PANEL)
        self.base_color = color

        top = tk.Frame(self, bg=BG_PANEL)
        top.pack(fill="x")
        tk.Label(top, text=label, fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).pack(side="left")
        self.value_label = tk.Label(top, text="0%", fg=color, bg=BG_PANEL, font=FONT_SMALL)
        self.value_label.pack(side="right")

        self.rail = tk.Frame(self, bg=GLOW, height=8)
        self.rail.pack(fill="x", pady=(4, 0))
        self.rail.pack_propagate(False)

        self.fill = tk.Frame(self.rail, bg=color, width=0)
        self.fill.place(x=0, y=0, relheight=1.0)

    def update(self, pct: float):
        pct = max(0.0, min(100.0, pct))
        rail_width = max(1, self.rail.winfo_width())
        width = int((pct / 100.0) * rail_width)
        color = RED if pct >= 85 else ORANGE if pct >= 60 else self.base_color
        self.fill.place_configure(width=width)
        self.fill.configure(bg=color)
        self.value_label.configure(text=f"{pct:.0f}%", fg=color)


class ScrollColumn(tk.Frame):
    def __init__(self, parent, width: int = 320):
        super().__init__(parent, bg=BG, width=width, highlightthickness=0, bd=0)
        self.pack_propagate(False)
        self._mousewheel_bound = False

        self.canvas = tk.Canvas(
            self,
            bg=BG,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            troughcolor=BG,
            bg=BG_INPUT,
            activebackground=CYAN_DIM,
            relief="flat",
            bd=0,
            width=10,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.content = tk.Frame(self.canvas, bg=BG)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self.content.bind("<Enter>", self._bind_mousewheel)
        self.content.bind("<Leave>", self._unbind_mousewheel)

    def _on_content_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event):
        if event.delta:
            direction = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(direction, "units")
        elif getattr(event, "num", None) == 4:
            self.canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            self.canvas.yview_scroll(1, "units")
        return "break"

    def _bind_mousewheel(self, _event=None):
        if self._mousewheel_bound:
            return
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)
        self._mousewheel_bound = True

    def _unbind_mousewheel(self, _event=None):
        if not self._mousewheel_bound:
            return
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")
        self._mousewheel_bound = False


class JarvisOrb(tk.Canvas):
    def __init__(self, parent, size: int = 320):
        super().__init__(
            parent,
            width=size,
            height=size,
            bg=BG_PANEL,
            highlightthickness=0,
        )
        self.size = size
        self.angle = 0
        self.pulse = 0
        self.active = False
        self.listening = False
        self.thinking = False
        self.speaking = False
        self.error_flash_until = 0.0
        self.signal_pct = None  # 0..100
        self.satellites: list[str] = []
        self.phase = 0
        self._animate()

    def set_active(self, active: bool):
        self.active = active

    def set_listening(self, listening: bool):
        self.listening = listening
        self.active = listening

    def set_thinking(self, thinking: bool):
        self.thinking = thinking
        if thinking:
            self.active = True

    def set_speaking(self, speaking: bool):
        self.speaking = speaking
        if speaking:
            self.active = True

    def flash_error(self, duration_s: float = 1.2):
        self.error_flash_until = time.time() + max(0.2, float(duration_s))

    def set_signal(self, pct: int | None):
        self.signal_pct = pct

    def set_satellites(self, items: list[str]):
        self.satellites = list(items or [])[:4]

    def _draw(self):
        self.delete("all")
        c = self.size // 2
        spin = self.angle
        pulse = (self.pulse + 1) / 8.0
        glow_r = 26 + (pulse * 8)
        now = time.time()
        if now < self.error_flash_until:
            outer_color = RED
            inner_color = RED_SOFT
            core_color = RED
        elif self.listening:
            outer_color = VOICE_GREEN
            inner_color = VOICE_GREEN
            core_color = VOICE_GREEN
        elif self.thinking:
            outer_color = "#a855f7"
            inner_color = "#7c3aed"
            core_color = "#c084fc"
        elif self.speaking:
            outer_color = GOLD
            inner_color = GOLD_SOFT
            core_color = GOLD
        else:
            outer_color = CYAN if self.active or self.listening else CYAN_SOFT
            inner_color = GOLD if self.listening else GOLD_SOFT
            core_color = CYAN if self.active or self.listening else "#49c8dc"

        self.create_oval(12, 12, self.size - 12, self.size - 12, outline="#0a2231", width=2)
        self.create_oval(20, 20, self.size - 20, self.size - 20, outline=BORDER, width=2)
        self.create_arc(18, 18, self.size - 18, self.size - 18, start=205 + spin, extent=72, style="arc", outline=outer_color, width=12)
        self.create_arc(18, 18, self.size - 18, self.size - 18, start=292 + spin, extent=96, style="arc", outline="#107aa0", width=12)
        self.create_arc(18, 18, self.size - 18, self.size - 18, start=88 + spin, extent=54, style="arc", outline="#0a6f95", width=12)
        self.create_arc(28, 28, self.size - 28, self.size - 28, start=22 - spin, extent=122, style="arc", outline=outer_color, width=3)
        self.create_arc(28, 28, self.size - 28, self.size - 28, start=176 - spin, extent=94, style="arc", outline="#0d6b8f", width=3)

        # Live signal strength ring (outermost)
        if isinstance(self.signal_pct, (int, float)):
            pct = max(0.0, min(100.0, float(self.signal_pct)))
            extent = 360.0 * (pct / 100.0)
            self.create_arc(
                10, 10, self.size - 10, self.size - 10,
                start=90, extent=-extent,
                style="arc",
                outline=outer_color,
                width=4,
            )

        for start in range(130, 294, 14):
            self.create_arc(
                56,
                56,
                self.size - 56,
                self.size - 56,
                start=start + int(spin * 0.2),
                extent=9,
                style="arc",
                outline=GOLD,
                width=12,
            )

        self.create_arc(56, 56, self.size - 56, self.size - 56, start=132 + int(spin * 0.2), extent=162, style="arc", outline=GOLD_DIM, width=14)
        self.create_arc(70, 70, self.size - 70, self.size - 70, start=200 - spin, extent=132, style="arc", outline=outer_color, width=4)
        self.create_arc(70, 70, self.size - 70, self.size - 70, start=26 - spin, extent=108, style="arc", outline="#0a83ae", width=4)

        for tick in range(48):
            angle = math.radians((tick * 7.5) + spin)
            inner = 90 if tick % 2 == 0 else 96
            outer = 108 if tick % 2 == 0 else 112
            x1 = c + math.cos(angle) * inner
            y1 = c + math.sin(angle) * inner
            x2 = c + math.cos(angle) * outer
            y2 = c + math.sin(angle) * outer
            tick_color = GOLD if tick % 6 == 0 else outer_color
            self.create_line(x1, y1, x2, y2, fill=tick_color, width=2 if tick % 6 == 0 else 1)

        for radius, color, width in ((84, outer_color, 3), (66, "#107ba1", 2), (50, GOLD_DIM, 2), (36, "#0b3443", 1)):
            self.create_oval(c - radius, c - radius, c + radius, c + radius, outline=color, width=width)

        for ring in range(3):
            radius = 74 - (ring * 12)
            self.create_arc(
                c - radius,
                c - radius,
                c + radius,
                c + radius,
                start=18 + ring * 18 + spin,
                extent=132 - ring * 18,
                style="arc",
                outline=outer_color if ring != 1 else GOLD,
                width=2,
            )

        self.create_oval(c - glow_r, c - glow_r, c + glow_r, c + glow_r, fill=CYAN_DIM, outline="")
        self.create_oval(c - 24, c - 24, c + 24, c + 24, outline=outer_color, width=2)
        self.create_oval(c - 12, c - 12, c + 12, c + 12, fill=core_color, outline="")
        self.create_polygon(
            c, c - 18,
            c + 18, c + 12,
            c - 18, c + 12,
            outline="#b8ffff",
            fill="",
            width=3,
        )
        self.create_polygon(
            c, c - 10,
            c + 10, c + 6,
            c - 10, c + 6,
            outline="#d8ffff",
            fill="",
            width=1,
        )

        self.create_text(c, 34, text="SIGNAL", fill=outer_color, font=("Orbitron", 10, "bold"))
        self.create_text(44, c, text="WIFI", fill=GOLD, font=("Orbitron", 10, "bold"), angle=90)
        self.create_text(c, self.size - 40, text="ENERGY LEVEL", fill=GOLD, font=("Orbitron", 12, "bold"))

        label = "LISTENING" if self.listening else "SPEAKING" if self.speaking else "THINKING" if self.thinking else "PROCESSING" if self.active else "STANDBY"
        self.create_text(c, c + 104, text=label, fill=TEXT, font=("Orbitron", 9, "bold"))

        if self.thinking:
            # Orbiting dots like electrons
            for i in range(8):
                ang = math.radians((spin * 3) + i * 45)
                r = 120 + (i % 2) * 10
                x = c + int(math.cos(ang) * r)
                y = c + int(math.sin(ang) * r)
                self.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#d8b4fe", outline="")

        # Orbiting data satellites (mini-stats)
        if self.satellites:
            for i, text in enumerate(self.satellites[:4]):
                ang = math.radians((spin * 1.2) + i * (360 / max(1, len(self.satellites))))
                r = 148
                x = c + int(math.cos(ang) * r)
                y = c + int(math.sin(ang) * r)
                self.create_oval(x - 4, y - 4, x + 4, y + 4, fill=outer_color, outline="")
                self.create_text(x, y - 12, text=str(text), fill=TEXT_DIM, font=("JetBrains Mono", 7))

    def _animate(self):
        speed = 10 if self.listening else 9 if self.thinking else 5 if self.speaking else 4 if self.active or self.listening else 1
        self.angle = (self.angle + speed) % 360
        self.phase = (self.phase + 1) % 5
        self.pulse = (self.pulse + 1) % 8
        self._draw()
        self.after(40, self._animate)


class JARVISGui:
    def __init__(self, root: tk.Tk, jarvis: JARVIS):
        self.root = root
        self.jarvis = jarvis
        self.cfg = jarvis.cfg
        self.name = self.cfg.get("user_name", "Prashant")

        self.command_history: list[str] = []
        self.command_index = -1
        self.attached_files: list[str] = []
        self.reference_image_path: str | None = None
        self.current_frame = None
        self.current_overlay_frame = None
        self._last_faces = []
        self._cam_fc = 0
        self.current_preview_image = None
        self.reference_preview_image = None
        self.weather_last_text = "Weather pending."
        self.news_last_text = "News pending."
        self.radar_blips: list[dict] = []
        self.radar_angle = 0.0
        self.radar_prev_small = None
        self.radar_motion_hits = 0
        self.radar_status = tk.StringVar(value="Radar standby. Start camera to scan movement.")
        self.activity_events: deque[ActivityEvent] = deque(maxlen=800)
        self._activity_widget = None
        self.toasts = ToastManager(root)
        self._audio_state = "idle"  # idle | mic | tts
        self._audio_vis_mode = "spectrum"  # spectrum | bars | wave
        self._audio_wake_until = 0.0
        self._audio_level = 0.0
        self._audio_meter = None
        self._mic_analyzer = None
        self._tts_analyzer = None
        self._thinking_job = None
        self._thinking_started = None
        self.session_started_at = datetime.datetime.now()
        self.stats = {
            "commands_today": 0,
            "ai_queries": 0,
            "photos_taken": 0,
            "voice_activations": 0,
        }
        self._net_prev = None
        self._diskio_prev = None
        self._analytics_job = None
        self._wifi_job = None
        self._calendar_job = None
        self._wifi_signal_pct = None
        self._perf_mode = tk.StringVar(value="default")  # default | quiet | eco
        self._metrics_interval_ms = 2500
        self._analytics_interval_ms = 2000
        self._security_interval_ms = 8000
        self._wifi_interval_ms = 5000
        self._news_interval_ms = 600000

        self.camera_running = False
        self.camera_capture = None
        self.voice_thread = None
        self.matrix_tick = 0
        self.matrix_columns: list[int] = []
        self.last_face_count = 0
        self.face_cascade = self._load_face_cascade()
        self.face_tracking_available = bool(self.face_cascade is not None)
        self._face_identity_label = "—"
        self._face_rec_interval = max(3, int(self.cfg.get("face_recognition_interval_frames", 10) or 10))
        self.vision_mode = tk.StringVar(value=VisionMode.MARK50)
        self._hud_anim = 0
        self._glitch_seed = random.randint(0, 10_000)
        self._face_identity_busy = False
        self._face_identity_last_request = 0.0
        self._face_identity_min_interval = 1.6
        self._mic_lock = threading.Lock()
        self._voice_busy = False
        self._wake_active = False
        self._wake_thread = None
        self._boot_greeting = ""
        self._system_loops_started = False

        self.locked = True
        self.lock_password_var = tk.StringVar()
        self.lock_status_var = tk.StringVar(value="Enter passcode to unlock J.A.R.V.I.S.")
        self.lock_face_status_var = tk.StringVar(value="Facial access panel ready.")
        self.lock_cooldown_var = tk.StringVar(value="")
        self.lock_attempts = 0
        self.lock_cooldown_until = 0.0
        self._lock_camera_capture = None
        self._lock_camera_active = False
        self._lock_camera_opening = False
        self._lock_camera_job = None
        self._lock_camera_photo = None
        self._lock_camera_frame = 0
        self._lock_face_identity = "NO FACE"
        self._lock_face_identity_busy = False
        self._lock_face_identity_last_request = 0.0

        self.force_ai_var = tk.BooleanVar(value=False)
        self.speak_reply_var = tk.BooleanVar(value=True)
        self.auto_keep_refs_var = tk.BooleanVar(value=True)
        self.face_tracking_var = tk.BooleanVar(value=self.face_tracking_available)
        self.matrix_overlay_var = tk.BooleanVar(value=True)

        self.status_text = tk.StringVar(value="ONLINE")
        self.status_detail = tk.StringVar(value="Ready for voice, camera, and file-aware chat.")
        self.context_text = tk.StringVar(value="No active references.")
        self.weather_summary = tk.StringVar(value="Awaiting refresh.")
        self.news_summary = tk.StringVar(value="Awaiting refresh.")
        self.capture_summary = tk.StringVar(value="No captures yet.")
        self.reference_name = tk.StringVar(value="No reference image selected.")
        self.file_summary = tk.StringVar(value="No files attached.")
        self.camera_summary = tk.StringVar(value="Camera offline.")
        self.clock_text = tk.StringVar(value="")
        self.date_text = tk.StringVar(value="")
        self.backdrop = None
        self._backdrop_job = None
        self._backdrop_size = (0, 0)

        self._setup_window()
        self._build_ui()
        self._build_lock_screen()
        self._start_lock_camera()
        self._theme_buttons(self.root)
        self._apply_perf_mode(self._perf_mode.get(), log=False)
        self._boot_message()
        self._update_clock()

    def _start_wifi_signal_loop(self):
        def tick():
            try:
                pct = self._get_wifi_signal_percent()
                self._wifi_signal_pct = pct
                self.orb.set_signal(pct)
            except Exception:
                pass
            self._wifi_job = self.root.after(int(getattr(self, "_wifi_interval_ms", 5000)), tick)
        self.root.after(800, tick)

    def _get_wifi_signal_percent(self) -> int | None:
        # Windows: netsh wlan show interfaces => Signal : 92%
        try:
            if platform.system().lower() != "windows":
                return None
            out = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], text=True, timeout=4, encoding="utf-8", errors="ignore")
            m = re.search(r"\\bSignal\\s*:\\s*(\\d+)\\s*%\\b", out)
            if not m:
                return None
            return int(m.group(1))
        except Exception:
            return None

    def _setup_window(self):
        self.root.title("J.A.R.V.I.S - Mission Control")
        self.root.configure(bg=BG)
        self.root.geometry("1560x930")
        self.root.minsize(1320, 820)
        self.backdrop = tk.Canvas(self.root, bg=BG, highlightthickness=0, bd=0)
        self.backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        self.backdrop.tk.call("lower", self.backdrop._w)
        self.root.bind("<Configure>", self._schedule_backdrop)
        try:
            from ctypes import byref, c_int, sizeof, windll

            hwnd = windll.user32.GetParent(self.root.winfo_id())
            color = 0x0004080E
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(color)), sizeof(c_int))
        except Exception:
            pass
        self.root.after(80, self._draw_backdrop)

    def _schedule_backdrop(self, _event=None):
        # Debounce expensive backdrop redraws and skip pure move events.
        try:
            new_size = (self.root.winfo_width(), self.root.winfo_height())
            if new_size == self._backdrop_size:
                return
        except Exception:
            pass
        if self._backdrop_job is not None:
            self.root.after_cancel(self._backdrop_job)
        self._backdrop_job = self.root.after(200, self._draw_backdrop)

    def _draw_backdrop(self):
        self._backdrop_job = None
        if not self.backdrop:
            return

        width = max(1, self.root.winfo_width())
        height = max(1, self.root.winfo_height())
        if (width, height) == self._backdrop_size:
            return
        self._backdrop_size = (width, height)

        canvas = self.backdrop
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill=BG, outline="")

        for y in range(0, height, 16):
            canvas.create_line(0, y, width, y, fill="#071018")

        def hex_points(cx: float, cy: float, radius: float):
            points = []
            for idx in range(6):
                angle = math.radians((60 * idx) - 30)
                points.extend([cx + radius * math.cos(angle), cy + radius * math.sin(angle)])
            return points

        hex_r = 18
        hex_w = hex_r * 1.72
        hex_h = hex_r * 1.5
        rows = int(height / hex_h) + 3
        cols = int(width / hex_w) + 3
        for row in range(rows):
            offset = hex_w / 2 if row % 2 else 0
            y = row * hex_h
            for col in range(cols):
                x = col * hex_w + offset
                if x > width + hex_r or y > height + hex_r:
                    continue
                canvas.create_polygon(
                    hex_points(x, y, hex_r),
                    outline="#0c1821" if (row + col) % 3 else "#122432",
                    fill="",
                    width=1,
                )

        orb_x = width // 2
        orb_y = int(height * 0.38)
        for radius, color, line_w in ((260, "#0b2736", 2), (210, CYAN_DIM, 2), (168, GOLD_DIM, 2)):
            canvas.create_oval(orb_x - radius, orb_y - radius, orb_x + radius, orb_y + radius, outline=color, width=line_w)

        for start, extent, color, line_w in (
            (18, 68, GOLD, 3),
            (132, 96, CYAN, 2),
            (274, 54, RED, 3),
        ):
            canvas.create_arc(
                orb_x - 238,
                orb_y - 238,
                orb_x + 238,
                orb_y + 238,
                start=start,
                extent=extent,
                style="arc",
                outline=color,
                width=line_w,
            )

        corner = 54
        canvas.create_line(16, 16, 16 + corner, 16, fill=GOLD, width=3)
        canvas.create_line(16, 16, 16, 16 + corner, fill=GOLD, width=3)
        canvas.create_line(width - 16 - corner, 16, width - 16, 16, fill=CYAN, width=3)
        canvas.create_line(width - 16, 16, width - 16, 16 + corner, fill=CYAN, width=3)
        canvas.create_line(16, height - 16, 16 + corner, height - 16, fill=RED, width=3)
        canvas.create_line(16, height - 16 - corner, 16, height - 16, fill=RED, width=3)
        canvas.create_line(width - 16 - corner, height - 16, width - 16, height - 16, fill=GOLD, width=3)
        canvas.create_line(width - 16, height - 16 - corner, width - 16, height - 16, fill=GOLD, width=3)

    def _load_face_cascade(self):
        if not cv2:
            return None
        try:
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(str(cascade_path))
            if cascade.empty():
                return None
            return cascade
        except Exception:
            return None

    def _button_style_for_text(self, text: str) -> str:
        label = (text or "").strip().upper()
        if not label:
            return "ghost"
        if any(token in label for token in ("STOP", "CLEAR", "REMOVE")):
            return "danger"
        if any(token in label for token in ("SEND", "VOICE", "ANALYZE", "CAM", "SNAP", "ATTACH IMAGE")):
            return "arc"
        if any(token in label for token in ("THERM", "REFRESH", "LOAD", "USE", "ADD", "ATTACH", "PROJECT", "HP COOLING", "SYSTEM REPORT")):
            return "primary"
        return "ghost"

    def _set_vision_mode(self, mode: str):
        self.vision_mode.set(mode)
        self._sync_vision_mode_buttons()
        label = VisionMode.LABELS.get(mode, mode).upper()
        self._log_system(f"📷 Vision mode set: {label}")

    def _sync_vision_mode_buttons(self):
        active = self.vision_mode.get()
        for mode, btn in getattr(self, "_vision_mode_buttons", {}).items():
            if mode == active:
                apply_button_style(btn, "primary")
            else:
                apply_button_style(btn, "ghost")

    def _theme_buttons(self, parent):
        for child in parent.winfo_children():
            if isinstance(child, tk.Button):
                apply_button_style(child, getattr(child, "_hud_style", self._button_style_for_text(child.cget("text"))))
                enhance_hud_button(child)
            elif not isinstance(child, (tk.Tk, tk.Toplevel)):
                self._theme_buttons(child)

    def _build_ui(self):
        tk.Frame(self.root, bg=GOLD, height=4).pack(fill="x", side="top")
        self._build_topbar()

        # Bottom waveform bar (audio feedback)
        self.waveform_frame = tk.Frame(self.root, bg=BG_PANEL_ALT, highlightthickness=1, highlightbackground=BORDER)
        self.waveform_frame.pack(fill="x", side="bottom", padx=18, pady=(0, 18))
        self.waveform_canvas = tk.Canvas(self.waveform_frame, bg=BG_PANEL_ALT, height=46, highlightthickness=0, bd=0)
        self.waveform_canvas.pack(fill="x", padx=10, pady=8)
        self.waveform_canvas.bind("<Button-1>", self._cycle_audio_vis_mode)

        host = tk.Frame(self.root, bg=BG)
        host.pack(fill="both", expand=True, padx=18, pady=(12, 12))
        host.rowconfigure(0, weight=1)
        host.columnconfigure(0, weight=1)

        # Notebook shell for multi-tab mission control.
        self._init_notebook_style()
        notebook = ttk.Notebook(host)
        notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook = notebook

        self.tab_mission = tk.Frame(notebook, bg=BG)
        self.tab_analytics = tk.Frame(notebook, bg=BG)
        self.tab_command = tk.Frame(notebook, bg=BG)
        self.tab_security = tk.Frame(notebook, bg=BG)
        self.tab_settings = tk.Frame(notebook, bg=BG)

        notebook.add(self.tab_mission, text="MISSION CORE")
        notebook.add(self.tab_analytics, text="ANALYTICS")
        notebook.add(self.tab_command, text="COMMAND CENTER")
        notebook.add(self.tab_security, text="SECURITY")
        notebook.add(self.tab_settings, text="SETTINGS")

        self._build_mission_core_tab(self.tab_mission)
        self._build_analytics_tab(self.tab_analytics)
        self._build_command_center_tab(self.tab_command)
        self._build_security_tab(self.tab_security)
        self._build_settings_tab(self.tab_settings)

    def _build_lock_screen(self):
        self.lock_overlay = tk.Frame(self.root, bg="#02040c")
        self.lock_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.lock_canvas = tk.Canvas(self.lock_overlay, bg="#02040c", highlightthickness=0, bd=0)
        self.lock_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lock_canvas.bind("<Configure>", self._draw_lock_hud_shell)

        content = tk.Frame(self.lock_overlay, bg="#020912")
        content.place(relx=0.095, rely=0.13, relwidth=0.81, relheight=0.74)
        content.columnconfigure(0, weight=44)
        content.columnconfigure(1, weight=56)
        content.rowconfigure(0, weight=1)

        left = tk.Frame(content, bg="#020912")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 38))
        left.rowconfigure(1, weight=1)

        brand = tk.Frame(left, bg="#020912")
        brand.grid(row=0, column=0, sticky="nw")
        logo = tk.Canvas(brand, width=72, height=72, bg="#020912", highlightthickness=0, bd=0)
        logo.pack(side="left", padx=(0, 18))
        logo.create_oval(11, 11, 61, 61, outline=CYAN, width=2)
        logo.create_oval(6, 6, 66, 66, outline=CYAN_DIM, width=1)
        logo.create_polygon(36, 17, 55, 52, 17, 52, outline=CYAN, fill="#073146", width=2)
        logo.create_polygon(36, 27, 46, 46, 26, 46, outline="#7df3ff", fill="#0b5b75", width=1)
        for start in (22, 154, 286):
            logo.create_arc(3, 3, 69, 69, start=start, extent=48, outline=CYAN_SOFT, width=2, style="arc")

        brand_text = tk.Frame(brand, bg="#020912")
        brand_text.pack(side="left", anchor="center")
        tk.Label(brand_text, text="J.A.R.V.I.S", fg=GOLD, bg="#020912",
                 font=(FONT_ORBITRON, 20, "bold")).pack(anchor="w")
        tk.Label(brand_text, text="MISSION CONTROL", fg=TEXT_DIM, bg="#020912",
                 font=(FONT_EXO, 10, "bold")).pack(anchor="w", pady=(4, 0))

        lock_block = tk.Frame(left, bg="#020912")
        lock_block.grid(row=1, column=0, sticky="sw", pady=(30, 44))
        title_row = tk.Frame(lock_block, bg="#020912")
        title_row.pack(anchor="w")
        lock_icon = tk.Canvas(title_row, width=52, height=52, bg="#020912", highlightthickness=0, bd=0)
        lock_icon.pack(side="left", padx=(0, 18))
        lock_icon.create_arc(12, 7, 40, 39, start=0, extent=180, outline=GOLD, width=5, style="arc")
        lock_icon.create_rectangle(8, 24, 44, 47, fill=GOLD, outline=GOLD)
        lock_icon.create_rectangle(24, 33, 28, 43, fill="#7a5600", outline="")
        tk.Label(title_row, text="SYSTEM LOCKED", fg=GOLD, bg="#020912",
                 font=(FONT_ORBITRON, 28, "bold")).pack(side="left", anchor="center")

        tk.Label(lock_block, text="Authentication required to access J.A.R.V.I.S",
                 fg=TEXT, bg="#020912", font=(FONT_EXO, 15, "bold")).pack(anchor="w", pady=(18, 30))
        tk.Frame(lock_block, bg="#34291d", height=1).pack(fill="x", pady=(0, 30))

        tk.Label(lock_block, text="SECURITY LEVEL", fg=TEXT, bg="#020912",
                 font=(FONT_EXO, 10, "bold")).pack(anchor="w", pady=(0, 12))
        bar_row = tk.Frame(lock_block, bg="#020912")
        bar_row.pack(anchor="w", pady=(0, 30))
        for i in range(8):
            color = GOLD if i < 6 else "#071420"
            tk.Frame(
                bar_row,
                bg=color,
                width=22,
                height=22,
                highlightthickness=1,
                highlightbackground=GOLD if i >= 6 else GOLD_SOFT,
            ).pack(side="left", padx=(0, 12))

        tk.Frame(lock_block, bg="#34291d", height=1).pack(fill="x", pady=(0, 28))
        warn_row = tk.Frame(lock_block, bg="#020912")
        warn_row.pack(anchor="w")
        tk.Label(warn_row, text="///", fg=GOLD, bg="#020912",
                 font=(FONT_ORBITRON, 16, "bold")).pack(side="left", padx=(0, 20))
        self.lock_warn = tk.Label(warn_row, text="Unauthorized access is prohibited",
                                  fg=TEXT_DIM, bg="#020912", font=(FONT_EXO, 10, "bold"))
        self.lock_warn.pack(side="left")

        right = tk.Frame(content, bg="#020912")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        auth_card = tk.Frame(right, bg="#020912")
        auth_card.grid(row=0, column=0, sticky="nsew")
        auth_card.columnconfigure(0, weight=1)

        tk.Label(auth_card, text="FACE RECOGNITION", fg=CYAN, bg="#020912",
                 font=(FONT_ORBITRON, 12, "bold")).pack(anchor="center", pady=(28, 10))
        camera_frame = tk.Frame(
            auth_card,
            bg="#03111a",
            height=340,
            highlightthickness=1,
            highlightbackground=CYAN_DIM,
        )
        camera_frame.pack(fill="x", padx=22, pady=(0, 20))
        camera_frame.pack_propagate(False)

        self.lock_camera_canvas = tk.Canvas(
            camera_frame,
            bg="#03111a",
            highlightthickness=0,
            bd=0,
        )
        self.lock_camera_canvas.pack(fill="both", expand=True)
        self.lock_camera_canvas.bind("<Configure>", lambda _e: self._draw_lock_camera_placeholder())

        tk.Label(auth_card, textvariable=self.lock_face_status_var, fg=CYAN, bg="#020912",
                 font=(FONT_EXO, 10, "bold"), justify="left", wraplength=560).pack(anchor="w", padx=22, pady=(0, 8))

        input_card = tk.Frame(auth_card, bg="#020912")
        input_card.pack(fill="x", padx=22, pady=(0, 20))
        tk.Label(input_card, text="PASSWORD", fg=CYAN, bg="#020912",
                 font=(FONT_EXO, 10, "bold")).pack(anchor="w", pady=(0, 8))
        entry_shell = tk.Frame(input_card, bg=BG_INPUT, highlightthickness=1, highlightbackground=CYAN_DIM)
        entry_shell.pack(fill="x")
        self.lock_password_entry = tk.Entry(
            entry_shell,
            textvariable=self.lock_password_var,
            bg=BG_INPUT,
            fg=TEXT,
            insertbackground=CYAN,
            relief="flat",
            bd=0,
            font=(FONT_EXO, 12, "bold"),
            show="*",
        )
        self.lock_password_entry.pack(side="left", fill="x", expand=True, padx=(16, 8), ipady=14)
        tk.Label(entry_shell, text="[LOCK]", fg=TEXT_DIM, bg=BG_INPUT,
                 font=(FONT_MONO, 9)).pack(side="right", padx=(0, 14))
        self.lock_password_entry.bind("<Return>", lambda e: self._validate_lock_password())
        self.lock_password_entry.focus_set()

        self.lock_status_label = tk.Label(input_card, textvariable=self.lock_status_var,
                                          fg=TEXT, bg="#020912", font=FONT_SMALL, justify="left",
                                          wraplength=560)
        self.lock_status_label.pack(anchor="w", pady=(10, 0))

        self.lock_submit_btn = tk.Button(
            auth_card,
            text="CONTINUE  ->",
            command=self._validate_lock_password,
            bg="#00c853",
            fg="#f4fff7",
            activebackground="#14e66a",
            activeforeground="#f4fff7",
            relief="flat",
            bd=0,
            padx=14,
            pady=16,
            font=(FONT_ORBITRON, 12, "bold"),
            cursor="hand2",
        )
        self.lock_submit_btn.pack(fill="x", padx=22, pady=(0, 22))

        tk.Button(
            auth_card,
            text="Forgot Password?  ?",
            command=self._show_forgot_password,
            bg="#020912",
            fg=CYAN,
            activebackground="#06131d",
            activeforeground=TEXT,
            relief="flat",
            bd=1,
            highlightthickness=1,
            highlightbackground=CYAN_DIM,
            padx=14,
            pady=12,
            font=(FONT_EXO, 10, "bold"),
            cursor="hand2",
        ).pack(fill="x", padx=22, pady=(0, 12))

        tk.Label(
            auth_card,
            textvariable=self.lock_cooldown_var,
            fg=RED,
            bg="#020912",
            font=FONT_SMALL,
            justify="left",
            wraplength=560,
        ).pack(anchor="w", padx=22)

        self.lock_overlay.bind("<Button-1>", lambda e: None)
        self.lock_overlay.lift()
        self.root.after(50, self._draw_lock_hud_shell)
        self.root.after(80, self._draw_lock_camera_placeholder)

    def _draw_lock_hud_shell(self, _event=None):
        canvas = getattr(self, "lock_canvas", None)
        if canvas is None:
            return
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#02040c", outline="")

        for y in range(0, height + 20, 22):
            canvas.create_line(0, y, width, y, fill="#06111a")
        hex_r = 16
        hex_w = hex_r * 1.72
        hex_h = hex_r * 1.5
        rows = int(height / hex_h) + 2
        cols = int(width / hex_w) + 2
        for row in range(rows):
            offset = hex_w / 2 if row % 2 else 0
            cy = row * hex_h
            for col in range(cols):
                cx = col * hex_w + offset
                if 80 < cx < width - 80 and 70 < cy < height - 70:
                    continue
                pts = []
                for idx in range(6):
                    angle = math.radians((60 * idx) - 30)
                    pts.extend([cx + hex_r * math.cos(angle), cy + hex_r * math.sin(angle)])
                canvas.create_polygon(pts, outline="#082030", fill="", width=1)

        margin = 32
        cut = 26
        top_tab_w = 112
        tab_left = width / 2 - top_tab_w / 2
        tab_right = width / 2 + top_tab_w / 2
        shell = [
            margin + cut, margin,
            tab_left - 42, margin,
            tab_left - 22, margin + 14,
            tab_left, margin + 14,
            tab_left + 12, margin - 10,
            tab_right - 12, margin - 10,
            tab_right, margin + 14,
            tab_right + 22, margin + 14,
            tab_right + 42, margin,
            width - margin - cut, margin,
            width - margin, margin + cut,
            width - margin, height - margin - cut,
            width - margin - cut, height - margin,
            tab_right + 42, height - margin,
            tab_right + 22, height - margin - 14,
            tab_left - 22, height - margin - 14,
            tab_left - 42, height - margin,
            margin + cut, height - margin,
            margin, height - margin - cut,
            margin, margin + cut,
            margin + cut, margin,
        ]
        canvas.create_line(*shell, fill=GOLD, width=2)
        canvas.create_line(margin + cut + 12, margin + 8, tab_left - 72, margin + 8, fill="#714f09", width=1)
        canvas.create_line(tab_right + 72, margin + 8, width - margin - cut - 12, margin + 8, fill="#714f09", width=1)
        canvas.create_line(margin + cut + 12, height - margin - 8, tab_left - 72, height - margin - 8, fill="#714f09", width=1)
        canvas.create_line(tab_right + 72, height - margin - 8, width - margin - cut - 12, height - margin - 8, fill="#714f09", width=1)

        canvas.create_polygon(
            tab_left + 8, margin - 18,
            tab_right - 8, margin - 18,
            tab_right + 16, margin + 4,
            tab_right - 10, margin + 28,
            tab_left + 10, margin + 28,
            tab_left - 16, margin + 4,
            fill="#06111a",
            outline=GOLD,
            width=2,
        )
        canvas.create_text(width / 2, margin + 5, text="////", fill=GOLD, font=(FONT_ORBITRON, 12, "bold"))
        canvas.create_text(width / 2, height - margin + 6, text="/////", fill=GOLD, font=(FONT_ORBITRON, 11, "bold"))

        for side_x, sign in ((margin - 4, 1), (width - margin + 4, -1)):
            base_y = height * 0.42
            for idx in range(8):
                y = base_y + idx * 18
                canvas.create_line(side_x, y, side_x + sign * (8 + (idx % 3) * 4), y - 8, fill=CYAN if idx % 2 else GOLD, width=2)

    def _draw_lock_camera_overlay(self, canvas: tk.Canvas, width: int, height: int):
        corner = 30
        inset = 10
        for sx, sy in ((inset, inset), (width - inset, inset), (inset, height - inset), (width - inset, height - inset)):
            hx = corner if sx == inset else -corner
            vy = corner if sy == inset else -corner
            canvas.create_line(sx, sy, sx + hx, sy, fill=CYAN, width=2)
            canvas.create_line(sx, sy, sx, sy + vy, fill=CYAN, width=2)
        cx = width // 2
        cy = height // 2
        canvas.create_line(cx, 34, cx, cy - 44, fill="#0b6d88", width=1)
        canvas.create_line(cx, cy + 44, cx, height - 34, fill="#0b6d88", width=1)
        canvas.create_line(44, cy, cx - 44, cy, fill="#0b6d88", width=1)
        canvas.create_line(cx + 44, cy, width - 44, cy, fill="#0b6d88", width=1)
        canvas.create_line(cx - 14, cy, cx + 14, cy, fill=CYAN_DIM, width=1)
        canvas.create_line(cx, cy - 14, cx, cy + 14, fill=CYAN_DIM, width=1)

    def _draw_lock_camera_placeholder(self, status: str | None = None):
        canvas = getattr(self, "lock_camera_canvas", None)
        if canvas is None:
            return
        if getattr(self, "_lock_camera_photo", None) is not None and not status:
            return
        width = max(280, canvas.winfo_width())
        height = max(190, canvas.winfo_height())
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#03111a", outline="")
        for y in range(0, height, 16):
            canvas.create_line(0, y, width, y, fill="#051a27")
        self._draw_lock_camera_overlay(canvas, width, height)
        label = status or "CAMERA STANDBY"
        canvas.create_text(width / 2, height / 2 + 32, text=label, fill=TEXT_DIM, font=(FONT_MONO, 10, "bold"))

    def _start_lock_camera(self):
        if not (cv2 and PIL_OK and self.face_cascade):
            self.lock_face_status_var.set("Facial access panel unavailable.")
            self._draw_lock_camera_placeholder("CAMERA UNAVAILABLE")
            return
        if self._lock_camera_opening or self._lock_camera_active:
            return
        self._lock_camera_opening = True
        self._lock_camera_active = True
        self.lock_face_status_var.set("Facial access panel initializing...")
        self._draw_lock_camera_placeholder("INITIALIZING CAMERA")

        def _init_cam():
            try:
                capture = self._camera_backend()
                if not capture or not capture.isOpened():
                    raise RuntimeError("Unable to open camera")
                try:
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
                    capture.set(cv2.CAP_PROP_FPS, 15)
                except Exception:
                    pass
                if not self._lock_camera_active:
                    capture.release()
                    self._lock_camera_opening = False
                    return
                self._lock_camera_capture = capture
                self._lock_camera_opening = False
                self._update_lock_camera()
            except Exception as e:
                self.lock_face_status_var.set(f"Camera preview failed: {e}")
                self._lock_camera_active = False
                self._lock_camera_opening = False
                self._lock_camera_capture = None
                self._draw_lock_camera_placeholder("CAMERA FAILED")

        self.root.after(50, _init_cam)

    def _stop_lock_camera(self):
        self._lock_camera_active = False
        self._lock_camera_opening = False
        if self._lock_camera_job is not None:
            try:
                self.root.after_cancel(self._lock_camera_job)
            except Exception:
                pass
            self._lock_camera_job = None
        if self._lock_camera_capture is not None:
            try:
                self._lock_camera_capture.release()
            except Exception:
                pass
        self._lock_camera_capture = None
        self._lock_camera_photo = None

    def _request_lock_face_identity(self, frame, faces):
        if self._lock_face_identity_busy:
            return
        now = time.time()
        if now - self._lock_face_identity_last_request < 1.5:
            return
        owner_face = getattr(self.jarvis, "owner_face", None)
        if not owner_face or not owner_face.enabled:
            self._lock_face_identity = "FACE DETECTED"
            return
        self._lock_face_identity_busy = True
        self._lock_face_identity_last_request = now
        frame_copy = frame.copy()
        faces_copy = [tuple(map(int, face)) for face in faces]

        def worker():
            try:
                identity = owner_face.identify_primary(frame_copy, faces_copy)
            except Exception:
                identity = "?"

            def done():
                self._lock_face_identity = identity or "?"
                self._lock_face_identity_busy = False

            self._safe_after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _update_lock_camera(self):
        self._lock_camera_job = None
        if not self._lock_camera_active or self._lock_camera_capture is None:
            return
        try:
            ok, frame = self._lock_camera_capture.read()
            if ok and frame is not None:
                self._lock_camera_frame += 1
                
                # Only run heavy face detection every 4th frame to prevent GUI lag
                if getattr(self, "_last_lock_faces", None) is None:
                    self._last_lock_faces = []
                
                if self.face_cascade is not None and self._lock_camera_frame % 4 == 0:
                    small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    detected = self.face_cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.14,
                        minNeighbors=4,
                        minSize=(48, 48),
                    )
                    self._last_lock_faces = [(int(x * 2), int(y * 2), int(w * 2), int(h * 2)) for (x, y, w, h) in detected]
                
                faces = self._last_lock_faces
                identity = self._lock_face_identity if faces else "NO FACE"
                if faces is not None and len(faces):
                    if self._lock_camera_frame % 15 == 0:
                        self._request_lock_face_identity(frame, list(faces))
                    identity = self._lock_face_identity
                    for (x, y, w, h) in faces:
                        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 212, 255), 2)
                        cv2.line(frame, (x, y), (x + 28, y), (255, 184, 0), 2)
                        cv2.line(frame, (x, y), (x, y + 28), (255, 184, 0), 2)
                else:
                    self._lock_face_identity = "NO FACE"
                self.lock_face_status_var.set(f"Facial access panel: {identity}")
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                canvas = self.lock_camera_canvas
                width = max(280, canvas.winfo_width())
                height = max(190, canvas.winfo_height())
                image = ImageOps.contain(image, (width, height), Image.BILINEAR)
                panel = Image.new("RGB", (width, height), "#03111a")
                panel.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
                photo = ImageTk.PhotoImage(panel)
                canvas.delete("all")
                canvas.create_image(0, 0, image=photo, anchor="nw")
                self._draw_lock_camera_overlay(canvas, width, height)
                self._lock_camera_photo = photo
        except Exception as e:
            self.lock_face_status_var.set(f"Facial panel error: {e}")
        if self._lock_camera_active:
            self._lock_camera_job = self.root.after(180, self._update_lock_camera)

    def _validate_lock_password(self):
        now = time.time()
        if self.lock_cooldown_until and now < self.lock_cooldown_until:
            remaining = int(self.lock_cooldown_until - now)
            self.lock_status_var.set(f"Cooldown active. Try again in {remaining} seconds.")
            return
        password = (self.lock_password_var.get() or "").strip()
        if not password:
            self.lock_status_var.set("Passcode required to unlock.")
            return
        if password in ("0A0W8E4P7X6N9X1U3", "Astaroth_legion.v.2.0"):
            self._unlock_system()
            return
        self.lock_attempts += 1
        self.lock_status_var.set("ACCESS DENIED. Incorrect passcode.")
        self.toasts.show("Access denied.", "warning")
        self.lock_password_var.set("")
        self.lock_password_entry.focus_set()
        if self.lock_attempts >= 3:
            self._start_lock_cooldown()

    def _show_forgot_password(self):
        answer = simpledialog.askstring(
            "Forgot Password",
            "Enter recovery key:",
            show="*",
            parent=self.root,
        )
        if answer is None:
            return
        if answer.strip() == "Astaroth_legion.v.2.0":
            self._unlock_system()
            return
        self.lock_attempts += 1
        self.lock_status_var.set("Recovery key invalid.")
        self.toasts.show("Recovery failed.", "warning")
        if self.lock_attempts >= 3:
            self._start_lock_cooldown()

    def _start_lock_cooldown(self):
        self.lock_cooldown_until = time.time() + 30
        self.lock_password_entry.configure(state="disabled")
        self.lock_submit_btn.configure(state="disabled")
        self.lock_status_var.set("Too many failed attempts. Cooldown active.")
        self._update_lock_cooldown()

    def _update_lock_cooldown(self):
        remaining = int(self.lock_cooldown_until - time.time())
        if remaining > 0:
            self.lock_cooldown_var.set(f"Retry available in {remaining} seconds.")
            self.root.after(1000, self._update_lock_cooldown)
            return
        self.lock_cooldown_var.set("")
        self.lock_status_var.set("Cooldown ended. Enter passcode to unlock.")
        self.lock_password_entry.configure(state="normal")
        self.lock_submit_btn.configure(state="normal")
        self.lock_attempts = 0
        self.lock_password_entry.focus_set()

    def _unlock_system(self):
        self.locked = False
        self._stop_lock_camera()
        if self.lock_overlay is not None:
            self.lock_overlay.place_forget()
            self.lock_overlay.destroy()
            self.lock_overlay = None
        self.lock_status_var.set("Access accepted. Welcome.")
        self.toasts.show("ACCESS ACCEPTED", "success")
        self._start_system_loops()

    def _start_system_loops(self):
        if self._system_loops_started:
            return
        self._system_loops_started = True
        if self._boot_greeting:
            self.root.after(500, lambda: self._safe_speak(self._boot_greeting))
        self._start_wake_listener()
        self._update_metrics()
        self._refresh_weather()
        self._refresh_news()
        self._start_waveform_loop()
        self._start_analytics_loop()
        self._start_wifi_signal_loop()
        self._start_radar_loop()

    def _safe_after(self, delay_ms: int, callback, *args):
        try:
            if not getattr(self, 'root', None):
                return None
            return self.root.after(delay_ms, callback, *args)
        except RuntimeError:
            return None

    def _ensure_audio_meter(self):
        if self._audio_meter is None:
            self._audio_meter = AudioMeter()
        return self._audio_meter

    def _set_audio_state(self, state: str):
        self._audio_state = state
        # Keep legacy meter for simple level, but prefer analyzers for FFT.
        meter = self._ensure_audio_meter()
        if state == "mic":
            meter.start_mic()
            self._ensure_analyzers(start_mic=True, start_tts=False)
        elif state == "tts":
            meter.start_loopback()
            self._ensure_analyzers(start_mic=False, start_tts=True)
        else:
            meter.stop()
            self._ensure_analyzers(start_mic=False, start_tts=False)

    def _ensure_analyzers(self, start_mic: bool, start_tts: bool):
        if self._mic_analyzer is None:
            self._mic_analyzer = AudioAnalyzer("mic")
        if self._tts_analyzer is None:
            self._tts_analyzer = AudioAnalyzer("loopback")

        if start_mic:
            self._mic_analyzer.start()
        else:
            self._mic_analyzer.stop()

        if start_tts:
            self._tts_analyzer.start()
        else:
            self._tts_analyzer.stop()

    def _cycle_audio_vis_mode(self, _event=None):
        order = ["spectrum", "bars", "wave"]
        cur = self._audio_vis_mode
        try:
            nxt = order[(order.index(cur) + 1) % len(order)]
        except Exception:
            nxt = "spectrum"
        self._audio_vis_mode = nxt
        self.toasts.show(f"Audio visualizer: {nxt.upper()}", "info", 1600)

    def _start_waveform_loop(self):
        self._wave_seed = random.randint(0, 10_000)
        self._wave_phase = 0

        def tick():
            try:
                self._draw_waveform()
            finally:
                self.root.after(33, tick)

        self.root.after(120, tick)

    def _draw_waveform(self):
        canvas = getattr(self, "waveform_canvas", None)
        if canvas is None:
            return
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        canvas.delete("all")
        mid = h // 2
        top_base = mid - 2
        bot_base = h - 2

        # Lane levels
        mic_lvl = float(self._mic_analyzer.level()) if self._mic_analyzer else 0.0
        tts_lvl = float(self._tts_analyzer.level()) if self._tts_analyzer else 0.0

        # Speaking fallback if loopback cannot be measured
        if self._audio_state == "tts" and tts_lvl < 0.02:
            tts_lvl = 0.25 + 0.25 * (0.5 + 0.5 * math.sin(self._hud_anim * 0.24))

        # idle decay
        if self._audio_state == "idle":
            mic_lvl *= 0.12
            tts_lvl *= 0.12

        gold = GOLD
        green = VOICE_GREEN
        idle = TEXT_FAINT

        # baselines
        canvas.create_line(0, top_base, w, top_base, fill=GLOW, width=1)
        canvas.create_line(0, bot_base, w, bot_base, fill=GLOW, width=1)

        mode = self._audio_vis_mode
        bands = 52
        gap = 2
        bar_w = max(2, int((w - 2) / bands))

        if mode in ("spectrum", "bars"):
            if mode == "spectrum" and self._tts_analyzer and self._mic_analyzer:
                top_vals = self._tts_analyzer.fft_bands(bands=bands)
                bot_vals = self._mic_analyzer.fft_bands(bands=bands)
            else:
                # amplitude bars: spread level with slight band weighting
                self._wave_phase = (self._wave_phase + 1) % 10_000
                top_vals = []
                bot_vals = []
                for i in range(bands):
                    bass_boost = 1.15 - (i / max(1, bands - 1)) * 0.55
                    jitter = 0.10 * math.sin((i * 0.55) + (self._wave_phase * 0.22))
                    top_vals.append(max(0.0, min(1.0, (tts_lvl * bass_boost) + jitter)))
                    bot_vals.append(max(0.0, min(1.0, (mic_lvl * bass_boost) + jitter)))

            # draw top (tts) and bottom (mic mirrored)
            for i in range(bands):
                x1 = i * bar_w
                x2 = x1 + bar_w - gap
                # speaking lane
                amp = float(top_vals[i]) * (0.35 + 0.65 * tts_lvl)
                bar_h = int(3 + amp * (mid - 10))
                canvas.create_rectangle(x1, top_base - bar_h, x2, top_base, fill=gold if self._audio_state == "tts" else idle, outline="")
                # mic lane (mirrored)
                amp2 = float(bot_vals[i]) * (0.35 + 0.65 * mic_lvl)
                bar_h2 = int(3 + amp2 * (mid - 10))
                canvas.create_rectangle(x1, top_base + 4, x2, top_base + 4 + bar_h2, fill=green if self._audio_state == "mic" else idle, outline="")

        else:
            # waveform mode: smooth-ish polyline (top=tts, bottom=mic)
            pts = 200
            top_w = self._tts_analyzer.waveform(points=pts) if self._tts_analyzer else [0.0] * pts
            bot_w = self._mic_analyzer.waveform(points=pts) if self._mic_analyzer else [0.0] * pts
            # flatten when idle
            if self._audio_state == "idle":
                top_w = [v * 0.12 for v in top_w]
                bot_w = [v * 0.12 for v in bot_w]
            # scale with levels
            top_scale = (mid - 10) * max(0.08, min(1.0, tts_lvl * 1.2))
            bot_scale = (mid - 10) * max(0.08, min(1.0, mic_lvl * 1.2))

            def poly(samples, y_mid, scale):
                out = []
                for i, v in enumerate(samples):
                    x = int(i * (w - 1) / max(1, len(samples) - 1))
                    y = int(y_mid + (-v * scale))
                    out.extend([x, y])
                return out

            top_pts = poly(top_w, top_base - (mid // 3), top_scale)
            bot_pts = poly(bot_w, top_base + (mid // 3), bot_scale)
            if len(top_pts) >= 4:
                canvas.create_line(*top_pts, fill=gold if self._audio_state == "tts" else idle, width=2, smooth=True)
            if len(bot_pts) >= 4:
                canvas.create_line(*bot_pts, fill=green if self._audio_state == "mic" else idle, width=2, smooth=True)

        # Dynamic label
        now = time.time()
        if now < self._audio_wake_until:
            label = "⚡ WAKE WORD DETECTED"
            color = CYAN
        elif self._audio_state == "mic":
            label = "🎙 LISTENING"
            color = VOICE_GREEN
        elif self._audio_state == "tts":
            label = "🔊 JARVIS SPEAKING"
            color = GOLD
        else:
            label = "💤 STANDBY"
            color = TEXT_FAINT
        canvas.create_text(8, 6, anchor="nw", text=f"{label}  |  {mode.upper()}", fill=color, font=("JetBrains Mono", 8))

    def _init_notebook_style(self):
        try:
            style = ttk.Style(self.root)
            style.theme_use(style.theme_use())
            style.configure(
                "TNotebook",
                background=BG,
                borderwidth=0,
            )
            style.configure(
                "TNotebook.Tab",
                background=BG_PANEL_ALT,
                foreground=TEXT_DIM,
                padding=(14, 8),
                borderwidth=0,
                focuscolor=BG,
                font=FONT_SMALL,
            )
            style.map(
                "TNotebook.Tab",
                background=[("selected", BG_INPUT), ("active", BG_PANEL)],
                foreground=[("selected", GOLD), ("active", TEXT)],
            )
        except Exception:
            pass

    def _build_placeholder_tab(self, parent, text: str):
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="both", expand=True)
        tk.Label(wrap, text=text, fg=TEXT_DIM, bg=BG, font=FONT_UI).pack(pady=22)

    def _build_mission_core_tab(self, parent):
        main = tk.Frame(parent, bg=BG)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=0, minsize=320)
        main.columnconfigure(1, weight=1)
        main.columnconfigure(2, weight=0, minsize=430)
        main.rowconfigure(0, weight=1)

        left = ScrollColumn(main, width=320)
        left.grid(row=0, column=0, sticky="nsew")
        # Make center stack scrollable so radar and lower cards are fully reachable.
        center = ScrollColumn(main, width=780)
        center.grid(row=0, column=1, sticky="nsew", padx=14)
        right = tk.Frame(main, bg=BG)
        right.grid(row=0, column=2, sticky="nse")

        center.content.rowconfigure(0, weight=0)
        center.content.rowconfigure(1, weight=0)
        center.content.rowconfigure(2, weight=1)
        center.content.columnconfigure(0, weight=1)

        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=0)
        right.columnconfigure(0, weight=1)

        self._build_left_column(left.content)
        self._build_center_column(center.content)
        self._build_right_column(right)

    # ── ANALYTICS TAB ──────────────────────────────────────────
    def _build_analytics_tab(self, parent):
        wrapper = tk.Frame(parent, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=14, pady=14)
        wrapper.columnconfigure(0, weight=2)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(0, weight=1)

        left = tk.Frame(wrapper, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        right = tk.Frame(wrapper, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        charts = HudCard(left, "LIVE CHARTS", "Last 60 seconds · updates every 2 seconds")
        charts.pack(fill="both", expand=False, pady=(0, 12))
        charts.body.columnconfigure((0, 1), weight=1)

        self.chart_cpu = LineChart(charts.body, "CPU %", color=CYAN, height=90, max_points=60)
        self.chart_ram = LineChart(charts.body, "RAM %", color=ORANGE, height=90, max_points=60)
        self.chart_batt = LineChart(charts.body, "BATTERY %", color=GOLD, height=90, max_points=60)
        self.chart_net_down = LineChart(charts.body, "NET DOWN KB/s", color=CYAN_SOFT, height=90, max_points=60)
        self.chart_net_up = LineChart(charts.body, "NET UP KB/s", color=GREEN, height=90, max_points=60)
        self.chart_disk = LineChart(charts.body, "DISK IO KB/s", color=TEXT_DIM, height=90, max_points=60)

        # Place as a 2-column grid.
        for r in range(3):
            charts.body.rowconfigure(r, weight=1)
        self.chart_cpu._label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.chart_ram._label.grid(row=0, column=1, sticky="w")
        self.chart_cpu.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 10))
        self.chart_ram.grid(row=1, column=1, sticky="ew", pady=(0, 10))
        self.chart_batt._label.grid(row=2, column=0, sticky="w", padx=(0, 8))
        self.chart_disk._label.grid(row=2, column=1, sticky="w")
        self.chart_batt.grid(row=3, column=0, sticky="ew", padx=(0, 8), pady=(0, 10))
        self.chart_disk.grid(row=3, column=1, sticky="ew", pady=(0, 10))
        self.chart_net_down._label.grid(row=4, column=0, sticky="w", padx=(0, 8))
        self.chart_net_up._label.grid(row=4, column=1, sticky="w")
        self.chart_net_down.grid(row=5, column=0, sticky="ew", padx=(0, 8))
        self.chart_net_up.grid(row=5, column=1, sticky="ew")

        stats = HudCard(right, "SESSION STATS", "Live counters for today/session")
        stats.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.analytics_stats_label = tk.Label(
            stats.body,
            text="Initializing...",
            fg=TEXT,
            bg=BG_PANEL,
            justify="left",
            font=FONT_SMALL,
        )
        self.analytics_stats_label.pack(anchor="w")

        proc = HudCard(right, "TOP PROCESSES", "Top 10 by CPU · refresh 5 seconds")
        proc.grid(row=1, column=0, sticky="nsew")
        proc.body.rowconfigure(0, weight=1)
        proc.body.columnconfigure(0, weight=1)

        self.proc_list = tk.Listbox(
            proc.body,
            bg=BG_INPUT,
            fg=TEXT,
            selectbackground=RED_SOFT,
            selectforeground="#fff2ee",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            font=("JetBrains Mono", 9),
            height=10,
        )
        self.proc_list.grid(row=0, column=0, sticky="nsew")

        btns = tk.Frame(proc.body, bg=BG_PANEL)
        btns.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        btns.columnconfigure((0, 1), weight=1)
        self.kill_proc_btn = tk.Button(
            btns,
            text="KILL SELECTED",
            command=self._kill_selected_process,
            bg=BG_INPUT,
            fg=RED,
            activebackground=RED_SOFT,
            activeforeground="#fff2ee",
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            font=FONT_SMALL,
            cursor="hand2",
        )
        self.kill_proc_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Button(
            btns,
            text="REFRESH",
            command=self._refresh_process_table,
            bg=BG_INPUT,
            fg=CYAN,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self._refresh_process_table()

    # ── COMMAND CENTER TAB ─────────────────────────────────────
    def _build_command_center_tab(self, parent):
        self._reminders: list[dict] = []
        self._tasks_path = Path(__file__).resolve().parent / "jarvis_tasks.json"
        self._tasks: list[dict] = self._load_tasks()

        wrapper = tk.Frame(parent, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=14, pady=14)
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(0, weight=1)

        left = tk.Frame(wrapper, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right = tk.Frame(wrapper, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)

        # Calendar
        cal_card = HudCard(left, "CALENDAR", "Today, upcoming, and add new events")
        cal_card.pack(fill="x", pady=(0, 12))
        cal_card.body.columnconfigure(1, weight=1)

        self.cal_month_var = tk.StringVar(value=datetime.datetime.now().strftime("%B %Y"))
        tk.Label(cal_card.body, textvariable=self.cal_month_var, fg=GOLD, bg=BG_PANEL, font=FONT_TITLE).grid(row=0, column=0, sticky="w")
        tk.Button(
            cal_card.body,
            text="REFRESH",
            command=self._refresh_calendar_views,
            bg=BG_INPUT,
            fg=CYAN,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="e")

        self.cal_grid = tk.Frame(cal_card.body, bg=BG_PANEL)
        self.cal_grid.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        self._build_month_grid(self.cal_grid)

        self.today_events_label = tk.Label(cal_card.body, text="Today's events: …", fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL, justify="left", wraplength=520)
        self.today_events_label.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.upcoming_events_label = tk.Label(cal_card.body, text="Upcoming (7 days): …", fg=TEXT_FAINT, bg=BG_PANEL, font=FONT_SMALL, justify="left", wraplength=520)
        self.upcoming_events_label.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        add_row = tk.Frame(cal_card.body, bg=BG_PANEL)
        add_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        add_row.columnconfigure((0, 1, 2, 3), weight=1)
        self.add_event_title = tk.Entry(add_row, bg=BG_INPUT, fg=TEXT, insertbackground=GOLD, relief="flat", bd=0, font=FONT_SMALL)
        self.add_event_date = tk.Entry(add_row, bg=BG_INPUT, fg=TEXT, insertbackground=GOLD, relief="flat", bd=0, font=FONT_SMALL)
        self.add_event_time = tk.Entry(add_row, bg=BG_INPUT, fg=TEXT, insertbackground=GOLD, relief="flat", bd=0, font=FONT_SMALL)
        self.add_event_title.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.add_event_date.grid(row=0, column=1, sticky="ew", padx=3)
        self.add_event_time.grid(row=0, column=2, sticky="ew", padx=3)
        self.add_event_date.insert(0, datetime.date.today().isoformat())
        self.add_event_time.insert(0, "10:00")
        tk.Button(
            add_row,
            text="ADD",
            command=self._add_calendar_event,
            bg=GOLD,
            fg=BG,
            activebackground=GOLD_SOFT,
            activeforeground=BG,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        # Notes
        notes_card = HudCard(right, "NOTES", "Add, search, and delete notes")
        notes_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        notes_card.body.columnconfigure(0, weight=1)

        search_row = tk.Frame(notes_card.body, bg=BG_PANEL)
        search_row.pack(fill="x", pady=(0, 8))
        search_row.columnconfigure(0, weight=1)
        self.notes_search = tk.Entry(search_row, bg=BG_INPUT, fg=TEXT, insertbackground=GOLD, relief="flat", bd=0, font=FONT_SMALL)
        self.notes_search.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=4)
        tk.Button(
            search_row,
            text="SEARCH",
            command=self._refresh_notes_list,
            bg=BG_INPUT,
            fg=CYAN,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=1)

        self.notes_list = tk.Listbox(
            notes_card.body,
            bg=BG_INPUT,
            fg=TEXT,
            selectbackground=GOLD_DIM,
            selectforeground="#fff2ee",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            font=FONT_SMALL,
            height=8,
        )
        self.notes_list.pack(fill="x")

        add_note_row = tk.Frame(notes_card.body, bg=BG_PANEL)
        add_note_row.pack(fill="x", pady=(10, 0))
        add_note_row.columnconfigure(0, weight=1)
        self.add_note_entry = tk.Entry(add_note_row, bg=BG_INPUT, fg=TEXT, insertbackground=GOLD, relief="flat", bd=0, font=FONT_SMALL)
        self.add_note_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=5)
        tk.Button(
            add_note_row,
            text="SAVE",
            command=self._add_note,
            bg=GOLD,
            fg=BG,
            activebackground=GOLD_SOFT,
            activeforeground=BG,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="ew")
        tk.Button(
            add_note_row,
            text="DELETE",
            command=self._delete_selected_note,
            bg=BG_INPUT,
            fg=RED,
            activebackground=RED_SOFT,
            activeforeground="#fff2ee",
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        # Reminders
        rem_card = HudCard(right, "REMINDERS", "Active reminders with countdown")
        rem_card.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        rem_card.body.columnconfigure(0, weight=1)
        self.rem_list = tk.Listbox(
            rem_card.body,
            bg=BG_INPUT,
            fg=TEXT,
            selectbackground=RED_SOFT,
            selectforeground="#fff2ee",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            font=FONT_SMALL,
            height=6,
        )
        self.rem_list.pack(fill="x")
        rem_row = tk.Frame(rem_card.body, bg=BG_PANEL)
        rem_row.pack(fill="x", pady=(10, 0))
        rem_row.columnconfigure(0, weight=1)
        self.rem_text_entry = tk.Entry(rem_row, bg=BG_INPUT, fg=TEXT, insertbackground=GOLD, relief="flat", bd=0, font=FONT_SMALL)
        self.rem_minutes_entry = tk.Entry(rem_row, bg=BG_INPUT, fg=TEXT, insertbackground=GOLD, relief="flat", bd=0, font=FONT_SMALL, width=6)
        self.rem_text_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=5)
        self.rem_minutes_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6), ipady=5)
        self.rem_minutes_entry.insert(0, "5")
        tk.Button(
            rem_row,
            text="SET",
            command=self._set_reminder_from_ui,
            bg=GOLD,
            fg=BG,
            activebackground=GOLD_SOFT,
            activeforeground=BG,
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=2, sticky="ew")
        tk.Button(
            rem_row,
            text="CANCEL",
            command=self._cancel_selected_reminder,
            bg=BG_INPUT,
            fg=RED,
            activebackground=RED_SOFT,
            activeforeground="#fff2ee",
            relief="flat",
            bd=0,
            padx=10,
            pady=6,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        # Quick tasks
        tasks_card = HudCard(right, "QUICK TASKS", "Checklist (persists between sessions)")
        tasks_card.grid(row=2, column=0, sticky="nsew")
        tasks_card.body.rowconfigure(1, weight=1)
        tasks_card.body.columnconfigure(0, weight=1)

        self.tasks_list = tk.Listbox(
            tasks_card.body,
            bg=BG_INPUT,
            fg=TEXT,
            selectbackground=GOLD_DIM,
            selectforeground="#fff2ee",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            font=FONT_SMALL,
            height=10,
        )
        self.tasks_list.grid(row=0, column=0, sticky="nsew")

        task_row = tk.Frame(tasks_card.body, bg=BG_PANEL)
        task_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        task_row.columnconfigure(0, weight=1)
        self.task_entry = tk.Entry(task_row, bg=BG_INPUT, fg=TEXT, insertbackground=GOLD, relief="flat", bd=0, font=FONT_SMALL)
        self.task_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=5)
        tk.Button(task_row, text="ADD", command=self._add_task, bg=GOLD, fg=BG, activebackground=GOLD_SOFT, activeforeground=BG,
                  relief="flat", bd=0, padx=10, pady=6, font=FONT_SMALL, cursor="hand2").grid(row=0, column=1, padx=(0, 6))
        tk.Button(task_row, text="TOGGLE", command=self._toggle_task_done, bg=BG_INPUT, fg=CYAN, activebackground=CYAN_DIM, activeforeground=TEXT,
                  relief="flat", bd=0, padx=10, pady=6, font=FONT_SMALL, cursor="hand2").grid(row=0, column=2, padx=(0, 6))
        tk.Button(task_row, text="DELETE", command=self._delete_task, bg=BG_INPUT, fg=RED, activebackground=RED_SOFT, activeforeground="#fff2ee",
                  relief="flat", bd=0, padx=10, pady=6, font=FONT_SMALL, cursor="hand2").grid(row=0, column=3)

        self._refresh_calendar_views()
        self._refresh_notes_list()
        self._refresh_tasks_list()
        self._start_reminder_loop()

    def _build_month_grid(self, parent):
        for child in parent.winfo_children():
            child.destroy()
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, d in enumerate(days):
            tk.Label(parent, text=d, fg=TEXT_FAINT, bg=BG_PANEL, font=FONT_SMALL).grid(row=0, column=i, padx=2, pady=2)
            parent.columnconfigure(i, weight=1)
        for r in range(1, 7):
            parent.rowconfigure(r, weight=1)
            for c in range(7):
                lbl = tk.Label(parent, text="", fg=TEXT, bg=BG_INPUT, font=FONT_SMALL, width=4)
                lbl.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
                lbl._date = None
                lbl.bind("<Button-1>", lambda e, w=lbl: self._on_calendar_day_click(w))
        self._render_month_grid()

    def _render_month_grid(self):
        now = datetime.date.today()
        year, month = now.year, now.month
        self.cal_month_var.set(datetime.date(year, month, 1).strftime("%B %Y"))
        cal = pycalendar.Calendar(firstweekday=0)  # Monday
        month_days = list(cal.itermonthdates(year, month))
        # events by day
        events = getattr(self.jarvis.calendar, "events", [])
        event_days = set()
        for ev in events:
            try:
                event_days.add(ev.get("date", ""))
            except Exception:
                pass

        cells = [w for w in self.cal_grid.winfo_children() if hasattr(w, "_date")]
        for i, cell in enumerate(cells):
            d = month_days[i] if i < len(month_days) else None
            if not d:
                cell.configure(text="", bg=BG_INPUT)
                cell._date = None
                continue
            date_str = d.isoformat()
            cell._date = date_str
            in_month = (d.month == month)
            has_event = date_str in event_days
            txt = str(d.day) + (" •" if has_event else "")
            cell.configure(
                text=txt,
                fg=TEXT if in_month else TEXT_FAINT,
                bg=BG_PANEL_ALT if date_str == datetime.date.today().isoformat() else BG_INPUT,
            )

    def _on_calendar_day_click(self, widget):
        date_str = getattr(widget, "_date", None)
        if not date_str:
            return
        self.add_event_date.delete(0, "end")
        self.add_event_date.insert(0, date_str)

    def _refresh_calendar_views(self):
        try:
            today_txt = self.jarvis.calendar.today()
            upcoming_txt = self.jarvis.calendar.upcoming(7)
        except Exception as e:
            today_txt = f"Calendar error: {e}"
            upcoming_txt = ""
        self.today_events_label.configure(text=today_txt)
        self.upcoming_events_label.configure(text=upcoming_txt)
        self._render_month_grid()

        # Auto-refresh (single scheduled job) so Command Center stays live.
        try:
            if self._calendar_job is not None:
                self.root.after_cancel(self._calendar_job)
        except Exception:
            pass
        try:
            self._calendar_job = self.root.after(300000, self._refresh_calendar_views)  # 5 minutes
        except Exception:
            self._calendar_job = None

    def _add_calendar_event(self):
        title = self.add_event_title.get().strip()
        date_str = self.add_event_date.get().strip()
        tstr = self.add_event_time.get().strip()
        if not title or not date_str:
            self.toasts.show("Title and date required.", "warning")
            return
        try:
            resp = self.jarvis.calendar.add(title, date_str, tstr or "00:00")
            self._emit_event("system", resp)
            self.add_event_title.delete(0, "end")
            self._refresh_calendar_views()
        except Exception as e:
            self._log("JARVIS", f"Add event failed: {e}", "error")

    def _refresh_notes_list(self):
        q = (self.notes_search.get() or "").strip().lower()
        notes = getattr(self.jarvis.notes, "notes", []) or []
        self.notes_list.delete(0, "end")
        for n in reversed(notes[-200:]):
            text = str(n.get("text", "")).strip()
            ts = str(n.get("time", "")).strip()
            if q and q not in text.lower():
                continue
            label = f"{ts} — {text[:60]}"
            self.notes_list.insert("end", label)

    def _add_note(self):
        content = self.add_note_entry.get().strip()
        if not content:
            return
        try:
            resp = self.jarvis.notes.add(content)
            self._emit_event("system", resp)
            self.add_note_entry.delete(0, "end")
            self._refresh_notes_list()
        except Exception as e:
            self._log("JARVIS", f"Note save failed: {e}", "error")

    def _delete_selected_note(self):
        sel = self.notes_list.curselection()
        if not sel:
            return
        # map selection back to actual note by time/text prefix
        label = self.notes_list.get(sel[0])
        notes = getattr(self.jarvis.notes, "notes", []) or []
        try:
            # find matching note
            ts = label.split(" — ", 1)[0].strip()
            prefix = label.split(" — ", 1)[1].strip()
            idx = None
            for i, n in enumerate(notes):
                if str(n.get("time", "")).strip() == ts and str(n.get("text", "")).strip().startswith(prefix.split()[0]):
                    idx = i
            if idx is None:
                # fallback: delete last note
                idx = len(notes) - 1
            if idx >= 0:
                notes.pop(idx)
                # persist via module save
                self.jarvis.notes._save()
                self._emit_event("system", "Note deleted.")
                self._refresh_notes_list()
        except Exception as e:
            self._log("JARVIS", f"Delete failed: {e}", "error")

    def _set_reminder_from_ui(self):
        text = self.rem_text_entry.get().strip()
        mins = self.rem_minutes_entry.get().strip()
        if not text:
            return
        try:
            minutes = max(1, int(mins))
        except Exception:
            minutes = 5
        end = time.time() + minutes * 60
        self._reminders.append({"text": text, "end": end, "cancelled": False})
        self.rem_text_entry.delete(0, "end")
        self._emit_event("system", f"Reminder set: {text} ({minutes} min)")

    def _cancel_selected_reminder(self):
        sel = self.rem_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self._reminders):
            return
        self._reminders[idx]["cancelled"] = True
        self._emit_event("system", "Reminder cancelled.")

    def _start_reminder_loop(self):
        def tick():
            now = time.time()
            alive = []
            self.rem_list.delete(0, "end")
            for r in self._reminders:
                if r.get("cancelled"):
                    continue
                remaining = int(r["end"] - now)
                if remaining <= 0:
                    msg = f"Reminder: {r['text']}"
                    self._log("JARVIS", msg)
                    self._safe_speak(msg)
                    continue
                alive.append(r)
                mm, ss = divmod(remaining, 60)
                self.rem_list.insert("end", f"{mm:02d}:{ss:02d}  {r['text']}")
            self._reminders = alive
            self.root.after(1000, tick)
        self.root.after(500, tick)

    def _load_tasks(self) -> list[dict]:
        try:
            if self._tasks_path.exists():
                return json.loads(self._tasks_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def _save_tasks(self):
        try:
            self._tasks_path.write_text(json.dumps(self._tasks, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _refresh_tasks_list(self):
        self.tasks_list.delete(0, "end")
        for t in self._tasks:
            mark = "✓" if t.get("done") else "•"
            self.tasks_list.insert("end", f"{mark} {t.get('text','')}")

    def _add_task(self):
        text = self.task_entry.get().strip()
        if not text:
            return
        self._tasks.append({"text": text, "done": False, "created": datetime.datetime.now().isoformat(timespec="seconds")})
        self.task_entry.delete(0, "end")
        self._save_tasks()
        self._refresh_tasks_list()

    def _toggle_task_done(self):
        sel = self.tasks_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self._tasks):
            self._tasks[idx]["done"] = not bool(self._tasks[idx].get("done"))
            self._save_tasks()
            self._refresh_tasks_list()

    def _delete_task(self):
        sel = self.tasks_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self._tasks):
            self._tasks.pop(idx)
            self._save_tasks()
            self._refresh_tasks_list()

    # ── SECURITY TAB ───────────────────────────────────────────
    def _build_security_tab(self, parent):
        wrapper = tk.Frame(parent, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=14, pady=14)
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(1, weight=1)

        net = HudCard(wrapper, "NETWORK INTELLIGENCE", "Public/local IP, ISP, connections, ping")
        net.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(0, 12))
        net.body.columnconfigure(1, weight=1)

        self.net_summary = tk.Label(net.body, text="Loading network info…", fg=TEXT, bg=BG_PANEL, font=FONT_SMALL, justify="left", wraplength=520)
        self.net_summary.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.net_conn_list = tk.Listbox(net.body, bg=BG_INPUT, fg=TEXT, font=("JetBrains Mono", 9),
                                        selectbackground=GOLD_DIM, relief="flat", bd=0, highlightthickness=0, height=8)
        self.net_conn_list.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        net_btns = tk.Frame(net.body, bg=BG_PANEL)
        net_btns.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        net_btns.columnconfigure((0, 1, 2), weight=1)
        tk.Button(net_btns, text="PING GOOGLE", command=self._ping_google, bg=BG_INPUT, fg=CYAN,
                  activebackground=CYAN_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8,
                  font=FONT_SMALL, cursor="hand2").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Button(net_btns, text="REFRESH", command=self._refresh_security_panels, bg=BG_INPUT, fg=GOLD,
                  activebackground=GOLD_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8,
                  font=FONT_SMALL, cursor="hand2").grid(row=0, column=1, sticky="ew", padx=3)
        tk.Button(net_btns, text="PORT SCAN", command=self._port_scan_common, bg=BG_INPUT, fg=ORANGE,
                  activebackground=CYAN_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8,
                  font=FONT_SMALL, cursor="hand2").grid(row=0, column=2, sticky="ew", padx=(6, 0))

        syssec = HudCard(wrapper, "SYSTEM SECURITY", "Processes, flags, and basic signals")
        syssec.grid(row=0, column=1, sticky="ew", pady=(0, 12))
        syssec.body.columnconfigure(0, weight=1)
        self.sec_proc_list = tk.Listbox(syssec.body, bg=BG_INPUT, fg=TEXT, font=("JetBrains Mono", 9),
                                        selectbackground=RED_SOFT, relief="flat", bd=0, highlightthickness=0, height=10)
        self.sec_proc_list.grid(row=0, column=0, sticky="ew")
        self.sec_status = tk.Label(syssec.body, text="Defender status: (not wired)", fg=TEXT_FAINT, bg=BG_PANEL, font=FONT_SMALL, justify="left")
        self.sec_status.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        fs = HudCard(wrapper, "FILE SYSTEM", "Quick folders + recently modified files")
        fs.grid(row=1, column=0, columnspan=2, sticky="nsew")
        fs.body.columnconfigure(0, weight=1)
        fs.body.rowconfigure(1, weight=1)

        quick = tk.Frame(fs.body, bg=BG_PANEL)
        quick.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        for i in range(4):
            quick.columnconfigure(i, weight=1)
        tk.Button(quick, text="DESKTOP", command=lambda: self._open_folder(Path.home() / "Desktop"), bg=BG_INPUT, fg=CYAN,
                  activebackground=CYAN_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8, font=FONT_SMALL, cursor="hand2").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Button(quick, text="DOWNLOADS", command=lambda: self._open_folder(Path.home() / "Downloads"), bg=BG_INPUT, fg=CYAN,
                  activebackground=CYAN_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8, font=FONT_SMALL, cursor="hand2").grid(row=0, column=1, sticky="ew", padx=3)
        tk.Button(quick, text="DOCUMENTS", command=lambda: self._open_folder(Path.home() / "Documents"), bg=BG_INPUT, fg=CYAN,
                  activebackground=CYAN_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8, font=FONT_SMALL, cursor="hand2").grid(row=0, column=2, sticky="ew", padx=3)
        tk.Button(quick, text="PHOTOS", command=lambda: self._open_folder(PHOTOS_DIR), bg=BG_INPUT, fg=CYAN,
                  activebackground=CYAN_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8, font=FONT_SMALL, cursor="hand2").grid(row=0, column=3, sticky="ew", padx=(6, 0))

        self.recent_files = scrolledtext.ScrolledText(fs.body, bg=BG_INPUT, fg=TEXT, relief="flat", bd=0, wrap="word",
                                                      state="disabled", insertbackground=GOLD, font=FONT_SMALL)
        self.recent_files.grid(row=1, column=0, sticky="nsew")

        self._refresh_security_panels()

    def _open_folder(self, path: Path):
        try:
            self.jarvis.system.open_file(str(path))
        except Exception:
            try:
                import os
                os.startfile(str(path))
            except Exception:
                pass

    def _ping_google(self):
        def worker():
            try:
                # Windows ping
                out = subprocess.check_output(["ping", "-n", "1", "google.com"], text=True, timeout=6, encoding="utf-8", errors="ignore")
                m = re.search(r"time[=<]\\s*(\\d+)ms", out)
                latency = f"{m.group(1)}ms" if m else "unknown"
                self.root.after(0, lambda: self.toasts.show(f"Ping: {latency}", "info"))
                self.root.after(0, lambda: self._emit_event("system", f"Ping google.com: {latency}"))
            except Exception as e:
                self.root.after(0, lambda: self.toasts.show(f"Ping failed: {e}", "warning"))
        threading.Thread(target=worker, daemon=True).start()

    def _port_scan_common(self):
        def worker():
            try:
                target = "127.0.0.1"
                ports = [21, 22, 23, 53, 80, 135, 139, 443, 445, 3389]
                open_ports = []
                for p in ports:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.25)
                    try:
                        if s.connect_ex((target, p)) == 0:
                            open_ports.append(p)
                    finally:
                        s.close()
                msg = "Open ports: " + (", ".join(map(str, open_ports)) if open_ports else "none detected")
                self.root.after(0, lambda: self._emit_event("system", msg))
                self.root.after(0, lambda: self.toasts.show(msg, "info", 2600))
            except Exception as e:
                self.root.after(0, lambda: self.toasts.show(f"Port scan failed: {e}", "warning"))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_security_panels(self):
        """Run heavy security data collection off the main thread."""
        if getattr(self, 'locked', False):
            return
        def _worker():
            result = {}
            # Network info
            try:
                d = self.jarvis.location.get() if hasattr(self.jarvis, "location") else {}
                local_ip = ""
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("8.8.8.8", 80))
                    local_ip = s.getsockname()[0]
                    s.close()
                except Exception:
                    local_ip = socket.gethostbyname(socket.gethostname())
                result["net"] = (
                    f"Public IP: {d.get('ip','')}\nLocal IP: {local_ip}\n"
                    f"ISP: {d.get('isp','')}\nLocation: {d.get('city','')}, "
                    f"{d.get('region','')}, {d.get('country','')}"
                )
            except Exception as e:
                result["net"] = f"Network info error: {e}"

            # Connections
            try:
                conns = psutil.net_connections(kind="inet")
                result["conns"] = [
                    f"{c.status:<12} {(str(c.laddr.ip)+':'+str(c.laddr.port)) if c.laddr else '-':<22}"
                    f" -> {(str(c.raddr.ip)+':'+str(c.raddr.port)) if c.raddr else '-':<22} pid={c.pid}"
                    for c in conns[:25]
                ]
            except Exception as e:
                result["conns"] = [f"Connections error: {e}"]

            # Processes
            try:
                procs = []
                for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
                    try:
                        procs.append(p.info)
                    except Exception:
                        pass
                procs.sort(key=lambda x: float(x.get("cpu_percent") or 0), reverse=True)
                result["procs"] = [
                    f"{info.get('pid',''):>6}  {float(info.get('cpu_percent') or 0):>5.1f}%  "
                    f"{(info.get('name') or '')[:18]}"
                    f"{' !' if float(info.get('cpu_percent') or 0) > 60 else ''}"
                    for info in procs[:25]
                ]
            except Exception as e:
                result["procs"] = [f"Process scan error: {e}"]

            # Recent files: non-recursive for speed
            try:
                roots = [Path.home() / "Desktop", Path.home() / "Downloads", Path.home() / "Documents"]
                items = []
                for r in roots:
                    if not r.exists():
                        continue
                    try:
                        for p in r.glob("*"):
                            if p.is_file():
                                items.append((p.stat().st_mtime, p))
                    except Exception:
                        continue
                items.sort(key=lambda x: x[0], reverse=True)
                result["files"] = "\n".join(
                    f"{datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')}  {p.name}  [{short_path(str(p), 80)}]"
                    for ts, p in items[:20]
                ) or "No recent files found."
            except Exception as e:
                result["files"] = f"Recent files error: {e}"

            # Windows Defender status (best-effort)
            try:
                if platform.system().lower() == "windows":
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
                    result["defender"] = f"Defender: AV {av} | RTP {rtp}"
                else:
                    result["defender"] = "Defender status: unavailable on non-Windows."
            except Exception as e:
                result["defender"] = f"Defender status unavailable: {e}"

            self._safe_after(0, lambda r=result: self._apply_security_data(r))

        threading.Thread(target=_worker, daemon=True).start()
        self._safe_after(int(getattr(self, "_security_interval_ms", 8000)), self._refresh_security_panels)

    def _apply_security_data(self, result: dict):
        try:
            self.net_summary.configure(text=result.get("net", ""))
            self.net_conn_list.delete(0, "end")
            for line in result.get("conns", []):
                self.net_conn_list.insert("end", line)
            self.sec_proc_list.delete(0, "end")
            for line in result.get("procs", []):
                self.sec_proc_list.insert("end", line)
            self.recent_files.configure(state="normal")
            self.recent_files.delete("1.0", "end")
            self.recent_files.insert("end", result.get("files", ""))
            self.recent_files.configure(state="disabled")
            try:
                self.sec_status.configure(text=result.get("defender", "Defender status: unavailable."))
            except Exception:
                pass
        except Exception:
            pass

    # ── SETTINGS TAB ───────────────────────────────────────────
    def _build_settings_tab(self, parent):
        self._cfg_path = Path(__file__).resolve().parent / "jarvis_config.json"
        self._settings_vars = {}

        wrapper = tk.Frame(parent, bg=BG)
        wrapper.pack(fill="both", expand=True, padx=14, pady=14)
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(1, weight=1)

        ai = HudCard(wrapper, "AI CONFIGURATION", "Keys, model, style")
        ai.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(0, 12))
        ai.body.columnconfigure(1, weight=1)

        self._settings_vars["openrouter_api_key"] = tk.StringVar(value=str(self.cfg.get("openrouter_api_key", "")))
        self._settings_vars["groq_api_key"] = tk.StringVar(value=str(self.cfg.get("groq_api_key", "")))
        self._settings_vars["openweather_api_key"] = tk.StringVar(value=str(self.cfg.get("openweather_api_key", "")))
        self._settings_vars["news_api_key"] = tk.StringVar(value=str(self.cfg.get("news_api_key", "")))
        self._settings_vars["openrouter_model"] = tk.StringVar(value=str(self.cfg.get("openrouter_model", "")))
        self._settings_vars["ai_style"] = tk.StringVar(value="Concise")
        self._settings_vars["temperature"] = tk.DoubleVar(value=float(self.cfg.get("temperature", 0.7) or 0.7))
        self._settings_vars["memory"] = tk.BooleanVar(value=bool(self.cfg.get("memory", True)))

        self._row_label_entry(ai.body, 0, "OpenRouter key", self._settings_vars["openrouter_api_key"], masked=True)
        self._row_label_entry(ai.body, 1, "Groq key", self._settings_vars["groq_api_key"], masked=True)
        self._row_label_entry(ai.body, 2, "OpenWeather key", self._settings_vars["openweather_api_key"], masked=True)
        self._row_label_entry(ai.body, 3, "NewsAPI key (optional)", self._settings_vars["news_api_key"], masked=True)

        # Model selector
        tk.Label(ai.body, text="Model", fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).grid(row=4, column=0, sticky="w", pady=4)
        models = []
        try:
            models = list(getattr(self.jarvis.ai, "FREE_MODELS", []) or [])
        except Exception:
            models = []
        if not models:
            models = ["openrouter/free"]
        model_menu = ttk.Combobox(ai.body, values=models, textvariable=self._settings_vars["openrouter_model"], state="readonly")
        model_menu.grid(row=4, column=1, sticky="ew", pady=4)

        tk.Label(ai.body, text="Response style", fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).grid(row=5, column=0, sticky="w", pady=4)
        style_menu = ttk.Combobox(ai.body, values=["Concise", "Detailed", "Custom"], textvariable=self._settings_vars["ai_style"], state="readonly")
        style_menu.grid(row=5, column=1, sticky="ew", pady=4)

        tk.Label(ai.body, text="Temperature", fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).grid(row=6, column=0, sticky="w", pady=4)
        temp = tk.Scale(ai.body, from_=0.0, to=1.2, resolution=0.05, orient="horizontal", variable=self._settings_vars["temperature"],
                        bg=BG_PANEL, fg=TEXT, troughcolor=BG_INPUT, highlightthickness=0)
        temp.grid(row=6, column=1, sticky="ew", pady=4)

        mem = tk.Checkbutton(ai.body, text="Conversation memory", variable=self._settings_vars["memory"], fg=GOLD, bg=BG_PANEL,
                             activebackground=BG_PANEL, selectcolor=BG_PANEL, font=FONT_SMALL, cursor="hand2")
        mem.grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))

        voice = HudCard(wrapper, "VOICE SETTINGS", "TTS controls + wake words")
        voice.grid(row=0, column=1, sticky="ew", pady=(0, 12))
        voice.body.columnconfigure(1, weight=1)
        self._settings_vars["tts_rate"] = tk.IntVar(value=int(self.cfg.get("tts_rate", 172) or 172))
        self._settings_vars["tts_volume"] = tk.DoubleVar(value=float(self.cfg.get("tts_volume", 0.95) or 0.95))
        self._settings_vars["wake_words"] = tk.StringVar(value=", ".join(self.cfg.get("wake_words", ["jarvis", "hey jarvis"])))

        tk.Label(voice.body, text="TTS rate", fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).grid(row=0, column=0, sticky="w", pady=4)
        tk.Scale(voice.body, from_=120, to=240, orient="horizontal", variable=self._settings_vars["tts_rate"], bg=BG_PANEL, fg=TEXT,
                 troughcolor=BG_INPUT, highlightthickness=0).grid(row=0, column=1, sticky="ew", pady=4)
        tk.Label(voice.body, text="TTS volume", fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).grid(row=1, column=0, sticky="w", pady=4)
        tk.Scale(voice.body, from_=0.1, to=1.0, resolution=0.05, orient="horizontal", variable=self._settings_vars["tts_volume"], bg=BG_PANEL,
                 fg=TEXT, troughcolor=BG_INPUT, highlightthickness=0).grid(row=1, column=1, sticky="ew", pady=4)
        self._row_label_entry(voice.body, 2, "Wake words", self._settings_vars["wake_words"], masked=False)
        tk.Button(voice.body, text="TEST VOICE", command=lambda: self._safe_speak(f"Systems online, {self.name}."), bg=BG_INPUT, fg=CYAN,
                  activebackground=CYAN_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8, font=FONT_SMALL, cursor="hand2").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        cam = HudCard(wrapper, "CAMERA SETTINGS", "Index, HUD mode, toggles")
        cam.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        cam.body.columnconfigure(1, weight=1)
        self._settings_vars["camera_index"] = tk.IntVar(value=int(self.cfg.get("camera_index", 0) or 0))
        self._settings_vars["hud_style"] = tk.StringVar(value=self.vision_mode.get())
        self._settings_vars["face_tracking"] = tk.BooleanVar(value=bool(self.face_tracking_var.get()))
        self._settings_vars["matrix_overlay"] = tk.BooleanVar(value=bool(self.matrix_overlay_var.get()))

        tk.Label(cam.body, text="Camera index", fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).grid(row=0, column=0, sticky="w", pady=4)
        tk.Spinbox(cam.body, from_=0, to=10, textvariable=self._settings_vars["camera_index"], bg=BG_INPUT, fg=TEXT, insertbackground=GOLD,
                   relief="flat", bd=0, font=FONT_SMALL, width=8).grid(row=0, column=1, sticky="w", pady=4)

        tk.Label(cam.body, text="HUD style", fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).grid(row=1, column=0, sticky="w", pady=4)
        hud_values = [VisionMode.MARK50, VisionMode.THERMAL, VisionMode.TRON, VisionMode.PREDATOR, VisionMode.NEURAL]
        hud_menu = ttk.Combobox(cam.body, values=hud_values, textvariable=self._settings_vars["hud_style"], state="readonly")
        hud_menu.grid(row=1, column=1, sticky="ew", pady=4)
        tk.Checkbutton(cam.body, text="Face tracking", variable=self._settings_vars["face_tracking"], fg=GOLD, bg=BG_PANEL,
                       activebackground=BG_PANEL, selectcolor=BG_PANEL, font=FONT_SMALL, cursor="hand2").grid(row=2, column=0, columnspan=2, sticky="w")
        tk.Checkbutton(cam.body, text="Matrix overlay", variable=self._settings_vars["matrix_overlay"], fg=GOLD, bg=BG_PANEL,
                       activebackground=BG_PANEL, selectcolor=BG_PANEL, font=FONT_SMALL, cursor="hand2").grid(row=3, column=0, columnspan=2, sticky="w")

        appearance = HudCard(wrapper, "APPEARANCE", "Theme placeholders (wired later)")
        appearance.grid(row=1, column=1, sticky="nsew")
        tk.Label(appearance.body, text="Theme selector, font size, orb size, opacity are placeholders here.", fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL, justify="left", wraplength=520).pack(anchor="w")

        syscard = tk.Frame(appearance.body, bg=BG_PANEL)
        syscard.pack(fill="x", pady=(12, 0))
        for i in range(4):
            syscard.columnconfigure(i, weight=1)
        tk.Button(syscard, text="EXPORT CONFIG", command=self._export_config, bg=BG_INPUT, fg=CYAN,
                  activebackground=CYAN_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8,
                  font=FONT_SMALL, cursor="hand2").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Button(syscard, text="IMPORT CONFIG", command=self._import_config, bg=BG_INPUT, fg=CYAN,
                  activebackground=CYAN_DIM, activeforeground=TEXT, relief="flat", bd=0, padx=10, pady=8,
                  font=FONT_SMALL, cursor="hand2").grid(row=0, column=1, sticky="ew", padx=3)
        tk.Button(syscard, text="SAVE", command=self._save_settings_to_config, bg=GOLD, fg=BG,
                  activebackground=GOLD_SOFT, activeforeground=BG, relief="flat", bd=0, padx=10, pady=8,
                  font=FONT_SMALL, cursor="hand2").grid(row=0, column=2, sticky="ew", padx=3)
        tk.Button(syscard, text="RESET", command=self._reset_settings, bg=BG_INPUT, fg=RED,
                  activebackground=RED_SOFT, activeforeground="#fff2ee", relief="flat", bd=0, padx=10, pady=8,
                  font=FONT_SMALL, cursor="hand2").grid(row=0, column=3, sticky="ew", padx=(6, 0))

    def _row_label_entry(self, parent, row: int, label: str, var: tk.Variable, masked: bool = False):
        tk.Label(parent, text=label, fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).grid(row=row, column=0, sticky="w", pady=4)
        show = "•" if masked else ""
        ent = tk.Entry(parent, textvariable=var, bg=BG_INPUT, fg=TEXT, insertbackground=GOLD, relief="flat", bd=0, font=FONT_SMALL, show=show)
        ent.grid(row=row, column=1, sticky="ew", pady=4)
        return ent

    def _save_settings_to_config(self):
        # Apply to runtime cfg + persist to jarvis_config.json.
        try:
            cfg = dict(self.cfg)
            cfg["openrouter_api_key"] = self._settings_vars["openrouter_api_key"].get().strip()
            cfg["groq_api_key"] = self._settings_vars["groq_api_key"].get().strip()
            cfg["openweather_api_key"] = self._settings_vars["openweather_api_key"].get().strip()
            cfg["news_api_key"] = self._settings_vars["news_api_key"].get().strip()
            cfg["openrouter_model"] = self._settings_vars["openrouter_model"].get().strip()
            cfg["tts_rate"] = int(self._settings_vars["tts_rate"].get())
            cfg["tts_volume"] = float(self._settings_vars["tts_volume"].get())
            cfg["wake_words"] = [w.strip() for w in self._settings_vars["wake_words"].get().split(",") if w.strip()]
            cfg["camera_index"] = int(self._settings_vars["camera_index"].get())
            cfg["temperature"] = float(self._settings_vars["temperature"].get())
            cfg["memory"] = bool(self._settings_vars["memory"].get())

            # Persist
            self._cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            self.cfg.update(cfg)
            self.jarvis.cfg.update(cfg)

            # Apply to modules live if possible
            try:
                if hasattr(self.jarvis, "weather"):
                    self.jarvis.weather.key = cfg.get("openweather_api_key", "")
                    self.jarvis.weather.enabled = bool(self.jarvis.weather.key)
                if hasattr(self.jarvis, "news"):
                    self.jarvis.news.key = cfg.get("news_api_key", "")
                    self.jarvis.news.enabled = bool(self.jarvis.news.key)
            except Exception:
                pass

            # Apply to voice engine live if possible
            try:
                self.jarvis.voice.cfg.update(cfg)
                if getattr(self.jarvis.voice, "engine", None):
                    self.jarvis.voice.engine.setProperty("rate", cfg["tts_rate"])
                    self.jarvis.voice.engine.setProperty("volume", cfg["tts_volume"])
            except Exception:
                pass

            # Apply to GUI toggles
            try:
                self.face_tracking_var.set(bool(self._settings_vars["face_tracking"].get()))
                self.matrix_overlay_var.set(bool(self._settings_vars["matrix_overlay"].get()))
                self._set_vision_mode(self._settings_vars["hud_style"].get())
            except Exception:
                pass

            self.toasts.show("Settings saved.", "success", 2200)
            self._emit_event("system", "Settings saved to jarvis_config.json")
        except Exception as e:
            self._log("JARVIS", f"Settings save failed: {e}", "error")

    def _export_config(self):
        try:
            path = filedialog.asksaveasfilename(title="Export config", defaultextension=".json", filetypes=[("JSON", "*.json")])
            if not path:
                return
            Path(path).write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
            self.toasts.show("Config exported.", "success", 2200)
        except Exception as e:
            self._log("JARVIS", f"Export failed: {e}", "error")

    def _import_config(self):
        try:
            path = filedialog.askopenfilename(title="Import config", filetypes=[("JSON", "*.json")])
            if not path:
                return
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.cfg.update(data)
                self.jarvis.cfg.update(data)
                self._cfg_path.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
                self._sync_settings_vars_from_cfg()
                self.toasts.show("Config imported.", "success", 2200)
        except Exception as e:
            self._log("JARVIS", f"Import failed: {e}", "error")

    def _reset_settings(self):
        # Light reset to current disk config or defaults.
        try:
            if self._cfg_path.exists():
                cfg = json.loads(self._cfg_path.read_text(encoding="utf-8"))
                if isinstance(cfg, dict):
                    self.cfg.update(cfg)
                    self.jarvis.cfg.update(cfg)
            self._sync_settings_vars_from_cfg()
            self.toasts.show("Settings reset (reload).", "info", 2200)
        except Exception as e:
            self._log("JARVIS", f"Reset failed: {e}", "error")

    def _sync_settings_vars_from_cfg(self):
        """Update Settings tab variables from current cfg + apply to runtime modules."""
        try:
            v = getattr(self, "_settings_vars", {}) or {}
            if "openrouter_api_key" in v:
                v["openrouter_api_key"].set(str(self.cfg.get("openrouter_api_key", "")))
            if "groq_api_key" in v:
                v["groq_api_key"].set(str(self.cfg.get("groq_api_key", "")))
            if "openweather_api_key" in v:
                v["openweather_api_key"].set(str(self.cfg.get("openweather_api_key", "")))
            if "news_api_key" in v:
                v["news_api_key"].set(str(self.cfg.get("news_api_key", "")))
            if "openrouter_model" in v:
                v["openrouter_model"].set(str(self.cfg.get("openrouter_model", "")))
            if "tts_rate" in v:
                v["tts_rate"].set(int(self.cfg.get("tts_rate", 172) or 172))
            if "tts_volume" in v:
                v["tts_volume"].set(float(self.cfg.get("tts_volume", 0.95) or 0.95))
            if "wake_words" in v:
                v["wake_words"].set(", ".join(self.cfg.get("wake_words", ["jarvis", "hey jarvis"])))
            if "camera_index" in v:
                v["camera_index"].set(int(self.cfg.get("camera_index", 0) or 0))
            if "temperature" in v:
                v["temperature"].set(float(self.cfg.get("temperature", 0.7) or 0.7))
            if "memory" in v:
                v["memory"].set(bool(self.cfg.get("memory", True)))

            # Apply to runtime modules best-effort
            try:
                if hasattr(self.jarvis, "weather"):
                    self.jarvis.weather.key = str(self.cfg.get("openweather_api_key", "")).strip()
                    self.jarvis.weather.enabled = bool(self.jarvis.weather.key)
                if hasattr(self.jarvis, "news"):
                    self.jarvis.news.key = str(self.cfg.get("news_api_key", "")).strip()
                    self.jarvis.news.enabled = bool(self.jarvis.news.key)
            except Exception:
                pass

            try:
                self.jarvis.voice.cfg.update(self.cfg)
                if getattr(self.jarvis.voice, "engine", None):
                    self.jarvis.voice.engine.setProperty("rate", int(self.cfg.get("tts_rate", 172) or 172))
                    self.jarvis.voice.engine.setProperty("volume", float(self.cfg.get("tts_volume", 0.95) or 0.95))
            except Exception:
                pass
        except Exception:
            pass

    def _build_topbar(self):
        bar = tk.Frame(self.root, bg=BG_PANEL_ALT, highlightthickness=1, highlightbackground=BORDER)
        bar.pack(fill="x", padx=18, pady=(18, 0))
        bar.columnconfigure(1, weight=1)
        bar.columnconfigure(3, weight=0)

        left = tk.Frame(bar, bg=BG_PANEL_ALT)
        left.grid(row=0, column=0, sticky="w", padx=16, pady=12)
        tk.Label(left, text="◈", fg=GOLD, bg=BG_PANEL_ALT, font=("Orbitron", 12, "bold")).pack(side="left", padx=(0, 8))
        tk.Label(left, text="J.A.R.V.I.S", fg=GOLD, bg=BG_PANEL_ALT, font=("Orbitron", 15, "bold")).pack(side="left")
        tk.Label(left, text="MISSION CONTROL", fg=TEXT_FAINT, bg=BG_PANEL_ALT, font=FONT_SMALL).pack(side="left", padx=(10, 0))

        middle = tk.Frame(bar, bg=BG_PANEL_ALT)
        middle.grid(row=0, column=1, sticky="ew")
        middle.columnconfigure(0, weight=1)

        status_frame = tk.Frame(middle, bg=BG_INPUT, highlightthickness=1, highlightbackground=BORDER)
        status_frame.grid(row=0, column=0, sticky="ew", padx=20)
        status_frame.columnconfigure(1, weight=1)
        self.status_dot = tk.Label(status_frame, text="●", fg=GOLD, bg=BG_INPUT, font=("Orbitron", 11, "bold"))
        self.status_dot.grid(row=0, column=0, padx=(10, 8), pady=8)
        self.status_label = tk.Label(status_frame, textvariable=self.status_text, fg=GOLD, bg=BG_INPUT, font=FONT_TITLE)
        self.status_label.grid(row=0, column=1, sticky="w")
        tk.Label(status_frame, textvariable=self.status_detail, fg=TEXT_DIM, bg=BG_INPUT, font=FONT_SMALL).grid(row=0, column=2, sticky="e", padx=(10, 12))

        right = tk.Frame(bar, bg=BG_PANEL_ALT)
        right.grid(row=0, column=2, sticky="e", padx=16)
        tk.Label(right, textvariable=self.clock_text, fg=GOLD, bg=BG_PANEL_ALT, font=("Orbitron", 14, "bold")).pack(anchor="e")
        tk.Label(right, textvariable=self.date_text, fg=TEXT_DIM, bg=BG_PANEL_ALT, font=FONT_SMALL).pack(anchor="e")

        # Performance modes: ECO / QUIET / DEFAULT
        modes = tk.Frame(bar, bg=BG_PANEL_ALT)
        modes.grid(row=0, column=3, sticky="e", padx=(0, 16))

        self._mode_buttons = {}
        for idx, (label, key) in enumerate([("ECO", "eco"), ("QUIET", "quiet"), ("DEFAULT", "default")]):
            btn = tk.Button(
                modes,
                text=label,
                command=lambda m=key: self._apply_perf_mode(m),
                bg=BG_INPUT,
                fg=TEXT,
                activebackground=CYAN_DIM,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                padx=12,
                pady=8,
                font=FONT_SMALL,
                cursor="hand2",
            )
            btn.grid(row=0, column=idx, padx=(0, 8) if idx < 2 else 0)
            self._mode_buttons[key] = btn
        self._sync_perf_mode_buttons()

    def _sync_perf_mode_buttons(self):
        cur = self._perf_mode.get()
        for key, btn in getattr(self, "_mode_buttons", {}).items():
            try:
                apply_button_style(btn, "primary" if key == cur else "ghost")
                enhance_hud_button(btn)
            except Exception:
                pass

    def _apply_perf_mode(self, mode: str, log: bool = True):
        mode = (mode or "default").strip().lower()
        if mode not in ("default", "quiet", "eco"):
            mode = "default"
        self._perf_mode.set(mode)
        self._sync_perf_mode_buttons()

        # Defaults
        self._metrics_interval_ms = 2500
        self._analytics_interval_ms = 2000
        self._security_interval_ms = 8000
        self._wifi_interval_ms = 5000
        self._news_interval_ms = 600000

        if mode == "quiet":
            try:
                self.speak_reply_var.set(False)
            except Exception:
                pass
        elif mode == "eco":
            self._metrics_interval_ms = 6000
            self._analytics_interval_ms = 6000
            self._security_interval_ms = 15000
            self._wifi_interval_ms = 12000
            self._news_interval_ms = 900000
            try:
                self.speak_reply_var.set(False)
            except Exception:
                pass

        # Restart loops that use after() timers (best-effort).
        try:
            if getattr(self, "_analytics_job", None) is not None:
                self.root.after_cancel(self._analytics_job)
                self._analytics_job = None
        except Exception:
            pass
        try:
            if getattr(self, "_wifi_job", None) is not None:
                self.root.after_cancel(self._wifi_job)
                self._wifi_job = None
        except Exception:
            pass

        try:
            self._start_wifi_signal_loop()
        except Exception:
            pass
        try:
            self._start_analytics_loop()
        except Exception:
            pass

        if log:
            self._log_system(f"Performance mode: {mode.upper()}")

    def _build_left_column(self, parent):
        system_card = HudCard(parent, "SYSTEM STATE", "Live hardware and battery metrics")
        system_card.pack(fill="x", pady=(0, 12))

        self.cpu_bar = MetricBar(system_card.body, "CPU", CYAN)
        self.cpu_bar.pack(fill="x", pady=(0, 8))
        self.ram_bar = MetricBar(system_card.body, "RAM", ORANGE)
        self.ram_bar.pack(fill="x", pady=(0, 8))
        self.disk_bar = MetricBar(system_card.body, "DISK", GREEN)
        self.disk_bar.pack(fill="x", pady=(0, 8))
        self.battery_bar = MetricBar(system_card.body, "BATTERY", "#f1c84b")
        self.battery_bar.pack(fill="x", pady=(0, 10))

        self.system_detail = tk.Label(
            system_card.body,
            text="Gathering telemetry...",
            fg=TEXT_DIM,
            bg=BG_PANEL,
            justify="left",
            font=FONT_SMALL,
        )
        self.system_detail.pack(anchor="w")

        self.thermal_detail = tk.Label(
            system_card.body,
            text="Thermals pending...",
            fg=CYAN,
            bg=BG_PANEL,
            justify="left",
            wraplength=300,
            font=FONT_SMALL,
        )
        self.thermal_detail.pack(anchor="w", pady=(8, 0))

        thermal_controls = tk.Frame(system_card.body, bg=BG_PANEL)
        thermal_controls.pack(fill="x", pady=(10, 0))
        thermal_controls.columnconfigure((0, 1), weight=1)

        tk.Button(
            thermal_controls,
            text="THERMALS",
            command=lambda: self._queue_command("thermal status"),
            bg=BG_INPUT,
            fg=TEXT,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=8,
            pady=6,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        tk.Button(
            thermal_controls,
            text="HP COOLING",
            command=lambda: self._queue_command("open omen gaming hub"),
            bg=BG_INPUT,
            fg=TEXT,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=8,
            pady=6,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        weather_card = HudCard(parent, "WEATHER", "Pulled from your configured OpenWeather setup")
        weather_card.pack(fill="x", pady=(0, 12))
        weather_card.body.columnconfigure(1, weight=1)
        self.weather_temp = tk.Label(weather_card.body, text="--", fg=TEXT, bg=BG_PANEL, font=FONT_HUGE)
        self.weather_temp.grid(row=0, column=0, sticky="w")
        tk.Button(
            weather_card.body,
            text="REFRESH",
            command=lambda: self._refresh_weather(manual=True),
            bg=BG_INPUT,
            fg=CYAN,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="e")
        self.weather_label = tk.Label(
            weather_card.body,
            textvariable=self.weather_summary,
            fg=TEXT_DIM,
            bg=BG_PANEL,
            justify="left",
            wraplength=255,
            font=FONT_SMALL,
        )
        self.weather_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        news_card = HudCard(parent, "NEWS", "Live headlines · NewsAPI (if key set) or Google News RSS fallback")
        news_card.pack(fill="x", pady=(0, 12))
        news_card.body.columnconfigure(1, weight=1)
        tk.Label(news_card.body, text="Top headlines", fg=TEXT, bg=BG_PANEL, font=FONT_TITLE).grid(row=0, column=0, sticky="w")
        tk.Button(
            news_card.body,
            text="REFRESH",
            command=lambda: self._refresh_news(manual=True),
            bg=BG_INPUT,
            fg=CYAN,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="e")
        self.news_label = tk.Label(
            news_card.body,
            textvariable=self.news_summary,
            fg=TEXT_DIM,
            bg=BG_PANEL,
            justify="left",
            wraplength=255,
            font=FONT_SMALL,
        )
        self.news_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        quick_card = HudCard(parent, "QUICK ACTIONS", "Shortcut commands that still use your existing backend")
        quick_card.pack(fill="x", pady=(0, 12))

        actions = [
            ("SYSTEM REPORT", lambda: self._queue_command("system status")),
            ("CHECK EMAIL", lambda: self._queue_command("check my emails")),
            ("NEWS", lambda: self._queue_command("top news today")),
            ("WEATHER", lambda: self._queue_command("what's the weather")),
            ("READ NOTES", lambda: self._queue_command("read my notes")),
            ("TODAY", lambda: self._queue_command("today's schedule")),
            ("SCREENSHOT", lambda: self._queue_command("take a screenshot")),
            ("LOCK", lambda: self._queue_command("lock screen")),
        ]
        for index, (label, command) in enumerate(actions):
            row = index // 2
            col = index % 2
            btn = tk.Button(
                quick_card.body,
                text=label,
                command=command,
                bg=BG_INPUT,
                fg=TEXT,
                activebackground=CYAN_DIM,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                padx=8,
                pady=8,
                font=FONT_SMALL,
                cursor="hand2",
            )
            btn.grid(row=row, column=col, sticky="ew", padx=(0, 8) if col == 0 else 0, pady=(0, 8))
            quick_card.body.columnconfigure(col, weight=1)

        camera_card = HudCard(parent, "CAMERA", "Embedded live feed with face tracking and Matrix HUD")
        camera_card.pack(fill="both", expand=True)

        preview_frame = tk.Frame(camera_card.body, bg="#020507", width=CAMERA_SIZE[0], height=CAMERA_SIZE[1])
        preview_frame.pack(fill="x")
        preview_frame.pack_propagate(False)

        self.camera_label = tk.Label(preview_frame, bg="#020507", fg=TEXT_DIM, text="Camera offline", font=FONT_SMALL)
        self.camera_label.pack(fill="both", expand=True)

        tk.Label(camera_card.body, textvariable=self.camera_summary, fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL, justify="left", wraplength=280).pack(anchor="w", pady=(10, 6))

        self.camera_lock_label = tk.Label(
            camera_card.body,
            text="Face lock idle.",
            fg=TEXT_FAINT,
            bg=BG_PANEL,
            font=FONT_SMALL,
        )
        self.camera_lock_label.pack(anchor="w", pady=(0, 8))

        cam_controls = tk.Frame(camera_card.body, bg=BG_PANEL)
        cam_controls.pack(fill="x")
        cam_controls.columnconfigure((0, 1, 2), weight=1)

        self.camera_toggle_btn = tk.Button(
            cam_controls,
            text="START CAM",
            command=self._toggle_camera,
            bg=BG_INPUT,
            fg=CYAN,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=8,
            pady=8,
            font=FONT_SMALL,
            cursor="hand2",
        )
        self.camera_toggle_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        tk.Button(
            cam_controls,
            text="SNAP",
            command=self._capture_live_frame,
            bg=BG_INPUT,
            fg=TEXT,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=8,
            pady=8,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="ew", padx=3)

        tk.Button(
            cam_controls,
            text="USE AS REF",
            command=self._use_live_frame_as_reference,
            bg=BG_INPUT,
            fg=TEXT,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=8,
            pady=8,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        tk.Button(
            camera_card.body,
            text="ANALYZE LIVE FRAME",
            command=self._analyze_live_frame,
            bg=CYAN_DIM,
            fg=TEXT,
            activebackground=CYAN_SOFT,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            font=FONT_SMALL,
            cursor="hand2",
        ).pack(fill="x", pady=(10, 0))

        camera_toggles = tk.Frame(camera_card.body, bg=BG_PANEL)
        camera_toggles.pack(fill="x", pady=(10, 0))
        camera_toggles.columnconfigure((0, 1), weight=1)

        self._build_toggle(camera_toggles, "FACE TRACKING", self.face_tracking_var).grid(row=0, column=0, sticky="w")
        self._build_toggle(camera_toggles, "MATRIX HUD", self.matrix_overlay_var).grid(row=0, column=1, sticky="w")

        # Vision modes
        mode_wrap = tk.Frame(camera_card.body, bg=BG_PANEL)
        mode_wrap.pack(fill="x", pady=(10, 0))
        for idx in range(5):
            mode_wrap.columnconfigure(idx, weight=1)

        self._vision_mode_buttons: dict[str, tk.Button] = {}
        for idx, mode in enumerate(VisionMode.ORDER):
            btn = tk.Button(
                mode_wrap,
                text=VisionMode.LABELS.get(mode, mode).upper(),
                command=lambda m=mode: self._set_vision_mode(m),
                bg=BG_INPUT,
                fg=TEXT,
                activebackground=CYAN_DIM,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                padx=6,
                pady=6,
                font=FONT_SMALL,
                cursor="hand2",
            )
            btn.grid(row=0, column=idx, sticky="ew", padx=(0, 6) if idx < 4 else 0)
            self._vision_mode_buttons[mode] = btn
        self._sync_vision_mode_buttons()

        # ── LIVE MAP PANEL (below camera) ─────────────────────────
        map_card = HudCard(parent, "LIVE LOCATION MAP", "IP geolocation · Map preview · Google/OSM fallback")
        map_card.pack(fill="x", pady=(12, 0))

        # Map display canvas
        self.map_frame = tk.Frame(map_card.body, bg="#010c14",
                                  width=CAMERA_SIZE[0], height=180)
        self.map_frame.pack(fill="x")
        self.map_frame.pack_propagate(False)

        self.map_label = tk.Label(self.map_frame, bg="#010c14",
                                  fg=TEXT_DIM, text="[ Fetching location... ]",
                                  font=FONT_SMALL)
        self.map_label.pack(fill="both", expand=True)

        # Location text
        self.location_var = tk.StringVar(value="Detecting location...")
        tk.Label(map_card.body, textvariable=self.location_var,
                 fg=GOLD, bg=BG_PANEL, font=FONT_SMALL,
                 justify="left", wraplength=290).pack(anchor="w", pady=(8,4))

        self.coords_var = tk.StringVar(value="Coords: --")
        tk.Label(map_card.body, textvariable=self.coords_var,
                 fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).pack(anchor="w")

        map_btns = tk.Frame(map_card.body, bg=BG_PANEL)
        map_btns.pack(fill="x", pady=(8,0))
        map_btns.columnconfigure((0,1), weight=1)

        tk.Button(map_btns, text="🗺  OPEN IN BROWSER",
                  command=self._open_map_browser,
                  bg=BG_INPUT, fg=GOLD,
                  activebackground=GOLD_DIM, activeforeground=TEXT,
                  relief="flat", bd=0, padx=8, pady=7,
                  font=FONT_SMALL, cursor="hand2").grid(
            row=0, column=0, sticky="ew", padx=(0,4))

        tk.Button(map_btns, text="⟳ REFRESH",
                  command=self._refresh_map,
                  bg=BG_INPUT, fg=CYAN,
                  activebackground=CYAN_DIM, activeforeground=TEXT,
                  relief="flat", bd=0, padx=8, pady=7,
                  font=FONT_SMALL, cursor="hand2").grid(
            row=0, column=1, sticky="ew", padx=(4,0))

        # Load map after UI is ready
        self.root.after(2000, self._load_map_image)

    def _build_center_column(self, parent):
        core_card = HudCard(parent, "MISSION CORE", "Voice, command, and multimodal control plane")
        core_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self.orb = JarvisOrb(core_card.body, size=360)
        self.orb.pack(pady=(4, 4))

        self.mode_label = tk.Label(core_card.body, text="Auto mode routes to AI when references are active.", fg=TEXT, bg=BG_PANEL, font=FONT_UI)
        self.mode_label.pack()
        tk.Label(core_card.body, textvariable=self.context_text, fg=TEXT_DIM, bg=BG_PANEL, font=FONT_SMALL).pack(pady=(6, 12))

        toggles = tk.Frame(core_card.body, bg=BG_PANEL)
        toggles.pack(fill="x", pady=(0, 10))
        for idx in range(3):
            toggles.columnconfigure(idx, weight=1)

        self._build_toggle(toggles, "FORCE AI", self.force_ai_var).grid(row=0, column=0, sticky="w")
        self._build_toggle(toggles, "VOICE REPLIES", self.speak_reply_var).grid(row=0, column=1, sticky="w")
        self._build_toggle(toggles, "KEEP REFERENCES", self.auto_keep_refs_var).grid(row=0, column=2, sticky="w")

        buttons = tk.Frame(core_card.body, bg=BG_PANEL)
        buttons.pack(fill="x")
        for idx in range(4):
            buttons.columnconfigure(idx, weight=1)

        for idx, (label, command) in enumerate([
            ("🎙 VOICE INPUT", self._toggle_voice),
            ("🔍 ANALYZE REF", self._analyze_reference_image),
            ("🗑 CLEAR MEMORY", self._clear_memory),
            ("📷 LIST CAMERAS", lambda: self._queue_command("list cameras")),
        ]):
            tk.Button(
                buttons,
                text=label,
                command=command,
                bg=BG_INPUT,
                fg=TEXT,
                activebackground=CYAN_DIM,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                padx=8,
                pady=10,
                font=FONT_SMALL,
                cursor="hand2",
            ).grid(row=0, column=idx, sticky="ew", padx=(0, 8) if idx < 3 else 0)

        radar_card = HudCard(parent, "MOTION RADAR", "Realtime movement detection from camera feed")
        radar_card.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        radar_frame = tk.Frame(radar_card.body, bg="#020507", width=REFERENCE_SIZE[0], height=REFERENCE_SIZE[1])
        radar_frame.pack(fill="x")
        radar_frame.pack_propagate(False)

        self.radar_canvas = tk.Canvas(
            radar_frame,
            bg="#00130a",
            width=REFERENCE_SIZE[0],
            height=REFERENCE_SIZE[1],
            highlightthickness=0,
            bd=0,
        )
        self.radar_canvas.pack(fill="both", expand=True)

        tk.Label(
            radar_card.body,
            textvariable=self.radar_status,
            fg=TEXT_DIM,
            bg=BG_PANEL,
            justify="left",
            wraplength=520,
            font=FONT_SMALL,
        ).pack(anchor="w", pady=(10, 8))

        radar_btns = tk.Frame(radar_card.body, bg=BG_PANEL)
        radar_btns.pack(fill="x")
        radar_btns.columnconfigure((0, 1), weight=1)
        tk.Button(
            radar_btns,
            text="RESET RADAR",
            command=self._reset_radar_contacts,
            bg=BG_INPUT,
            fg=GOLD,
            activebackground=GOLD_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=8,
            pady=8,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        tk.Button(
            radar_btns,
            text="SNAP + ANALYZE",
            command=self._analyze_live_frame,
            bg=BG_INPUT,
            fg=CYAN,
            activebackground=CYAN_DIM,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=8,
            pady=8,
            font=FONT_SMALL,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        files_card = HudCard(parent, "CONTEXT FILES", "Attach notes, code, configs, or folders and ask about them directly")
        files_card.grid(row=2, column=0, sticky="nsew")
        files_card.body.rowconfigure(1, weight=1)
        files_card.body.columnconfigure(0, weight=1)

        tk.Label(files_card.body, textvariable=self.file_summary, fg=TEXT_DIM, bg=BG_PANEL, justify="left", wraplength=520, font=FONT_SMALL).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.file_list = tk.Listbox(
            files_card.body,
            bg=BG_INPUT,
            fg=TEXT,
            selectbackground=RED_SOFT,
            selectforeground="#fff2ee",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            font=FONT_SMALL,
            height=8,
        )
        self.file_list.grid(row=1, column=0, sticky="nsew")

        file_buttons = tk.Frame(files_card.body, bg=BG_PANEL)
        file_buttons.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        for idx in range(5):
            file_buttons.columnconfigure(idx, weight=1)

        for idx, (label, command) in enumerate([
            ("ADD FILES", self._attach_files),
            ("ADD FOLDER", self._attach_folder),
            ("PROJECT FILES", self._attach_project_files),
            ("REMOVE", self._remove_selected_file),
            ("CLEAR ALL", self._clear_files),
        ]):
            tk.Button(
                file_buttons,
                text=label,
                command=command,
                bg=BG_INPUT,
                fg=TEXT,
                activebackground=CYAN_DIM,
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                padx=8,
                pady=8,
                font=FONT_SMALL,
                cursor="hand2",
            ).grid(row=0, column=idx, sticky="ew", padx=(0, 8) if idx < 4 else 0)

    def _build_right_column(self, parent):
        # Right column now: Activity Timeline (top), Conversation (middle), Composer (bottom)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=0)
        parent.columnconfigure(0, weight=1)

        timeline_card = HudCard(parent, "LIVE ACTIVITY", "Mission log with timestamps")
        timeline_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        timeline_card.body.rowconfigure(0, weight=1)
        timeline_card.body.columnconfigure(0, weight=1)

        self.activity_log = scrolledtext.ScrolledText(
            timeline_card.body,
            bg=BG_INPUT,
            fg=TEXT,
            relief="flat",
            bd=0,
            wrap="word",
            state="disabled",
            insertbackground=GOLD,
            font=FONT_SMALL,
            height=8,
        )
        self.activity_log.grid(row=0, column=0, sticky="nsew")
        self.activity_log.tag_config("system", foreground=RED_SOFT)
        self.activity_log.tag_config("ai", foreground=GOLD)
        self.activity_log.tag_config("camera", foreground=CYAN)
        self.activity_log.tag_config("voice", foreground=GREEN)
        self.activity_log.tag_config("default", foreground=TEXT_DIM)
        self.activity_log.tag_config("time", foreground=TEXT_FAINT, font=("JetBrains Mono", 8))
        self._activity_widget = self.activity_log

        convo_card = HudCard(parent, "CONVERSATION", "Type normally. Use /cmd to force commands or /ai to force multimodal chat.")
        convo_card.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        convo_card.body.rowconfigure(0, weight=1)
        convo_card.body.columnconfigure(0, weight=1)

        self.chat_log = scrolledtext.ScrolledText(
            convo_card.body,
            bg=BG_INPUT,
            fg=TEXT,
            relief="flat",
            bd=0,
            wrap="word",
            state="disabled",
            insertbackground=GOLD,
            selectbackground=GOLD_DIM,
            font=FONT_UI,
        )
        self.chat_log.grid(row=0, column=0, sticky="nsew")
        self.chat_log.tag_config("jarvis", foreground=GOLD, font=("Orbitron", 9, "bold"))
        self.chat_log.tag_config("user", foreground=RED, font=("Orbitron", 9, "bold"))
        self.chat_log.tag_config("system", foreground=TEXT_DIM, font=("Exo 2", 9, "italic"))
        self.chat_log.tag_config("text", foreground=TEXT)
        self.chat_log.tag_config("error", foreground=RED)
        self.chat_log.tag_config("time", foreground=TEXT_FAINT, font=("JetBrains Mono", 8))

        composer_card = HudCard(parent, "COMPOSER", "Active references are reused until you clear them or switch KEEP REFERENCES off")
        composer_card.grid(row=2, column=0, sticky="ew")
        composer_card.body.columnconfigure(0, weight=1)

        self.input_entry = tk.Entry(
            composer_card.body,
            bg=BG_INPUT,
            fg=TEXT,
            insertbackground=GOLD,
            relief="flat",
            bd=0,
            font=("JetBrains Mono", 10),
        )
        self.input_entry.grid(row=0, column=0, columnspan=4, sticky="ew", ipady=8)
        self.input_entry.bind("<Return>", self._submit_from_entry)
        self.input_entry.bind("<Up>", self._history_up)
        self.input_entry.bind("<Down>", self._history_down)
        self.input_entry.focus_set()

        self.context_label = tk.Label(
            composer_card.body,
            textvariable=self.context_text,
            fg=TEXT_DIM,
            bg=BG_PANEL,
            justify="left",
            font=FONT_SMALL,
        )
        self.context_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 10))

        button_specs = [
            ("📎 ATTACH FILES", self._attach_files),
            ("🖼 ATTACH IMAGE", self._pick_reference_image),
            ("➤ SEND", self._submit_text),
            ("🧹 CLEAR CHAT", self._clear_chat),
        ]
        for idx, (label, command) in enumerate(button_specs):
            composer_card.body.columnconfigure(idx, weight=1)
            tk.Button(
                composer_card.body,
                text=label,
                command=command,
                bg=CYAN if label == "SEND" else BG_INPUT,
                fg=BG if label == "SEND" else TEXT,
                activebackground=CYAN_SOFT if label == "SEND" else CYAN_DIM,
                activeforeground=TEXT if label == "SEND" else TEXT,
                relief="flat",
                bd=0,
                padx=8,
                pady=10,
                font=FONT_SMALL,
                cursor="hand2",
            ).grid(row=2, column=idx, sticky="ew", padx=(0, 8) if idx < len(button_specs) - 1 else 0)

        tk.Label(
            composer_card.body,
            textvariable=self.capture_summary,
            fg=TEXT_FAINT,
            bg=BG_PANEL,
            justify="left",
            wraplength=380,
            font=FONT_SMALL,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))

    def _build_toggle(self, parent, label: str, variable: tk.BooleanVar) -> tk.Checkbutton:
        return tk.Checkbutton(
            parent,
            text=label,
            variable=variable,
            onvalue=True,
            offvalue=False,
            fg=GOLD,
            bg=BG_PANEL,
            activeforeground=GOLD,
            activebackground=BG_PANEL,
            selectcolor=BG_PANEL,
            highlightthickness=0,
            bd=0,
            font=FONT_SMALL,
            cursor="hand2",
        )

    def _boot_message(self):
        self._log_system("J.A.R.V.I.S mission control initialized.")
        self._log_system("Tip: /cmd forces the classic assistant commands. /ai forces multimodal chat.")
        self._log_system("Security overlay active. Voice and telemetry will start after unlock.")
        self._boot_greeting = self.jarvis.greeter.greet()
        self._log("JARVIS", self._boot_greeting)
        self._update_context_text()

    def _safe_speak(self, text: str):
        """Always runs on main thread — safe for pyttsx3."""
        try:
            self._set_audio_state("tts")
            self.orb.set_speaking(True)
            self.jarvis.voice.speak(text)
        except Exception as e:
            print(f"[TTS] {e}")
        finally:
            self.orb.set_speaking(False)
            self._set_audio_state("idle")

    def _speak_and_log(self, message: str, orig_speak):
        clean = self._clean_message(message)
        if clean:
            self.root.after(0, lambda m=clean: self._log("JARVIS", m))
            if self.speak_reply_var.get():
                self.root.after(0, lambda m=clean: self._safe_speak(m))

    # ── Wake Word Listener ─────────────────────────────────────
    def _start_wake_listener(self):
        """Continuously listens for wake word in background."""
        if not self.jarvis.voice.stt_ok:
            self._log_system("⚠  Microphone not available — voice wake disabled.")
            return
        if self._wake_thread and self._wake_thread.is_alive():
            return
        self._wake_active = True
        self._wake_thread = threading.Thread(target=self._wake_loop, daemon=True)
        self._wake_thread.start()
        self._log_system("🎙  Wake listener active. Say JARVIS to activate.")

    def _wake_loop(self):
        while getattr(self, "_wake_active", False) and self.jarvis._running:
            mic_acquired = False
            try:
                if getattr(self, "_voice_busy", False):
                    # Don't listen for wake word while already processing voice
                    time.sleep(0.5)
                    continue
                if not self._mic_lock.acquire(timeout=0.2):
                    time.sleep(0.1)
                    continue
                mic_acquired = True
                activated = False
                try:
                    try:
                        activated = self.jarvis.voice.wait_wake_word(self.jarvis.wakes, max_seconds=1.5)
                    except TypeError:
                        activated = self.jarvis.voice.wait_wake_word(self.jarvis.wakes)
                finally:
                    if not activated:
                        self._mic_lock.release()
                        mic_acquired = False

                if activated and not getattr(self, "_voice_busy", False):
                    self.root.after(0, lambda: self._set_status("WAKE WORD", "Listening for command...", CYAN))
                    self.root.after(0, lambda: self.orb.set_listening(True))
                    self.root.after(0, lambda: self._log_system("🎙  Wake word detected! Listening..."))
                    self._audio_wake_until = time.time() + 2.0
                    self.stats["voice_activations"] = int(self.stats.get("voice_activations", 0)) + 1
                    self._voice_busy = True
                    # Listen for the actual command
                    try:
                        self.root.after(0, lambda: self._set_audio_state("mic"))
                        cmd = self.jarvis.voice.listen(timeout=6, phrase_limit=6)
                    finally:
                        self._mic_lock.release()
                        mic_acquired = False
                        self.root.after(0, lambda: self._set_audio_state("idle"))
                        self._voice_busy = False
                        self.root.after(0, lambda: self.orb.set_listening(False))
                    if cmd:
                        self.root.after(0, lambda c=cmd: self._handle_voice_command(c))
                    else:
                        self.root.after(0, lambda: self._log_system("No command heard."))
                        self.root.after(0, self._request_finished)
                elif activated:
                    self._mic_lock.release()
                    mic_acquired = False
            except Exception as e:
                if mic_acquired:
                    try:
                        self._mic_lock.release()
                    except RuntimeError:
                        pass
                print(f"[Wake loop] {e}")
                time.sleep(1)

    def _handle_voice_command(self, cmd: str):
        self._log("YOU", f"🎙 {cmd}")
        self._run_command_request(cmd)

    # ── Map Methods ───────────────────────────────────────────
    def _load_map_image(self):
        """Show a local map preview image and update location text."""
        def worker():
            try:
                loc = self.jarvis.location
                coords = loc.get_coords()
                loc_str = loc.get_str()
                self._safe_after(0, lambda s=loc_str: self.location_var.set(s))
                if coords:
                    lat, lon = coords
                    self._safe_after(0, lambda: self.coords_var.set(
                        f"Lat/Lon: {lat:.4f}, {lon:.4f}"))

                if not PIL_OK:
                    self._safe_after(0, lambda: self.map_label.config(
                        image="", text="Install Pillow for map preview\npip install Pillow"))
                    return

                import io
                width, height = CAMERA_SIZE[0], 170

                if not DEFAULT_MAP_PREVIEW_PATH.exists():
                    self._safe_after(
                        0,
                        lambda: self.map_label.config(
                            image="",
                            text="Preview image missing:\nassets/map_preview.png",
                        ),
                    )
                    return

                img = Image.open(DEFAULT_MAP_PREVIEW_PATH)
                img = img.resize((width, height), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)

                def update():
                    self.map_label.config(image=photo, text="")
                    self.map_label.image = photo

                self._safe_after(0, update)
                self._safe_after(0, lambda: self._log_system(f"Location ready: {loc_str}"))

            except Exception as e:
                self._safe_after(0, lambda err=str(e): self.map_label.config(
                    image="", text=f"Map preview unavailable\n{err[:80]}"))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_map(self):
        self.jarvis.location.refresh()
        self.location_var.set("Refreshing location...")
        self.map_label.config(image="", text="[ Refreshing... ]")
        self.root.after(3000, self._load_map_image)

    def _open_map_browser(self):
        import webbrowser
        webbrowser.open(self.jarvis.location.get_map_url())

    def _set_status(self, text: str, detail: str = "", color: str = GREEN):
        self.status_text.set(text)
        if detail:
            self.status_detail.set(detail)
        self.status_dot.configure(fg=color)
        self.status_label.configure(fg=color)

    def _log(self, who: str, message: str, tag: str = "text"):
        self.chat_log.configure(state="normal")
        stamp = datetime.datetime.now().strftime("%H:%M")
        if who == "JARVIS":
            self.chat_log.insert("end", f"\n[{stamp}] ", "time")
            self.chat_log.insert("end", "JARVIS: ", "jarvis")
            self.chat_log.insert("end", message + "\n", tag)
            if tag != "error":
                self.toasts.show(message, "info", duration_ms=2600)
        elif who == "YOU":
            self.chat_log.insert("end", f"\n[{stamp}] ", "time")
            self.chat_log.insert("end", f"{self.name}: ", "user")
            self.chat_log.insert("end", message + "\n", tag)
        else:
            self.chat_log.insert("end", f"\n[{stamp}] {message}\n", "system")
        self.chat_log.configure(state="disabled")
        self.chat_log.see("end")
        if tag == "error":
            try:
                self.orb.flash_error(1.2)
            except Exception:
                pass

    def _log_system(self, message: str):
        self._log("SYS", message, "system")
        # Also emit to mission timeline.
        self._emit_event("system", message)
        style = "alert" if "error" in message.lower() or "failed" in message.lower() else "success" if "ready" in message.lower() else "info"
        self.toasts.show(message, style, duration_ms=2200)

    def _emit_event(self, kind: str, message: str):
        evt = ActivityEvent(ts=datetime.datetime.now(), kind=kind, message=self._clean_message(message))
        self.activity_events.append(evt)
        widget = getattr(self, "_activity_widget", None)
        if widget is None:
            return

        tag = kind if kind in ("system", "ai", "camera", "voice") else "default"
        stamp = evt.ts.strftime("%H:%M")
        try:
            widget.configure(state="normal")
            widget.insert("end", f"[{stamp}] ", "time")
            widget.insert("end", evt.message + "\n", tag)
            widget.configure(state="disabled")
            widget.see("end")
        except Exception:
            try:
                widget.configure(state="disabled")
            except Exception:
                pass

    def _start_analytics_loop(self):
        # seed history with zeros
        for _ in range(6):
            try:
                self.chart_cpu.push(0)
                self.chart_ram.push(0)
                self.chart_batt.push(0)
                self.chart_net_down.push(0)
                self.chart_net_up.push(0)
                self.chart_disk.push(0)
            except Exception:
                break

        def tick():
            try:
                self._update_analytics()
            finally:
                self._analytics_job = self.root.after(int(getattr(self, "_analytics_interval_ms", 2000)), tick)

        self.root.after(1200, tick)

    def _update_analytics(self):
        # CPU/RAM/Battery from existing snapshot if possible.
        try:
            snap = self.jarvis.system.hardware_snapshot()
            if snap.get("available"):
                self.chart_cpu.push(float(snap.get("cpu_percent", 0.0)))
                self.chart_ram.push(float(getattr(snap.get("ram"), "percent", 0.0)))
                batt = snap.get("battery")
                self.chart_batt.push(float(getattr(batt, "percent", 0.0)) if batt else 0.0)
        except Exception:
            pass

        # Network speed (KB/s)
        try:
            now = time.time()
            counters = psutil.net_io_counters()
            cur = (now, counters.bytes_sent, counters.bytes_recv)
            if self._net_prev:
                t0, s0, r0 = self._net_prev
                dt = max(0.5, now - t0)
                up_kb = (cur[1] - s0) / dt / 1024.0
                down_kb = (cur[2] - r0) / dt / 1024.0
                self.chart_net_up.push(max(0.0, up_kb))
                self.chart_net_down.push(max(0.0, down_kb))
            self._net_prev = cur
        except Exception:
            pass

        # Disk IO speed (KB/s)
        try:
            now = time.time()
            io = psutil.disk_io_counters()
            cur = (now, io.read_bytes, io.write_bytes)
            if self._diskio_prev:
                t0, rb0, wb0 = self._diskio_prev
                dt = max(0.5, now - t0)
                kb_s = ((cur[1] - rb0) + (cur[2] - wb0)) / dt / 1024.0
                self.chart_disk.push(max(0.0, kb_s))
            self._diskio_prev = cur
        except Exception:
            pass

        # Session stats
        try:
            uptime = datetime.datetime.now() - self.session_started_at
            up_h, rem = divmod(int(uptime.total_seconds()), 3600)
            up_m, up_s = divmod(rem, 60)
            lines = [
                f"Session start: {self.session_started_at.strftime('%H:%M:%S')}",
                f"Uptime: {up_h:02d}:{up_m:02d}:{up_s:02d}",
                f"Commands today: {self.stats.get('commands_today', 0)}",
                f"AI queries: {self.stats.get('ai_queries', 0)}",
                f"Photos taken: {self.stats.get('photos_taken', 0)}",
                f"Voice activations: {self.stats.get('voice_activations', 0)}",
            ]
            if hasattr(self, "analytics_stats_label"):
                self.analytics_stats_label.configure(text="\n".join(lines))
        except Exception:
            pass

    def _refresh_process_table(self):
        try:
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
                try:
                    procs.append(p.info)
                except Exception:
                    pass
            # cpu_percent is 0 on first call; do a quick second sample if needed.
            if not any((i.get("cpu_percent") or 0) > 0 for i in procs):
                time.sleep(0.1)
                procs = []
                for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
                    try:
                        procs.append(p.info)
                    except Exception:
                        pass

            procs.sort(key=lambda x: float(x.get("cpu_percent") or 0.0), reverse=True)
            top = procs[:10]
            if hasattr(self, "proc_list"):
                self.proc_list.delete(0, "end")
                for row in top:
                    pid = row.get("pid")
                    name = (row.get("name") or "")[:20]
                    cpu = float(row.get("cpu_percent") or 0.0)
                    self.proc_list.insert("end", f"{pid:>6}  {cpu:>5.1f}%  {name}")
        except Exception as e:
            if hasattr(self, "proc_list"):
                self.proc_list.delete(0, "end")
                self.proc_list.insert("end", f"Process list error: {e}")

        # auto-refresh
        self.root.after(5000, self._refresh_process_table)

    def _kill_selected_process(self):
        if not hasattr(self, "proc_list"):
            return
        sel = self.proc_list.curselection()
        if not sel:
            return
        text = self.proc_list.get(sel[0])
        try:
            pid = int(text.strip().split()[0])
        except Exception:
            return
        try:
            psutil.Process(pid).terminate()
            self._emit_event("system", f"Terminated process PID {pid}")
            self.toasts.show(f"Killed PID {pid}", "warning", duration_ms=2000)
        except Exception as e:
            self._log("JARVIS", f"Kill failed: {e}", "error")

    def _clean_message(self, message: str) -> str:
        return " ".join(str(message).split())

    def _update_context_text(self):
        file_count = len(self.attached_files)
        image_name = Path(self.reference_image_path).name if self.reference_image_path else "none"
        parts = [
            f"Reference image: {image_name}",
            f"Attached items: {file_count}",
            f"Force AI: {'on' if self.force_ai_var.get() else 'off'}",
        ]
        self.context_text.set(" | ".join(parts))
        if not self.attached_files:
            self.file_summary.set("No files attached.")
        else:
            names = ", ".join(Path(path).name for path in self.attached_files[:4])
            if len(self.attached_files) > 4:
                names += ", ..."
            self.file_summary.set(f"{len(self.attached_files)} attached: {names}")

    def _update_clock(self):
        now = datetime.datetime.now()
        self.clock_text.set(now.strftime("%I:%M:%S %p"))
        self.date_text.set(now.strftime("%A, %d %B %Y"))
        self.root.after(1000, self._update_clock)

    def _update_metrics(self):
        """Collect telemetry in a worker thread, update UI on main thread."""
        def _worker():
            try:
                snapshot = self.jarvis.system.hardware_snapshot()
                self.root.after(0, lambda s=snapshot: self._apply_metrics(snapshot=s))
            except Exception as e:
                self.root.after(0, lambda: self.system_detail.configure(text=f"Telemetry error: {e}"))
        threading.Thread(target=_worker, daemon=True).start()
        self.root.after(int(getattr(self, "_metrics_interval_ms", 2500)), self._update_metrics)

    def _apply_metrics(self, snapshot: dict):
        try:
            if not snapshot.get("available"):
                raise RuntimeError(snapshot.get("error", "hardware telemetry unavailable"))

            cpu = snapshot["cpu_percent"]
            ram = snapshot["ram"]
            disk = snapshot["disk"]
            battery = snapshot["battery"]
            thermals = snapshot.get("thermals") or {}

            self.cpu_bar.update(float(cpu))
            self.ram_bar.update(ram.percent)
            self.disk_bar.update(disk.percent)
            if battery:
                self.battery_bar.update(battery.percent)
                battery_text = f"{battery.percent:.0f}% {'charging' if battery.power_plugged else 'battery'}"
            else:
                self.battery_bar.update(0)
                battery_text = "N/A"

            uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
            uptime_hours, rem = divmod(int(uptime.total_seconds()), 3600)
            uptime_minutes = rem // 60
            detail = (
                f"RAM {human_size(ram.used)}/{human_size(ram.total)} | "
                f"Disk {human_size(disk.used)}/{human_size(disk.total)} | "
                f"Battery {battery_text} | "
                f"Uptime {uptime_hours:02d}h {uptime_minutes:02d}m"
            )
            self.system_detail.configure(text=detail)

            thermal_parts = []
            if thermals.get("cpu_temp_c") is not None:
                thermal_parts.append(f"CPU {thermals['cpu_temp_c']:.0f} C")
            if thermals.get("gpu_temp_c") is not None:
                gpu_label = thermals.get("gpu_name") or "GPU"
                thermal_parts.append(f"{gpu_label} {thermals['gpu_temp_c']:.0f} C")
            if thermals.get("fans"):
                thermal_parts.append(", ".join(f"{fan['name']} {fan['rpm']} RPM" for fan in thermals["fans"][:2]))
            elif thermals.get("gpu_fan_percent") is not None:
                thermal_parts.append(f"GPU fan {thermals['gpu_fan_percent']:.0f}%")
            elif thermals.get("note"):
                thermal_parts.append(thermals["note"])
            elif thermals.get("fan_control_note"):
                thermal_parts.append(thermals["fan_control_note"])
            if thermals.get("source"):
                thermal_parts.append(f"Source {thermals['source']}")
            self.thermal_detail.configure(text=" | ".join(thermal_parts) if thermal_parts else "Thermals unavailable right now.")

            try:
                cpu_txt = f"CPU {float(cpu):.0f}%"
                batt_txt = f"BAT {battery.percent:.0f}%" if battery else "BAT N/A"
                time_txt = datetime.datetime.now().strftime("%H:%M")
                weather_txt = (self.weather_last_text.split("—", 1)[0] if "—" in self.weather_last_text else self.weather_last_text[:10]).strip()
                self.orb.set_satellites([cpu_txt, batt_txt, time_txt, weather_txt])
            except Exception:
                pass
        except Exception as e:
            self.system_detail.configure(text=f"Telemetry error: {e}")
            self.thermal_detail.configure(text="Thermals unavailable right now.")

    def _refresh_weather(self, manual: bool = False):
        def worker():
            try:
                weather_text = self.jarvis.weather.current()
            except Exception as e:
                weather_text = f"Weather error: {e}"

            def update():
                self.weather_last_text = weather_text
                self.weather_summary.set(weather_text)
                if "°" in weather_text:
                    before_degree = weather_text.split("°", 1)[0]
                    temp_text = before_degree.split()[-1] + "°"
                    self.weather_temp.configure(text=temp_text)
                else:
                    self.weather_temp.configure(text="--")
                if manual:
                    self._log_system("Weather panel refreshed.")
                else:
                    self._emit_event("system", "Weather fetched.")

            self.root.after(0, update)

        threading.Thread(target=worker, daemon=True).start()
        if not manual:
            self.root.after(900000, self._refresh_weather)

    def _refresh_news(self, manual: bool = False):
        def worker():
            try:
                # Use backend (NewsAPI if configured; RSS fallback otherwise)
                news_text = self.jarvis.news.headlines(country="in")
            except Exception as e:
                news_text = f"News error: {e}"

            def update():
                self.news_last_text = news_text
                self.news_summary.set(news_text)
                if manual:
                    self._log_system("News panel refreshed.")
                else:
                    self._emit_event("system", "News fetched.")

            self.root.after(0, update)

        threading.Thread(target=worker, daemon=True).start()
        if not manual:
            self.root.after(int(getattr(self, "_news_interval_ms", 600000)), self._refresh_news)

    def _queue_command(self, command: str):
        self.input_entry.delete(0, "end")
        self.input_entry.insert(0, command)
        self._submit_text(force_mode="cmd")

    def _submit_from_entry(self, _event=None):
        self._submit_text()

    def _should_force_command_route(self, text: str) -> bool:
        lowered = str(text or "").strip().lower()
        if not lowered:
            return False

        if re.search(r"\b(create|make|new)\s+(file|folder)\b", lowered):
            return True
        if re.search(r"\b(open|show|launch)\s+([a-z]:\\|file|folder|document)\b", lowered):
            return True
        if re.search(r"\b(find|search|locate|where is)\s+file\b", lowered):
            return True

        command_intents = {
            "open_app",
            "hardware",
            "thermal_status",
            "fan_control",
            "network",
            "email_check",
            "send_email",
            "send_whatsapp",
            "calendar_today",
            "calendar_upcoming",
            "add_event",
            "open_calendar",
            "weather",
            "note_add",
            "note_read",
            "note_clear",
            "reminder",
            "news",
            "time",
            "date",
            "screenshot",
            "volume",
            "search_files",
            "open_file",
            "desktop",
            "clipboard",
            "processes",
            "camera_photo",
            "camera_video",
            "camera_live",
            "camera_analyze",
            "camera_list",
            "web_search",
            "shutdown",
            "restart",
            "lock",
            "clear_chat",
            "joke",
            "greet",
            "stop",
        }
        return Intent.classify(lowered) in command_intents

    def _submit_text(self, force_mode: str | None = None):
        text = self.input_entry.get().strip()
        if not text:
            return
        self.input_entry.delete(0, "end")

        self.command_history.append(text)
        self.command_index = -1
        self.stats["commands_today"] = int(self.stats.get("commands_today", 0)) + 1
        self._log("YOU", text)

        route = force_mode
        if text.startswith("/cmd "):
            route = "cmd"
            text = text[5:].strip()
        elif text.startswith("/ai "):
            route = "ai"
            # KEEP the /ai prefix so chat_with_references detects cowork mode
            # text is NOT stripped here — the AI brain handles stripping internally
        elif self._should_force_command_route(text):
            route = "cmd"
        elif route is None:
            route = "ai" if self.force_ai_var.get() or self.reference_image_path or self.attached_files else "cmd"

        if not text:
            return

        if route == "ai":
            self._run_ai_request(text)
        else:
            self._run_command_request(text)

    def _run_command_request(self, text: str):
        self._set_status("COMMAND", "Executing through the classic JARVIS handler.", ORANGE)
        self.orb.set_active(True)

        def worker():
            original_speak = self.jarvis.voice.speak

            def gui_speak(message):
                self._speak_and_log(message, original_speak)

            self.jarvis.voice.speak = gui_speak
            try:
                self.jarvis.handle(text)
            except Exception as e:
                self.root.after(0, lambda: self._log("JARVIS", f"Error: {e}", "error"))
            finally:
                self.jarvis.voice.speak = original_speak
                self.root.after(0, self._request_finished)

        threading.Thread(target=worker, daemon=True).start()

    def _build_runtime_context(self) -> str:
        mood = getattr(self.jarvis.voice, "last_voice_mood", "neutral")
        fid = getattr(self, "_face_identity_label", "—")
        return (
            f"Time: {datetime.datetime.now().strftime('%A %I:%M %p')}; "
            f"OS: {platform.system()}; "
            f"Camera live: {self.camera_running}; "
            f"Face tracking: {self.face_tracking_var.get()}; "
            f"Faces detected: {self.last_face_count}; "
            f"Face ID (camera): {fid}; "
            f"Voice mood (last utterance): {mood}; "
            f"Matrix HUD: {self.matrix_overlay_var.get()}; "
            f"Reference image: {Path(self.reference_image_path).name if self.reference_image_path else 'none'}; "
            f"Attached items: {len(self.attached_files)}; "
            f"Latest weather: {self.weather_last_text}"
        )

    def _run_ai_request(
        self,
        prompt: str,
        image_paths: list[str] | None = None,
        file_paths: list[str] | None = None,
    ):
        active_images = image_paths if image_paths is not None else ([self.reference_image_path] if self.reference_image_path else [])
        active_files = file_paths if file_paths is not None else list(self.attached_files)

        model_label = self._ai_model_label(vision=bool(active_images))
        detail = f"Using: {model_label}"
        self._set_status("AI MODE", detail, CYAN)
        self.orb.set_active(True)
        self.orb.set_thinking(True)
        self.stats["ai_queries"] = int(self.stats.get("ai_queries", 0)) + 1
        self._emit_event("ai", f"AI request started ({model_label}).")
        self._start_thinking_timer(model_label)

        def worker():
            original_speak = self.jarvis.voice.speak
            try:
                reply = self.jarvis.ai.chat_with_references(
                    prompt,
                    context=self._build_runtime_context(),
                    file_paths=active_files,
                    image_paths=active_images,
                )
                self.root.after(0, lambda r=reply: self._stream_jarvis_reply(r, speak_after=self.speak_reply_var.get()))
            except Exception as e:
                self.root.after(0, lambda: self._log("JARVIS", f"AI error: {e}", "error"))
            finally:
                self.root.after(0, self._stop_thinking_timer)
                self.root.after(0, lambda: self.orb.set_thinking(False))
                self.root.after(0, self._request_finished)
                if not self.auto_keep_refs_var.get():
                    self.root.after(0, self._clear_reference_image)
                    self.root.after(0, self._clear_files)

        threading.Thread(target=worker, daemon=True).start()

    def _ai_model_label(self, vision: bool = False) -> str:
        # Best-effort: surface configured model or fallback to first FREE model.
        key = "openrouter_vision_model" if vision else "openrouter_model"
        configured = (self.cfg.get(key) or "").strip()
        if configured:
            return configured
        # Fall back to the first model in jarvis AIBrain list if available.
        try:
            models = getattr(self.jarvis.ai, "FREE_MODELS", None) or getattr(self.jarvis.ai, "OPENROUTER_TEXT_MODELS", None)
            if models:
                return str(models[0])
        except Exception:
            pass
        return "openrouter/free"

    def _start_thinking_timer(self, model_label: str):
        self._thinking_started = time.time()
        if self._thinking_job is not None:
            try:
                self.root.after_cancel(self._thinking_job)
            except Exception:
                pass
            self._thinking_job = None

        def tick():
            if self._thinking_started is None:
                return
            elapsed = int(time.time() - self._thinking_started)
            self.status_detail.set(f"Using: {model_label} | Thinking: {elapsed:02d}s")
            self._thinking_job = self.root.after(500, tick)

        self._thinking_job = self.root.after(500, tick)

    def _stop_thinking_timer(self):
        self._thinking_started = None
        if self._thinking_job is not None:
            try:
                self.root.after_cancel(self._thinking_job)
            except Exception:
                pass
            self._thinking_job = None

    def _stream_jarvis_reply(self, reply: str, speak_after: bool = True):
        text = str(reply or "").strip()
        if not text:
            return

        # Insert prefix once.
        self.chat_log.configure(state="normal")
        stamp = datetime.datetime.now().strftime("%H:%M")
        self.chat_log.insert("end", f"\n[{stamp}] ", "time")
        self.chat_log.insert("end", "JARVIS: ", "jarvis")
        self.chat_log.configure(state="disabled")
        self.chat_log.see("end")

        words = text.split()
        idx = 0

        def step():
            nonlocal idx
            if idx >= len(words):
                # End line.
                self.chat_log.configure(state="normal")
                self.chat_log.insert("end", "\n", "text")
                self.chat_log.configure(state="disabled")
                self.chat_log.see("end")
                self._emit_event("ai", "AI response completed.")
                if speak_after:
                    self.root.after(0, lambda t=text: self._safe_speak(t))
                return

            chunk_words = 2 if idx < 25 else 3
            chunk = " ".join(words[idx:idx + chunk_words]) + " "
            idx += chunk_words
            self.chat_log.configure(state="normal")
            self.chat_log.insert("end", chunk, "text")
            self.chat_log.configure(state="disabled")
            self.chat_log.see("end")
            self.root.after(35, step)

        step()

    def _request_finished(self):
        self.orb.set_active(False)
        self._set_status("ONLINE", "Ready for voice, camera, and file-aware chat.", GREEN)
        self._update_context_text()

    def _history_up(self, _event=None):
        if not self.command_history:
            return "break"
        self.command_index = min(self.command_index + 1, len(self.command_history) - 1)
        self.input_entry.delete(0, "end")
        self.input_entry.insert(0, self.command_history[-(self.command_index + 1)])
        return "break"

    def _history_down(self, _event=None):
        if self.command_index > 0:
            self.command_index -= 1
            self.input_entry.delete(0, "end")
            self.input_entry.insert(0, self.command_history[-(self.command_index + 1)])
        else:
            self.command_index = -1
            self.input_entry.delete(0, "end")
        return "break"

    def _clear_chat(self):
        self.chat_log.configure(state="normal")
        self.chat_log.delete("1.0", "end")
        self.chat_log.configure(state="disabled")
        self.jarvis.ai.reset()
        self._log_system("Conversation cleared.")

    def _clear_memory(self):
        self.jarvis.ai.reset()
        self._log_system("AI memory cleared.")

    def _toggle_voice(self):
        if self.voice_thread and self.voice_thread.is_alive():
            return
        if getattr(self, "_voice_busy", False):
            self._log_system("Voice channel is already busy.")
            return
        self._voice_busy = True
        self.voice_thread = threading.Thread(target=self._voice_capture, daemon=True)
        self.voice_thread.start()

    def _voice_capture(self):
        self.root.after(0, lambda: self._set_status("LISTENING", "Awaiting microphone input...", GREEN))
        self.root.after(0, lambda: self.orb.set_listening(True))
        acquired = False
        heard = None
        try:
            acquired = self._mic_lock.acquire(timeout=2.0)
            if not acquired:
                self.root.after(0, lambda: self._log_system("Microphone is busy. Try again in a moment."))
                return
            self.root.after(0, lambda: self._set_audio_state("mic"))
            heard = self.jarvis.voice.listen(timeout=6, phrase_limit=6)
        except Exception as e:
            heard = None
            self.root.after(0, lambda: self._log("JARVIS", f"Voice capture error: {e}", "error"))
        finally:
            if acquired:
                try:
                    self._mic_lock.release()
                except RuntimeError:
                    pass
            self._voice_busy = False
            self.root.after(0, lambda: self._set_audio_state("idle"))
            self.root.after(0, lambda: self.orb.set_listening(False))
            self.root.after(0, self._request_finished)

        if heard:
            self.root.after(0, lambda: self.input_entry.delete(0, "end"))
            self.root.after(0, lambda text=heard: self.input_entry.insert(0, text))
            self.root.after(0, self._submit_text)
        else:
            self.root.after(0, lambda: self._log_system("No speech detected."))

    def _camera_backend(self):
        index = int(self.cfg.get("camera_index", 0))
        # DirectShow (CAP_DSHOW) causes 5-10 second freezes on release in Windows.
        # MSMF is the default in Windows and releases instantly.
        return cv2.VideoCapture(index)

    def _detect_faces(self, frame):
        if not self.face_tracking_var.get() or not self.face_tracking_available:
            return []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.12,
                minNeighbors=5,
                minSize=(56, 56),
            )
            return sorted(faces, key=lambda face: face[2] * face[3], reverse=True)
        except Exception:
            return []

    def _ensure_matrix_columns(self, width: int, height: int):
        column_count = max(12, width // 18)
        if len(self.matrix_columns) != column_count:
            self.matrix_columns = [random.randint(0, height + 50) for _ in range(column_count)]

    def _draw_corner_brackets(self, frame, x: int, y: int, w: int, h: int, color):
        corner = max(12, min(w, h) // 4)
        thickness = 2
        cv2.line(frame, (x, y), (x + corner, y), color, thickness)
        cv2.line(frame, (x, y), (x, y + corner), color, thickness)
        cv2.line(frame, (x + w, y), (x + w - corner, y), color, thickness)
        cv2.line(frame, (x + w, y), (x + w, y + corner), color, thickness)
        cv2.line(frame, (x, y + h), (x + corner, y + h), color, thickness)
        cv2.line(frame, (x, y + h), (x, y + h - corner), color, thickness)
        cv2.line(frame, (x + w, y + h), (x + w - corner, y + h), color, thickness)
        cv2.line(frame, (x + w, y + h), (x + w, y + h - corner), color, thickness)

    def _draw_face_web(self, frame, face, primary: bool = False):
        x, y, w, h = [int(v) for v in face]
        height, width = frame.shape[:2]
        center = (x + w // 2, y + h // 2)
        accent = (0, 184, 255) if primary else (32, 32, 255)
        soft = (0, 112, 184) if primary else (18, 18, 170)

        nodes = [
            (x, y + h // 2),
            (x + w // 4, y),
            (x + (3 * w) // 4, y),
            (x + w, y + h // 2),
            (x + (3 * w) // 4, y + h),
            (x + w // 4, y + h),
        ]
        for idx, node in enumerate(nodes):
            cv2.circle(frame, node, 2, accent, -1)
            cv2.line(frame, center, node, accent, 1)
            cv2.line(frame, node, nodes[(idx + 1) % len(nodes)], soft, 1)

        if primary:
            anchors = [
                (center[0], 0),
                (0, center[1]),
                (width - 1, center[1]),
                (center[0], height - 1),
            ]
            for anchor in anchors:
                cv2.line(frame, center, anchor, soft, 1)
            cv2.circle(frame, center, max(10, min(w, h) // 5), accent, 1)
            cv2.circle(frame, center, 4, accent, -1)

    def _apply_matrix_overlay(self, frame):
        if not self.matrix_overlay_var.get():
            return frame

        display = frame.copy()
        height, width = display.shape[:2]

        if np is not None:
            gray = cv2.cvtColor(display, cv2.COLOR_BGR2GRAY)
            cool = (gray * 0.05).astype(np.uint8)
            amber = np.clip(gray * 0.52 + 16, 0, 255).astype(np.uint8)
            hot = np.clip(gray * 0.96 + 26, 0, 255).astype(np.uint8)
            display = cv2.merge([cool, amber, hot])
            display[::6, :, :] = (display[::6, :, :] * 0.5).astype(np.uint8)

        for gx in range(0, width, 32):
            cv2.line(display, (gx, 0), (gx, height), (0, 74, 128), 1)
        for gy in range(0, height, 24):
            cv2.line(display, (0, gy), (width, gy), (0, 62, 108), 1)

        self._ensure_matrix_columns(width, height)
        for idx, y in enumerate(self.matrix_columns):
            x = int((idx + 0.5) * width / len(self.matrix_columns))
            trail = 18 + (idx % 5) * 8
            top = max(0, y - trail)
            trail_color = (0, 160, 255) if idx % 3 else (18, 18, 255)
            cv2.line(display, (x, top), (x, min(height - 1, y)), trail_color, 1)
            cv2.circle(display, (x, min(height - 1, y)), 1, (0, 214, 255), -1)
            self.matrix_columns[idx] = (y + 6 + (idx % 4)) % (height + trail + 20)

        scan_y = (self.matrix_tick * 7) % max(1, height)
        cv2.line(display, (0, scan_y), (width, scan_y), (0, 184, 255), 1)
        self.matrix_tick = (self.matrix_tick + 1) % 10000
        return display

    def _pulse(self, base: float = 0.5, amp: float = 0.5, speed: float = 0.12) -> float:
        # Smooth 0..1 pulse driven by animation counter.
        return base + amp * (0.5 + 0.5 * math.sin(self._hud_anim * speed))

    def _clamp_pt(self, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        return max(0, min(width - 1, int(x))), max(0, min(height - 1, int(y)))

    def _draw_hex_grid(self, frame, color=(0, 168, 255), alpha: float = 0.16, step: int = 24):
        if np is None:
            return frame
        h, w = frame.shape[:2]
        overlay = frame.copy()
        r = max(10, step // 2)
        dx = int(r * 1.7)
        dy = int(r * 1.5)

        def hex_points(cx: int, cy: int, radius: int):
            pts = []
            for i in range(6):
                ang = math.radians(60 * i - 30)
                pts.append((int(cx + radius * math.cos(ang)), int(cy + radius * math.sin(ang))))
            return np.array(pts, dtype=np.int32).reshape((-1, 1, 2))

        for row, cy in enumerate(range(-r, h + r, dy)):
            x_off = dx // 2 if row % 2 else 0
            for cx in range(-r + x_off, w + r, dx):
                cv2.polylines(overlay, [hex_points(cx, cy, r)], True, color, 1, cv2.LINE_AA)
        return cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

    def _mark50_overlay(self, frame, faces):
        display = frame.copy()
        h, w = display.shape[:2]

        # Gold hex grid background.
        display = self._draw_hex_grid(display, color=(0, 184, 255), alpha=0.10, step=26)

        # Pulsing "SCANNING..." when no faces.
        if not faces:
            p = self._pulse()
            txt = "SCANNING..." if int(self._hud_anim / 10) % 2 == 0 else "SCANNING"
            cv2.putText(display, txt, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, int(120 + 100 * p), 255), 2, cv2.LINE_AA)
            return display

        # Face lock reticles and threat text.
        for idx, face in enumerate(faces[:3]):
            x, y, fw, fh = [int(v) for v in face]
            cx, cy = x + fw // 2, y + fh // 2
            accent = (0, 184, 255) if idx == 0 else (40, 70, 255)  # BGR: gold-ish / red-ish
            danger = (0, 50, 255)

            # Distance estimate (very rough): larger face -> closer.
            rel = max(1.0, (fw * fh) / float(w * h))
            distance_m = max(0.4, min(6.0, 1.6 / math.sqrt(rel)))
            threat = "LOW" if distance_m > 2.5 else "MED" if distance_m > 1.4 else "HIGH"
            threat_color = accent if threat != "HIGH" else danger

            # Rotating corner brackets illusion by shifting points slightly.
            wob = int(3 * math.sin((self._hud_anim + idx * 7) * 0.18))
            bx = x + wob
            by = y - wob
            self._draw_corner_brackets(display, bx, by, fw, fh, threat_color)

            # Reticle.
            r = max(16, min(fw, fh) // 3)
            cv2.circle(display, (cx, cy), r, threat_color, 1, cv2.LINE_AA)
            cv2.circle(display, (cx, cy), max(8, r // 2), (0, 120, 220), 1, cv2.LINE_AA)
            cv2.line(display, (cx - r - 10, cy), (cx + r + 10, cy), (0, 80, 160), 1, cv2.LINE_AA)
            cv2.line(display, (cx, cy - r - 10), (cx, cy + r + 10), (0, 80, 160), 1, cv2.LINE_AA)

            # Text above each face.
            top_y = max(18, y - 10)
            tag = "TARGET LOCKED" if idx == 0 else "ANALYZING"
            cv2.putText(display, tag, (x, top_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, threat_color, 1, cv2.LINE_AA)
            cv2.putText(display, f"THREAT LEVEL: {threat}", (x, top_y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, threat_color, 1, cv2.LINE_AA)
            cv2.putText(display, f"DIST: {distance_m:.1f}m", (x, top_y + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 150, 220), 1, cv2.LINE_AA)

        return display

    def _thermal_overlay(self, frame, faces):
        # False-color thermal effect.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (0, 0), 1.0)
        thermal = cv2.applyColorMap(gray, cv2.COLORMAP_TURBO)
        display = cv2.addWeighted(thermal, 0.92, frame, 0.08, 0)
        h, w = display.shape[:2]

        # Watermark.
        cv2.putText(display, "THERMAL MODE ACTIVE", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

        # Intensity meter (right side).
        meter_h = h - 50
        meter_x = w - 16
        meter_top = 35
        cv2.rectangle(display, (meter_x, meter_top), (meter_x + 8, meter_top + meter_h), (30, 30, 30), -1)
        intensity = 0.0
        if np is not None:
            # Heuristic: average brightness in face areas indicates "heat".
            vals = []
            for face in faces[:3]:
                x, y, fw, fh = [int(v) for v in face]
                roi = gray[max(0, y):min(h, y + fh), max(0, x):min(w, x + fw)]
                if roi.size:
                    vals.append(float(np.mean(roi)))
            intensity = (sum(vals) / len(vals) / 255.0) if vals else float(np.mean(gray)) / 255.0
        fill = int(meter_h * max(0.05, min(1.0, intensity)))
        cv2.rectangle(display, (meter_x, meter_top + meter_h - fill), (meter_x + 8, meter_top + meter_h), (0, 255, 255), -1)

        # Highlight faces with bright contour.
        for idx, face in enumerate(faces[:3]):
            x, y, fw, fh = [int(v) for v in face]
            color = (255, 255, 255) if idx == 0 else (220, 220, 220)
            cv2.rectangle(display, (x, y), (x + fw, y + fh), color, 1, cv2.LINE_AA)
        return display

    def _tron_overlay(self, frame, faces):
        display = frame.copy()
        h, w = display.shape[:2]

        # Electric blue grid with depth illusion.
        overlay = display.copy()
        center_x, center_y = w // 2, h // 2
        for i in range(10):
            t = i / 10.0
            pad_x = int(t * (w * 0.48))
            pad_y = int(t * (h * 0.48))
            color = (255, int(150 + 80 * (1 - t)), 20)  # BGR cyan-ish
            cv2.rectangle(overlay, (center_x - pad_x, center_y - pad_y), (center_x + pad_x, center_y + pad_y), color, 1, cv2.LINE_AA)
        for gx in range(0, w, 28):
            cv2.line(overlay, (gx, 0), (gx, h), (255, 140, 0), 1, cv2.LINE_AA)
        for gy in range(0, h, 22):
            cv2.line(overlay, (0, gy), (w, gy), (255, 110, 0), 1, cv2.LINE_AA)
        display = cv2.addWeighted(overlay, 0.18, display, 0.82, 0)

        # Cyan scan lines sweeping vertically.
        scan_y = int((self._hud_anim * 4) % max(1, h))
        cv2.line(display, (0, scan_y), (w, scan_y), (255, 255, 80), 1, cv2.LINE_AA)
        cv2.line(display, (0, max(0, scan_y - 12)), (w, max(0, scan_y - 12)), (255, 140, 30), 1, cv2.LINE_AA)

        # Glitch flicker.
        if (self._hud_anim + self._glitch_seed) % 37 == 0 and np is not None:
            strip_y = random.randint(0, max(0, h - 8))
            strip_h = random.randint(3, 10)
            display[strip_y:strip_y + strip_h, :, :] = (display[strip_y:strip_y + strip_h, :, :] * 0.3).astype(np.uint8)

        # Neon outlines and IDs.
        edges = cv2.Canny(cv2.cvtColor(display, cv2.COLOR_BGR2GRAY), 60, 140)
        display[edges > 0] = (255, 210, 30)

        for idx, face in enumerate(faces[:3]):
            x, y, fw, fh = [int(v) for v in face]
            cv2.rectangle(display, (x, y), (x + fw, y + fh), (255, 210, 30), 1, cv2.LINE_AA)
            cv2.putText(
                display,
                f"USER ID: PRASHANT_{idx + 1:03d}",
                (x, max(18, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 240, 80),
                1,
                cv2.LINE_AA,
            )
        return display

    def _predator_overlay(self, frame, faces):
        # High-contrast with neon edges (Predator-like).
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (0, 0), 1.2)
        edges = cv2.Canny(gray, 50, 140)
        display = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        display[:, :, 1] = np.clip(display[:, :, 1] + 60, 0, 255) if np is not None else display[:, :, 1]
        display[:, :, 2] = 0
        display[:, :, 0] = np.clip(display[:, :, 0] * 0.4, 0, 255) if np is not None else display[:, :, 0]
        display[edges > 0] = (0, 255, 255)  # bright neon

        if faces:
            cv2.putText(display, "PREY DETECTED", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
            # Heat bloom around faces.
            for face in faces[:3]:
                x, y, fw, fh = [int(v) for v in face]
                cx, cy = x + fw // 2, y + fh // 2
                cv2.circle(display, (cx, cy), max(18, min(fw, fh) // 2), (0, 220, 255), 2, cv2.LINE_AA)
        else:
            cv2.putText(display, "SEARCHING...", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 230, 230), 1, cv2.LINE_AA)
        return display

    def _neural_overlay(self, frame, faces):
        display = frame.copy()
        h, w = display.shape[:2]

        # Subtle darkening for "UI".
        display = cv2.addWeighted(display, 0.78, (display * 0).astype(display.dtype), 0.22, 0)

        cv2.putText(display, "PROCESSING", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 210, 255), 2, cv2.LINE_AA)

        # Animated nodes firing along top bar.
        for i in range(10):
            x = 10 + i * 18
            y = 34
            on = ((self._hud_anim // 2) + i) % 10 < 3
            cv2.circle(display, (x, y), 3, (0, 220, 255) if on else (40, 80, 120), -1, cv2.LINE_AA)

        for idx, face in enumerate(faces[:2]):
            x, y, fw, fh = [int(v) for v in face]
            # Fake 68-point landmarks based on box proportions.
            pts = []
            for t in range(17):  # jawline
                px = x + int(fw * (t / 16.0))
                py = y + int(fh * (0.72 + 0.22 * math.sin((t / 16.0) * math.pi)))
                pts.append((px, py))
            # eyes (approx)
            for t in range(6):
                pts.append((x + int(fw * (0.30 + 0.10 * t / 5.0)), y + int(fh * 0.40)))
                pts.append((x + int(fw * (0.60 + 0.10 * t / 5.0)), y + int(fh * 0.40)))
            # nose ridge
            for t in range(9):
                pts.append((x + int(fw * 0.50), y + int(fh * (0.35 + 0.30 * t / 8.0))))
            # mouth
            for t in range(10):
                pts.append((x + int(fw * (0.35 + 0.30 * t / 9.0)), y + int(fh * 0.62)))

            # Draw nodes + connections
            accent = (0, 210, 255) if idx == 0 else (32, 140, 255)
            for p in pts:
                px, py = self._clamp_pt(p[0], p[1], w, h)
                cv2.circle(display, (px, py), 2, accent, -1, cv2.LINE_AA)
            for i in range(0, len(pts) - 1, 2):
                p1 = pts[i]
                p2 = pts[i + 1]
                cv2.line(display, p1, p2, (0, 120, 180), 1, cv2.LINE_AA)

            conf = 94.2 - idx * 3.7 + 2.0 * math.sin((self._hud_anim + idx * 11) * 0.12)
            cv2.rectangle(display, (x, y), (x + fw, y + fh), accent, 1, cv2.LINE_AA)
            cv2.putText(display, f"IDENTITY: {conf:.1f}%", (x, max(18, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, accent, 1, cv2.LINE_AA)

        if faces and (self._hud_anim % 90) > 75:
            cv2.putText(display, "NEURAL SCAN COMPLETE", (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 210, 255), 1, cv2.LINE_AA)

        return display

    def _apply_vision_mode(self, frame, faces):
        mode = self.vision_mode.get()
        if mode == VisionMode.MARK50:
            return self._mark50_overlay(frame, faces)
        if mode == VisionMode.THERMAL:
            return self._thermal_overlay(frame, faces)
        if mode == VisionMode.TRON:
            return self._tron_overlay(frame, faces)
        if mode == VisionMode.PREDATOR:
            return self._predator_overlay(frame, faces)
        if mode == VisionMode.NEURAL:
            return self._neural_overlay(frame, faces)
        return frame

    def _request_camera_face_identity(self, frame, faces):
        owner_face = getattr(self.jarvis, "owner_face", None)
        if not owner_face or not owner_face.enabled or not faces:
            return
        if self._face_identity_busy:
            return
        now = time.time()
        if now - self._face_identity_last_request < self._face_identity_min_interval:
            return
        self._face_identity_busy = True
        self._face_identity_last_request = now
        frame_copy = frame.copy()
        faces_copy = [tuple(map(int, face)) for face in faces]

        def worker():
            try:
                identity = owner_face.identify_primary(frame_copy, faces_copy)
            except Exception:
                identity = "?"

            def done():
                prev = getattr(self, "_face_identity_label", "")
                self._face_identity_label = identity or "?"
                self._face_identity_busy = False
                if self._face_identity_label == "STRANGER" and prev != "STRANGER":
                    self._emit_event("camera", "Primary face does not match owner profile (stranger).")

            self._safe_after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _decorate_camera_frame(self, frame, skip_face_detect: bool = False):
        faces = list(self._last_faces) if skip_face_detect else self._detect_faces(frame)
        if (
            not skip_face_detect
            and getattr(self.jarvis, "owner_face", None)
            and self.jarvis.owner_face.enabled
            and faces
        ):
            fc = int(getattr(self, "_cam_fc", 0) or 0)
            if fc % self._face_rec_interval == 0:
                self._request_camera_face_identity(frame, faces)
        elif not skip_face_detect and not faces:
            self._face_identity_label = "NO_FACE"

        display = self._apply_vision_mode(frame, faces)
        # Matrix overlay remains optional as an extra layer (can be combined with modes).
        display = self._apply_matrix_overlay(display)
        height, width = display.shape[:2]

        tag = str(getattr(self, "_face_identity_label", "") or "").strip()
        if tag and tag not in ("—", "?", "NO_FACE"):
            if tag == "OWNER":
                col = (80, 220, 100)
            elif tag == "STRANGER":
                col = (60, 60, 255)
            elif tag == "NO_PROFILE":
                col = (180, 180, 100)
            else:
                col = (200, 200, 200)
            cv2.putText(
                display,
                f"FACE: {tag}",
                (10, 26),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                col,
                2,
                cv2.LINE_AA,
            )

        # In Mark50 we already draw target UI; keep the old face HUD for other modes.
        if self.face_tracking_var.get() and self.face_tracking_available and self.vision_mode.get() not in (VisionMode.MARK50,):
            for idx, face in enumerate(faces[:3]):
                x, y, w, h = [int(v) for v in face]
                color = (0, 184, 255) if idx == 0 else (32, 32, 255)
                self._draw_corner_brackets(display, x, y, w, h, color)
                cv2.rectangle(display, (x, y), (x + w, y + h), color, 1)
                self._draw_face_web(display, face, primary=(idx == 0))
                cv2.putText(
                    display,
                    f"TARGET {idx + 1}",
                    (x, max(18, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    color,
                    1,
                    cv2.LINE_AA,
                )

            if faces:
                x, y, w, h = [int(v) for v in faces[0]]
                center = (x + w // 2, y + h // 2)
                cv2.line(display, (center[0], 0), (center[0], height), (0, 118, 190), 1)
                cv2.line(display, (0, center[1]), (width, center[1]), (0, 118, 190), 1)
                cv2.putText(
                    display,
                    "FACE LOCK",
                    (max(8, x), min(height - 10, y + h + 18)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.52,
                    (0, 184, 255),
                    1,
                    cv2.LINE_AA,
                )

        return display, faces

    def _update_camera_overlay_status(self, faces):
        matrix_state = "Matrix HUD on" if self.matrix_overlay_var.get() else "Matrix HUD off"
        if self.face_tracking_var.get() and not self.face_tracking_available:
            self.camera_summary.set(f"Camera live. {matrix_state}. Face tracking unavailable on this setup.")
            self.camera_lock_label.configure(text="Face lock unavailable.")
            return

        if self.face_tracking_var.get():
            self.camera_summary.set(
                f"Camera live. {matrix_state}. Face tracking {'engaged' if faces else 'searching'}."
            )
            if faces:
                x, y, w, h = [int(v) for v in faces[0]]
                self.camera_lock_label.configure(
                    text=f"Primary lock: {len(faces)} face(s) detected | target box {w}x{h} at ({x}, {y})"
                )
            else:
                self.camera_lock_label.configure(text="Scanning for faces...")
        else:
            self.camera_summary.set(f"Camera live. {matrix_state}. Face tracking off.")
            self.camera_lock_label.configure(text="Manual visual mode.")

    # ── Motion Radar ───────────────────────────────────────────
    def _start_radar_loop(self):
        def tick():
            try:
                self._draw_radar()
            finally:
                self.root.after(80, tick)
        self.root.after(300, tick)

    def _reset_radar_contacts(self):
        self.radar_blips.clear()
        self.radar_motion_hits = 0
        self.radar_status.set("Radar contacts reset.")

    def _draw_radar(self):
        canvas = getattr(self, "radar_canvas", None)
        if canvas is None:
            return
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        cx, cy = w // 2, h // 2
        radius = int(min(w, h) * 0.44)

        canvas.delete("all")
        canvas.create_rectangle(0, 0, w, h, fill="#00130a", outline="")

        # Radar rings + grid
        for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
            r = int(radius * frac)
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#116b3a", width=1)
        for deg in range(0, 360, 30):
            a = math.radians(deg)
            x = cx + int(math.cos(a) * radius)
            y = cy + int(math.sin(a) * radius)
            canvas.create_line(cx, cy, x, y, fill="#0a3f25", width=1)

        # Sweep
        self.radar_angle = (self.radar_angle + 2.5) % 360.0
        a = math.radians(self.radar_angle)
        sx = cx + int(math.cos(a) * radius)
        sy = cy + int(math.sin(a) * radius)
        canvas.create_line(cx, cy, sx, sy, fill="#37ff7f", width=2)

        # Fading tail
        for i in range(1, 12):
            tail_deg = self.radar_angle - (i * 2.8)
            ta = math.radians(tail_deg)
            tx = cx + int(math.cos(ta) * radius)
            ty = cy + int(math.sin(ta) * radius)
            shade = 255 - (i * 18)
            shade = max(32, min(255, shade))
            color = f"#{0:02x}{shade:02x}{64:02x}"
            canvas.create_line(cx, cy, tx, ty, fill=color, width=1)

        # Draw and decay movement blips
        alive = []
        for blip in self.radar_blips:
            ttl = blip.get("ttl", 0.0) - 0.03
            if ttl <= 0:
                continue
            angle = blip.get("angle", 0.0)
            dist = max(0.06, min(1.0, blip.get("dist", 0.5)))
            strength = max(0.15, min(1.0, blip.get("strength", 0.5)))
            br = int(2 + strength * 5)
            pr = int(dist * radius)
            ba = math.radians(angle)
            bx = cx + int(math.cos(ba) * pr)
            by = cy + int(math.sin(ba) * pr)
            alpha_scale = max(0.15, ttl)
            g = int(160 + 90 * alpha_scale)
            color = f"#{20:02x}{g:02x}{80:02x}"
            canvas.create_oval(bx - br, by - br, bx + br, by + br, outline=color, fill=color)
            blip["ttl"] = ttl
            alive.append(blip)
        self.radar_blips = alive[-120:]

        # center marker
        canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#54ff97", outline="")
        canvas.create_text(10, 10, anchor="nw", text="RADAR ONLINE", fill="#67ff9a", font=("JetBrains Mono", 9, "bold"))

    def _update_radar_motion(self, frame):
        if frame is None or cv2 is None:
            return
        try:
            small = cv2.resize(frame, (120, 90), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
        except Exception:
            return

        if self.radar_prev_small is None:
            self.radar_prev_small = gray
            return

        try:
            diff = cv2.absdiff(self.radar_prev_small, gray)
            _, thresh = cv2.threshold(diff, 24, 255, cv2.THRESH_BINARY)
            thresh = cv2.dilate(thresh, None, iterations=2)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except Exception:
            self.radar_prev_small = gray
            return

        hits = 0
        h, w = gray.shape[:2]
        for c in contours[:40]:
            area = cv2.contourArea(c)
            if area < 60:
                continue
            x, y, cw, ch = cv2.boundingRect(c)
            mx = x + cw / 2.0
            my = y + ch / 2.0

            # Horizontal camera position -> radar angle, vertical -> pseudo distance
            angle = (mx / max(1.0, float(w))) * 300.0 - 150.0  # spread in front arc
            angle = (angle + 360.0) % 360.0
            dist = 0.2 + (my / max(1.0, float(h))) * 0.75
            strength = min(1.0, area / 800.0)

            self.radar_blips.append({
                "angle": angle,
                "dist": dist,
                "strength": strength,
                "ttl": 1.0,
            })
            hits += 1

        self.radar_prev_small = gray
        if hits:
            self.radar_motion_hits += hits
            self.radar_status.set(f"Movement detected: {hits} contact(s) | Total contacts: {self.radar_motion_hits}")
        elif self.camera_running:
            self.radar_status.set("Scanning... no movement detected.")

    def _toggle_camera(self):
        if self.camera_running:
            self._stop_camera()
        else:
            self._start_camera()

    def _start_camera(self):
        if not (PIL_OK and cv2):
            self._log("JARVIS", "Install Pillow and opencv-python to use the embedded camera.", "error")
            return
        capture = self._camera_backend()
        if not capture or not capture.isOpened():
            self._log("JARVIS", "Unable to open the configured camera.", "error")
            return

        self.camera_capture = capture
        self.camera_running = True
        self.last_face_count = 0
        self.matrix_columns = []
        self._last_faces = []
        self._cam_fc = 0
        self.radar_prev_small = None
        self.camera_toggle_btn.configure(text="STOP CAM")
        apply_button_style(self.camera_toggle_btn, "danger")
        self.camera_summary.set("Camera streaming at roughly 30 FPS.")
        self.camera_lock_label.configure(text="Initializing visual lock...")
        self._set_status("CAMERA LIVE", "Embedded feed is active.", CYAN)
        self._emit_event("camera", "Camera started.")
        self.radar_status.set("Radar scanning movement...")
        self._update_camera_frame()

    def _stop_camera(self):
        self.camera_running = False
        if self.camera_capture is not None:
            try:
                self.camera_capture.release()
            except Exception:
                pass
        self.camera_capture = None
        self.current_frame = None
        self.current_overlay_frame = None
        self.radar_prev_small = None
        self.camera_label.configure(image="", text="Camera offline", fg=TEXT_DIM)
        self.camera_label.image = None
        self.camera_toggle_btn.configure(text="START CAM")
        apply_button_style(self.camera_toggle_btn, "arc")
        self.camera_summary.set("Camera offline.")
        self.camera_lock_label.configure(text="Face lock idle.")
        self.radar_status.set("Radar standby. Start camera to scan movement.")
        self._emit_event("camera", "Camera stopped.")
        self._request_finished()

    def _update_camera_frame(self):
        if not self.camera_running or self.camera_capture is None:
            return

        try:
            ok, frame = self.camera_capture.read()
            if ok and frame is not None:
                self._hud_anim = (self._hud_anim + 1) % 1_000_000
                self._cam_fc = getattr(self, "_cam_fc", 0) + 1
                self.current_frame = frame.copy()
                self._update_radar_motion(frame)
                if self._cam_fc % 5 == 0:
                    display_frame, faces = self._decorate_camera_frame(frame, skip_face_detect=False)
                    self._last_faces = list(faces)
                    self.last_face_count = len(faces)
                    self._update_camera_overlay_status(faces)
                else:
                    display_frame, faces = self._decorate_camera_frame(frame, skip_face_detect=True)
                self.current_overlay_frame = display_frame.copy()
                frame_rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                image = image.resize(CAMERA_SIZE, Image.BILINEAR)
                photo = ImageTk.PhotoImage(image)
                self.camera_label.configure(image=photo, text="")
                self.camera_label.image = photo
        except Exception as e:
            self.camera_summary.set(f"Camera update failed: {e}")

        self.root.after(42, self._update_camera_frame)

    def _save_frame(self, frame) -> str:
        PHOTOS_DIR.mkdir(exist_ok=True)
        path = PHOTOS_DIR / f"hud_capture_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        cv2.imwrite(str(path), frame)
        self.capture_summary.set(f"Last capture: {path.name}")
        return str(path)

    def _capture_live_frame(self):
        if self.camera_running and self.current_frame is not None:
            path = self._save_frame(self.current_frame)
            self.stats["photos_taken"] = int(self.stats.get("photos_taken", 0)) + 1
            self._log_system(f"Live frame saved to {path}.")
            return path

        ok, result = self.jarvis.camera.capture_photo()
        if ok:
            self.capture_summary.set(f"Last capture: {Path(result).name}")
            self.stats["photos_taken"] = int(self.stats.get("photos_taken", 0)) + 1
            self._log_system(f"Photo captured to {result}.")
            return result

        self._log("JARVIS", result, "error")
        return None

    def _use_live_frame_as_reference(self):
        path = self._capture_live_frame()
        if path:
            self._set_reference_image(path, announce=True)

    def _analyze_live_frame(self):
        path = self._capture_live_frame()
        if not path:
            return
        self._set_reference_image(path, announce=False)
        prompt = self.input_entry.get().strip() or "Describe everything visible in this live camera frame."
        self._log_system("Analyzing the most recent live frame.")
        self._run_ai_request(prompt, image_paths=[path], file_paths=list(self.attached_files))

    def _pick_reference_image(self):
        path = filedialog.askopenfilename(
            title="Choose reference image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._set_reference_image(path, announce=True)

    def _set_reference_image(self, path: str, announce: bool = False):
        self.reference_image_path = str(Path(path))
        self.reference_name.set(short_path(self.reference_image_path, 72))

        if not hasattr(self, "reference_label"):
            # Reference preview UI may be replaced (e.g., radar panel). Keep context-only behavior.
            self._update_context_text()
            if announce:
                self._log_system(f"Reference image armed: {self.reference_image_path}")
            return

        if PIL_OK:
            try:
                image = Image.open(self.reference_image_path).convert("RGB")
                image = ImageOps.fit(image, REFERENCE_SIZE, Image.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self.reference_label.configure(image=photo, text="")
                self.reference_label.image = photo
                self.reference_preview_image = photo
            except Exception as e:
                self.reference_label.configure(image="", text=f"Preview unavailable\n{e}", fg=TEXT_DIM)
                self.reference_label.image = None
        else:
            self.reference_label.configure(image="", text=Path(path).name, fg=TEXT)
            self.reference_label.image = None

        self._update_context_text()
        if announce:
            self._log_system(f"Reference image armed: {self.reference_image_path}")

    def _clear_reference_image(self):
        self.reference_image_path = None
        self.reference_name.set("No reference image selected.")
        if hasattr(self, "reference_label"):
            self.reference_label.configure(image="", text="No reference image", fg=TEXT_DIM)
            self.reference_label.image = None
        self._update_context_text()

    def _analyze_reference_image(self):
        if not self.reference_image_path:
            self._log("JARVIS", "Select a reference image first, or promote a live frame.", "error")
            return
        prompt = self.input_entry.get().strip() or "Analyze this reference image in detail."
        self._log_system("Analyzing active reference image.")
        self._run_ai_request(prompt)

    def _attach_files(self):
        paths = filedialog.askopenfilenames(title="Attach files")
        if paths:
            self._add_attachments(paths)

    def _attach_folder(self):
        path = filedialog.askdirectory(title="Attach folder")
        if path:
            self._add_attachments([path])

    def _attach_project_files(self):
        base = Path(__file__).resolve().parent
        project_files = [
            base / "jarvis.py",
            base / "jarvis_gui.py",
            base / "README.md",
            base / "requirements.txt",
            base / "setup_windows.bat",
        ]
        existing = [str(path) for path in project_files if path.exists()]
        if existing:
            self._add_attachments(existing)

    def _add_attachments(self, paths):
        added = 0
        existing = set(self.attached_files)
        for path in paths:
            normalized = str(Path(path))
            if normalized not in existing:
                self.attached_files.append(normalized)
                existing.add(normalized)
                added += 1
        if added:
            self._refresh_file_list()
            self._update_context_text()
            self._log_system(f"Attached {added} item(s) to the AI context deck.")

    def _refresh_file_list(self):
        self.file_list.delete(0, "end")
        for path in self.attached_files:
            p = Path(path)
            label = f"{p.name}  [{short_path(path, 64)}]"
            self.file_list.insert("end", label)

    def _remove_selected_file(self):
        selection = self.file_list.curselection()
        if not selection:
            return
        index = selection[0]
        removed = self.attached_files.pop(index)
        self._refresh_file_list()
        self._update_context_text()
        self._log_system(f"Removed {removed} from the context deck.")

    def _clear_files(self):
        if not self.attached_files:
            return
        self.attached_files.clear()
        self._refresh_file_list()
        self._update_context_text()
        self._log_system("Attached file context cleared.")


def main():
    print("\n" + "=" * 60)
    print("  J.A.R.V.I.S GUI v3.0 - Starting Mission Control")
    print("=" * 60)

    jarvis = JARVIS()
    root = tk.Tk()
    app = JARVISGui(root, jarvis)

    def on_close():
        app._wake_active = False
        app._stop_lock_camera()
        app._stop_camera()
        jarvis._running = False
        jarvis.voice.shutdown()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
