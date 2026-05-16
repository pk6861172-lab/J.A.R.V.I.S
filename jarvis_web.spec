# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the J.A.R.V.I.S web/PWA bridge.
"""

from pathlib import Path


BASE_DIR = Path.cwd()

datas = [
    (str(BASE_DIR / "web"), "web"),
    (str(BASE_DIR / "assets"), "assets"),
    (str(BASE_DIR / "contacts.csv"), "."),
]

if (BASE_DIR / "jarvis_config.json").exists():
    datas.append((str(BASE_DIR / "jarvis_config.json"), "."))

if (BASE_DIR / "vosk-model-small-en-us-0.15").exists():
    datas.append((str(BASE_DIR / "vosk-model-small-en-us-0.15"), "vosk-model-small-en-us-0.15"))

a = Analysis(
    ["jarvis_web.py"],
    pathex=[str(BASE_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "jarvis",
        "PIL",
        "PIL.Image",
        "requests",
        "openai",
        "dotenv",
        "psutil",
        "pyautogui",
        "pyperclip",
        "speech_recognition",
        "pyttsx3",
        "pyttsx3.drivers",
        "pyttsx3.drivers.sapi5",
        "vosk",
        "sounddevice",
        "cv2",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "jupyter", "ipython"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="JARVIS-Web",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
