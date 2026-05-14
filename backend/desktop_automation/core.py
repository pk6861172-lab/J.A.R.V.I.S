"""Core desktop automation primitives.
This file provides high-level wrappers. Implementations should be Windows-friendly
and fall back gracefully when required packages or permissions are missing.
"""
from typing import Tuple
import time

try:
    import pyautogui
except Exception:
    pyautogui = None

from . import drivers


class DesktopAutomation:
    """High-level desktop automation API.

    Methods are implemented as lightweight wrappers so they can be mocked in tests.
    """

    def __init__(self, vision_model: str = "default"):
        self.vision_model = vision_model

    def screenshot(self) -> bytes:
        """Take a screenshot and return PNG bytes (if possible).
        Returns empty bytes when not supported.
        """
        if pyautogui is None:
            return b""
        img = pyautogui.screenshot()
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def switch_vision_model(self, model_name: str) -> None:
        """Switch vision model backend (placeholder)."""
        # Hook for swapping local/remote vision adapters
        self.vision_model = model_name

    def press_hotkey(self, *keys: str) -> None:
        """Press a sequence of hotkeys (e.g., 'win', 'r')."""
        if pyautogui is None:
            return
        pyautogui.hotkey(*keys)
        time.sleep(0.1)

    def type_text(self, text: str, use_clipboard_paste: bool = True) -> None:
        """Type text; prefer clipboard paste for special characters when available."""
        if pyautogui is None:
            return
        if use_clipboard_paste:
            try:
                import pyperclip
                pyperclip.copy(text)
                pyautogui.hotkey('ctrl', 'v')
                return
            except Exception:
                pass
        pyautogui.typewrite(text)

    def click(self, x: int, y: int, clicks: int = 1, right: bool = False) -> None:
        """Click at screen coordinates. Falls back to platform APIs if pyautogui unavailable."""
        button = 'right' if right else 'left'
        if pyautogui is not None:
            try:
                pyautogui.click(x=x, y=y, clicks=clicks, button=button)
                return
            except Exception:
                pass

        # Fallback: use Win32 mouse event via ctypes (best-effort)
        try:
            import ctypes
            import time as _t
            user32 = ctypes.windll.user32
            # move cursor
            user32.SetCursorPos(int(x), int(y))
            _t.sleep(0.02)
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            MOUSEEVENTF_RIGHTDOWN = 0x0008
            MOUSEEVENTF_RIGHTUP = 0x0010
            for _ in range(clicks):
                if right:
                    user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                    user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                else:
                    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                _t.sleep(0.05)
            return
        except Exception:
            return

    def double_click(self, x: int, y: int) -> None:
        self.click(x, y, clicks=2)

    def right_click(self, x: int, y: int) -> None:
        self.click(x, y, right=True)

    def scale_coordinates(self, thumb_w: int, thumb_h: int, tx: int, ty: int) -> Tuple[int, int]:
        """Scale coordinates from a thumbnail to actual screen resolution.
        Uses platform driver to determine primary display size and scales accordingly.
        """
        try:
            screen_w, screen_h = drivers.get_screen_size()
            sx = int(tx * screen_w / max(1, thumb_w))
            sy = int(ty * screen_h / max(1, thumb_h))
            return sx, sy
        except Exception:
            return tx, ty
