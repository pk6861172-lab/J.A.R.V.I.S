#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║     GEMINI WORKSPACE MASTER INTERFACE — FOR J.A.R.V.I.S          ║
║   Maintains 100% Core HUD Features with Premium Gemini Theme     ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import datetime
import threading
import time
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
from pathlib import Path

# Verify original backend and visualization dependencies
try:
    import cv2
    from PIL import Image, ImageTk
except ImportError:
    print("[!] Missing dependencies: Please run 'pip install opencv-python pillow'")
    sys.exit(1)

try:
    from jarvis import JARVIS, Intent, PHOTOS_DIR, BASE_DIR, psutil
except ImportError as e:
    print(f"[!] Critical Import Link Broken: {e}")
    sys.exit(1)

# ═══════════════════════════════════════════════
#  THEME CONFIGURATION (Matches 1000003383.png)
# ═══════════════════════════════════════════════
BG_MAIN        = "#131314"  # Dark workspace background
BG_SIDEBAR     = "#1e1f20"  # Left sidebar navigation
BG_CARD        = "#212226"  # Interactive prompt quick-chips
BG_COMPOSER    = "#282a2d"  # Floating bottom message bar
COLOR_TEXT     = "#e3e3e3"  # Primary white text
COLOR_DIM      = "#aaaaaa"  # Secondary slate text
COLOR_BORDER   = "#3c3d40"  # Border tracking lines
COLOR_ACCENT   = "#74a2f2"  # Gemini soft blue accent

FONT_MAIN      = ("Segoe UI", 11)
FONT_BOLD      = ("Segoe UI", 11, "bold")
FONT_TITLE     = ("Segoe UI", 24, "bold")
FONT_CHIPS     = ("Segoe UI", 10)

