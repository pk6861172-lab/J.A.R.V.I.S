# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for J.A.R.V.I.S GUI
Creates a standalone Windows executable with all dependencies bundled
"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Get the base directory
BASE_DIR = Path(os.getcwd())

vosk_datas = collect_data_files('vosk')
vosk_binaries = collect_dynamic_libs('vosk')

a = Analysis(
    ['jarvis_gui.py'],
    pathex=[str(BASE_DIR)],
    binaries=vosk_binaries,
    datas=[
        # Include Python source files
        (str(BASE_DIR / 'jarvis.py'), '.'),
        (str(BASE_DIR / 'jarvis_gui.py'), '.'),
        # Include assets
        (str(BASE_DIR / 'assets'), 'assets'),
        # Include vosk model (speech recognition)
        (str(BASE_DIR / 'vosk-model-small-en-us-0.15'), 'vosk-model-small-en-us-0.15'),
        # Include config files
        (str(BASE_DIR / 'jarvis_config.json'), '.'),
        (str(BASE_DIR / 'contacts.csv'), '.'),
        (str(BASE_DIR / 'PyWhatKit_DB.txt'), '.'),
    ] + vosk_datas,
    hiddenimports=[
        # Local modules
        'jarvis',
        
        # Core dependencies
        'tkinter',
        'tkinter.filedialog',
        'tkinter.scrolledtext',
        'tkinter.ttk',
        'PIL',
        'PIL.Image',
        'PIL.ImageOps',
        'PIL.ImageTk',
        'PIL.ImageDraw',
        'PIL.ImageFilter',
        
        # Speech & Audio
        'speech_recognition',
        'pyttsx3',
        'pyttsx3.drivers',
        'pyttsx3.drivers.sapi5',
        'vosk',
        'sounddevice',
        'soundfile',
        'librosa',
        'librosa.core',
        'librosa.util',
        'openwakeword',
        'onnxruntime',
        'onnxruntime.capi',
        
        # System & Process
        'psutil',
        'pyautogui',
        'pyperclip',
        
        # Networking & Web
        'requests',
        'requests.adapters',
        'urllib3',
        'urllib3.util',
        
        # Camera & Image
        'cv2',
        'cv2.cv2',
        
        # AI & ML
        'openai',
        'dotenv',
        'numpy',
        'numpy.core',
        'numpy.random',
        'scipy',
        'scipy.fftpack',
        
        # Face Recognition
        'face_recognition',
        'dlib',
        
        # WhatsApp
        'pywhatkit',
        'pywhatkit.requester',
        
        # Email
        'email',
        'email.mime',
        'email.mime.text',
        'email.mime.multipart',
        'email.header',
        'smtplib',
        'imaplib',
        
        # System modules
        'threading',
        'queue',
        'concurrent',
        'concurrent.futures',
        'subprocess',
        'datetime',
        'json',
        'os',
        'sys',
        'pathlib',
        'shutil',
        're',
        'time',
        'collections',
        'collections.deque',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'pytest',
        'setuptools',
        'pip',
        'jupyter',
        'ipython',
        'pandas',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='JARVIS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True to see error messages in console for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JARVIS_App'
)
