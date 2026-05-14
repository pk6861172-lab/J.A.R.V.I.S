"""Windows driver helpers for desktop automation.
This module contains platform-specific helpers (screen size, window lookup).
Uses win32 APIs when available and falls back safely.
"""

try:
    import ctypes
except Exception:
    ctypes = None


def get_screen_size() -> tuple:
    """Return (width, height) of the primary display."""
    try:
        if ctypes:
            user32 = ctypes.windll.user32
            # Some systems require DPI awareness
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
            return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    except Exception:
        pass
    return (1920, 1080)


def find_window_by_title(title_substr: str) -> int:
    """Find window handle by partial title. Return 0 if not found."""
    try:
        import win32gui
        def _enum(hwnd, results):
            txt = win32gui.GetWindowText(hwnd) or ''
            if title_substr.lower() in txt.lower():
                results.append(hwnd)
        results = []
        win32gui.EnumWindows(_enum, results)
        return results[0] if results else 0
    except Exception:
        # Best-effort fallback: not available on this platform
        return 0