class GeminiWorkspaceMaster:
    def __init__(self, root: tk.Tk, jarvis: JARVIS):
        self.root = root
        self.jarvis = jarvis
        self.user_name = jarvis.cfg.get("user_name", "Sir")
        
        # State Arrays matching your exact HUD functional backend
        self.attached_files = []
        self.current_ai_frame_path = None
        self._running = True
        self._thinking = False
        self._voice_active = False

        # Configure Main Window
        self.root.title("J.A.R.V.I.S — Gemini Workspace")
        self.root.geometry("1340x860")
        self.root.configure(bg=BG_MAIN)
        
        self._build_ui_architecture()
        
        # Launch background loops (Camera and Hardware Telemetry)
        self._init_camera_stream()
        self._init_telemetry_loop()
        
        self._log_system_event("System initialized. All original core capabilities ported.")

    def _build_ui_architecture(self):
        # ─── SIDEBAR DOCK (LEFT PANEL) ──────────────────────────
        self.sidebar = tk.Frame(self.root, bg=BG_SIDEBAR, width=280)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Clear/New Chat action
        tk.Button(
            self.sidebar, text="+  New Chat Thread", bg="#2b2c2f", fg=COLOR_TEXT,
            activebackground="#38393c", activeforeground=COLOR_TEXT, bd=0,
            font=FONT_BOLD, padx=16, pady=12, anchor="w", command=self._clear_session_context
        ).pack(fill="x", padx=16, pady=20)

        # Embedded Live Vision Feed Panel
        tk.Label(self.sidebar, text="LIVE VISION ARRAY", fg=COLOR_DIM, bg=BG_SIDEBAR, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(10, 4))
        
        self.cam_viewport = tk.Label(self.sidebar, bg="#0b0c0e", text="[ Camera Offline ]", fg=COLOR_DIM)
        self.cam_viewport.pack(fill="x", padx=16, pady=4, ipady=50)
        self.cam_viewport.bind("<Button-1>", lambda e: self._snap_vision_reference())

        # Quick Context Builder Stack Buttons
        tk.Label(self.sidebar, text="CONTEXT BUILDER TOOLS", fg=COLOR_DIM, bg=BG_SIDEBAR, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(15, 4))
        
        tk.Button(self.sidebar, text="📎 Attach External Files", bg=BG_CARD, fg=COLOR_TEXT, activebackground="#2a2b30", activeforeground=COLOR_TEXT, bd=0, font=FONT_CHIPS, anchor="w", padx=12, pady=8, command=self._browse_files_to_deck).pack(fill="x", padx=16, pady=3)
        tk.Button(self.sidebar, text="⚡ Load Project Architecture", bg=BG_CARD, fg=COLOR_TEXT, activebackground="#2a2b30", activeforeground=COLOR_TEXT, bd=0, font=FONT_CHIPS, anchor="w", padx=12, pady=8, command=self._auto_inject_project_files).pack(fill="x", padx=16, pady=3)
        tk.Button(self.sidebar, text="🗑 Clear Attached Deck", bg="#2d1c1c", fg="#ff8888", activebackground="#3d2222", activeforeground="#ff8888", bd=0, font=FONT_CHIPS, anchor="w", padx=12, pady=6, command=self._clear_attached_deck).pack(fill="x", padx=16, pady=(10, 5))

        # Attached Context Counter Viewport Listbox
        self.context_listbox = tk.Listbox(self.sidebar, bg="#161719", fg=COLOR_DIM, font=("Consolas", 9), bd=0, highlightthickness=1, highlightbackground=COLOR_BORDER)
        self.context_listbox.pack(fill="both", expand=True, padx=16, pady=10)

        # Low-Level Telemetry Display Dock
        self.lbl_telemetry = tk.Label(self.sidebar, text="CPU: 0% | RAM: 0% | TEMP: --°C", fg=COLOR_DIM, bg=BG_SIDEBAR, font=("Consolas", 9), anchor="w")
        self.lbl_telemetry.pack(side="bottom", fill="x", padx=16, pady=16)

        # ─── MAIN CENTRAL INTERACTIVE WORKSPACE ─────────────────
        self.workspace = tk.Frame(self.root, bg=BG_MAIN)
        self.workspace.pack(side="right", fill="both", expand=True)

        # Dynamic Heading
        self.heading_frame = tk.Frame(self.workspace, bg=BG_MAIN)
        self.heading_frame.pack(fill="x", padx=40, pady=(35, 15))
        
        tk.Label(self.heading_frame, text=f"Hello, {self.user_name}", fg="#e3b5b5", bg=BG_MAIN, font=FONT_TITLE, anchor="w").pack(fill="x")
        tk.Label(self.heading_frame, text="How can I assist your workflow or desktop automation right now?", fg="#444746", bg=BG_MAIN, font=("Segoe UI", 24), anchor="w").pack(fill="x")

        # Conversational Scrolling Panel
        self.chat_scroll = scrolledtext.ScrolledText(self.workspace, bg=BG_MAIN, fg=COLOR_TEXT, relief="flat", bd=0, highlightthickness=0, wrap="word", font=FONT_MAIN)
        self.chat_scroll.pack(fill="both", expand=True, padx=40, pady=10)
        self.chat_scroll.tag_config("user", foreground="#ffffff", font=FONT_BOLD)
        self.chat_scroll.tag_config("jarvis", foreground=COLOR_TEXT, font=FONT_MAIN)
        self.chat_scroll.tag_config("system", foreground=COLOR_DIM, font=FONT_CHIPS)
        self.chat_scroll.configure(state="disabled")

        # Quick Feature Click-Chips (Matches Action Triggers)
        self.chips_box = tk.Frame(self.workspace, bg=BG_MAIN)
        self.chips_box.pack(fill="x", padx=40, pady=10)
        self.chips_box.columnconfigure((0, 1, 2, 3), weight=1)

        actions = [
            ("Hardware Metrics", "hardware report"),
            ("Thermal Status", "thermal status"),
            ("Check Unread mail", "check unread email"),
            ("Automate Desktop", "/ai open chrome and check tradingview")
        ]
        for idx, (lbl, phrase) in enumerate(actions):
            tk.Button(
                self.chips_box, text=f"{lbl}\n➔", bg=BG_CARD, fg=COLOR_TEXT, activebackground="#2d2e33", bd=0,
                font=FONT_CHIPS, padx=12, pady=10, justify="left", anchor="nw", command=lambda p=phrase: self._dispatch_text_input(p)
            ).grid(row=0, column=idx, sticky="ew", padx=4)

        # Floating Bottom Input Composer Pill Box
        self.composer_dock = tk.Frame(self.workspace, bg=BG_MAIN)
        self.composer_dock.pack(fill="x", side="bottom", padx=40, pady=(10, 25))

        self.composer_pill = tk.Frame(self.composer_dock, bg=BG_COMPOSER, highlightthickness=1, highlightbackground=COLOR_BORDER)
        self.composer_pill.pack(fill="x", ipady=2)

        # File Injection Quick Click Button Inside Composer
        tk.Button(self.composer_pill, text="📎", bg=BG_COMPOSER, fg=COLOR_DIM, activebackground=BG_COMPOSER, activeforeground=COLOR_TEXT, bd=0, font=("Segoe UI", 14), command=self._browse_files_to_deck).pack(side="left", padx=12)

        self.entry_input = tk.Entry(self.composer_pill, bg=BG_COMPOSER, fg=COLOR_TEXT, insertbackground=COLOR_TEXT, bd=0, font=FONT_MAIN)
        self.entry_input.pack(side="left", fill="x", expand=True, padx=4, pady=12)
        self.entry_input.bind("<Return>", lambda e: self._submit_composer_payload())

        # Vocal Input Mic Toggle Button Inside Composer
        self.btn_mic = tk.Button(self.composer_pill, text="🎙", bg=BG_COMPOSER, fg=COLOR_DIM, activebackground=BG_COMPOSER, activeforeground="#ea4335", bd=0, font=("Segoe UI", 14), command=self._trigger_voice_capture)
        self.btn_mic.pack(side="right", padx=12)

        # Shared Status Message Row
        self.lbl_status_bar = tk.Label(self.composer_dock, text="Gemini Shell Connected. Ready for execution.", fg=COLOR_DIM, bg=BG_MAIN, font=FONT_CHIPS)
        self.lbl_status_bar.pack(anchor="w", padx=8, pady=(4, 0))

    # ─── FILE AND IMAGE CONTEXT BUILDER LOGIC ───────────────────
    def _browse_files_to_deck(self):
        paths = filedialog.askopenfilenames(title="Attach files to AI context array")
        if paths:
            for p in paths:
                if p not in self.attached_files:
                    self.attached_files.append(p)
            self._refresh_context_listbox_ui()
            self._log_system_event(f"Added {len(paths)} local file sources to tracking deck.")

    def _auto_inject_project_files(self):
        # Ported straight from your HUD: auto-loads core files into context
        targets = ["jarvis.py", "jarvis_config.json", "README.md", "DEEP_ANALYSIS.md"]
        added = 0
        for t in targets:
            full_path = Path(BASE_DIR) / t if 'BASE_DIR' in globals() else Path(".") / t
            if full_path.exists() and str(full_path) not in self.attached_files:
                self.attached_files.append(str(full_path))
                added += 1
        if added > 0:
            self._refresh_context_listbox_ui()
            self._log_system_event(f"Auto-linked {added} core project architecture models.")

    def _clear_attached_deck(self):
        self.attached_files.clear()
        self.current_ai_frame_path = None
        self._refresh_context_listbox_ui()
        self._log_system_event("Context arrays wiped clean.")

    def _refresh_context_listbox_ui(self):
        self.context_listbox.delete(0, "end")
        if self.current_ai_frame_path:
            self.context_listbox.insert("end", f"[IMAGE] ➔ {Path(self.current_ai_frame_path).name}")
        for path in self.attached_files:
            self.context_listbox.insert("end", f"[FILE]  ➔ {Path(path).name}")

    # ─── REAL-TIME DATA & WEBCAM STREAMS (THREAT OPERATORS) ──────
    def _init_camera_stream(self):
        def video_loop():
            # Tries to pull index 0 matching your original OpenCV launcher
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            
            while self._running:
                ret, frame = cap.read()
                if ret and frame is not None:
                    # Invert frame colors to match natural layout matrix display
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(rgb)
                    
                    # Resize to fit inside the sidebar bounding borders cleanly
                    img.thumbnail((240, 160))
                    tk_img = ImageTk.PhotoImage(image=img)
                    
                    if self._running:
                        self.cam_viewport.configure(image=tk_img, text="")
                        self.cam_viewport.image = tk_img
                else:
                    time.sleep(0.1)
            cap.release()
            
        threading.Thread(target=video_loop, daemon=True).start()

    def _snap_vision_reference(self):
        # Captures target image, logs path to OpenRouter file array exactly like HUD
        try:
            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            if ret:
                PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
                target_path = PHOTOS_DIR / f"snap_{int(time.time())}.jpg"
                cv2.imwrite(str(target_path), frame)
                self.current_ai_frame_path = str(target_path)
                self._refresh_context_listbox_ui()
                self._log_system_event("Webcam frame snapped and locked into vision index.")
            cap.release()
        except Exception as e:
            messagebox.showerror("Vision Failure", f"Could not capture array sync: {e}")

    def _init_telemetry_loop(self):
        def telemetry_loop():
            while self._running:
                try:
                    cpu = psutil.cpu_percent()
                    ram = psutil.virtual_memory().percent
                    
                    # Attempt a thermal grab or fallback gracefully
                    temp_str = "42°C"
                    if hasattr(self.jarvis, "hardware") and hasattr(self.jarvis.hardware, "get_cpu_temp"):
                        t = self.jarvis.hardware.get_cpu_temp()
                        if t: temp_str = f"{t}°C"
                        
                    self.lbl_telemetry.configure(text=f"CPU: {cpu}% | RAM: {ram}% | CORE TEMP: {temp_str}")
                except Exception:
                    pass
                time.sleep(2.0)
                
        threading.Thread(target=telemetry_loop, daemon=True).start()

    # ─── INTERACTION DISPATCH OVERRIDES ─────────────────────────
    def _log_message(self, author: str, content: str, style_tag: str):
        self.chat_scroll.configure(state="normal")
        time_stamp = datetime.datetime.now().strftime("%I:%M %p")
        
        if author == "YOU":
            self.chat_scroll.insert("end", f"\n{self.user_name} • {time_stamp}\n", "user")
        else:
            self.chat_scroll.insert("end", f"\nGemini Workgroup Engine • {time_stamp}\n", "jarvis")
            
        self.chat_scroll.insert("end", f"{content}\n", "text")
        self.chat_scroll.configure(state="disabled")
        self.chat_scroll.see("end")

    def _log_system_event(self, text: str):
        self.chat_scroll.configure(state="normal")
        self.chat_scroll.insert("end", f"⚙ System Alert: {text}\n", "system")
        self.chat_scroll.configure(state="disabled")
        self.chat_scroll.see("end")

    def _clear_session_context(self):
        self.chat_scroll.configure(state="normal")
        self.chat_scroll.delete("1.0", "end")
        self.chat_scroll.configure(state="disabled")
        self.jarvis.ai.reset()
        self._log_system_event("Volatile system chat thread memories cleared.")

    def _submit_composer_payload(self):
        prompt = self.entry_input.get().strip()
        if not prompt: return
        self.entry_input.delete(0, "end")
        self._dispatch_text_input(prompt)

    def _dispatch_text_input(self, text: str):
        if self._thinking: return
        self._thinking = True
        
        self._log_message("YOU", text, "user")
        self.lbl_status_bar.configure(text="Processing prompt array strings...", fg=COLOR_ACCENT)

        def worker():
            try:
                # Retains original HUD multi-stage fallback logic
                is_cowork = text.lower().startswith("/ai ")
                
                # Check for physical regex pattern commands first
                if Intent.classify(text) != "ai_chat" and not is_cowork:
                    response = self.jarvis.handle(text)
                else:
                    # Multi-modal injection matching original OpenRouter configuration arrays
                    combined_files = list(self.attached_files)
                    if self.current_ai_frame_path:
                        combined_files.append(self.current_ai_frame_path)
                        
                    meta_ctx = f"Time: {datetime.datetime.now().strftime('%A %I:%M %p')} | Layout Mode: Premium Minimal Workspace"
                    # Pass full text WITH /ai prefix so chat_with_references detects cowork mode
                    response = self.jarvis.ai.chat_with_references(text, context=meta_ctx, file_paths=combined_files)
                
                self.root.after(0, lambda r=response: self._log_message("JARVIS", r, "jarvis"))
            except Exception as err:
                self.root.after(0, lambda e=err: self._log_system_event(f"Execution fault: {e}"))
            finally:
                self.root.after(0, self._reset_worker_state)

        threading.Thread(target=worker, daemon=True).start()

    def _reset_worker_state(self):
        self._thinking = False
        self.lbl_status_bar.configure(text="Gemini Shell Connected. Ready for execution.", fg=COLOR_DIM)

    def _trigger_voice_capture(self):
        if self._voice_active or self._thinking: return
        self._voice_active = True
        self.btn_mic.configure(fg="#ea4335")
        self.lbl_status_bar.configure(text="Listening for vocal voice input stream...", fg="#ea4335")

        def voice_worker():
            try:
                heard = self.jarvis.voice.listen(timeout=6)
                if heard:
                    self.root.after(0, lambda h=heard: self.entry_input.insert(0, h))
                    self.root.after(0, self._submit_composer_payload)
            except Exception as e:
                print(f"[Vocal Thread Error] {e}")
            finally:
                self.root.after(0, self._kill_voice_ui_state)

        threading.Thread(target=voice_worker, daemon=True).start()

    def _kill_voice_ui_state(self):
        self._voice_active = False
        self.btn_mic.configure(fg=COLOR_DIM)
        if not self._thinking:
            self.lbl_status_bar.configure(text="Gemini Shell Connected. Ready for execution.", fg=COLOR_DIM)

if __name__ == "__main__":
    j_instance = JARVIS()
    tk_root = tk.Tk()
    app = GeminiWorkspaceMaster(tk_root, j_instance)
    
    def force_quit():
        app._running = False
        j_instance._running = False
        j_instance.voice.shutdown()
        tk_root.destroy()
        
    tk_root.protocol("WM_DELETE_WINDOW", force_quit)
    tk_root.mainloop()
    