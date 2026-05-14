"""Utility helpers for desktop_automation.
Provides screenshot saving, template matching (OpenCV fallback), and simple file helpers.
"""
from typing import Optional, Tuple
from .core import DesktopAutomation


def save_screenshot(path: str, da: Optional[DesktopAutomation] = None) -> bool:
    """Capture a screenshot via DesktopAutomation and save to the given path.
    Returns True on success, False otherwise.
    """
    try:
        if da is None:
            da = DesktopAutomation()
        img_bytes = da.screenshot()
        if not img_bytes:
            return False
        with open(path, 'wb') as f:
            f.write(img_bytes)
        return True
    except Exception:
        return False


def find_image_on_screen(template_path: str, threshold: float = 0.8) -> Optional[Tuple[int, int, int, int]]:
    """Find template image on the current screen.
    Returns bounding box (left, top, width, height) of best match or None.
    Tries OpenCV template matching first, falls back to pyautogui.locateOnScreen when available.
    """
    try:
        # Try OpenCV approach
        import cv2
        import numpy as np
        from io import BytesIO
        # capture screenshot as bytes
        da = DesktopAutomation()
        img_bytes = da.screenshot()
        if not img_bytes:
            return None
        screen_array = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template is None or screen_array is None:
            return None
        res = cv2.matchTemplate(screen_array, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val >= threshold:
            top_left = max_loc
            h, w = template.shape[:2]
            return (int(top_left[0]), int(top_left[1]), int(w), int(h))
    except Exception:
        pass

    # Fallback to pyautogui.locateOnScreen
    try:
        import pyautogui
        loc = pyautogui.locateOnScreen(template_path, confidence=threshold)
        if loc:
            return (loc.left, loc.top, loc.width, loc.height)
    except Exception:
        pass

    return None


def read_text_file(path: str) -> Optional[str]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return None


def write_text_file(path: str, content: str) -> bool:
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception:
        return False
