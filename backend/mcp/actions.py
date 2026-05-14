"""Additional MCP actions: image-finding and typed mouse flows."""
import base64
import tempfile
import os
from typing import Dict, Any, List

try:
    import pyautogui
except Exception:
    pyautogui = None

from backend.desktop_automation.core import DesktopAutomation
from backend.desktop_automation import utils as da_utils

_da = DesktopAutomation()


def find_image(image_b64: str = None, confidence: float = 0.8) -> Dict[str, Any]:
    """Find an image on screen. Accepts base64-encoded PNG. Returns bounding box or None.
    Tries OpenCV-based matching (via desktop_automation.utils) first, then falls back to pyautogui.
    """
    if not image_b64:
        return {"found": False, "reason": "no image provided"}
    try:
        data = base64.b64decode(image_b64)
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        with open(path, 'wb') as f:
            f.write(data)

        # Try the OpenCV-based helper
        try:
            bbox = da_utils.find_image_on_screen(path, threshold=confidence)
            if bbox:
                left, top, width, height = bbox
                try:
                    os.remove(path)
                except Exception:
                    pass
                return {"found": True, "left": left, "top": top, "width": width, "height": height}
        except Exception:
            pass

        # Fallback to pyautogui locateOnScreen
        if pyautogui is not None:
            try:
                loc = pyautogui.locateOnScreen(path, confidence=confidence)
            except Exception:
                try:
                    loc = pyautogui.locateOnScreen(path)
                except Exception:
                    loc = None
            try:
                os.remove(path)
            except Exception:
                pass
            if not loc:
                return {"found": False}
            left, top, width, height = loc.left, loc.top, loc.width, loc.height
            return {"found": True, "left": left, "top": top, "width": width, "height": height}

        try:
            os.remove(path)
        except Exception:
            pass
        return {"found": False, "reason": "no matching method available"}
    except Exception as e:
        return {"found": False, "reason": str(e)}


def typed_mouse_flow(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute a sequence of simple steps: hotkey/type/click/scroll.
    Each step is a dict with 'op' and op-specific params.
    Example: {'op':'hotkey','keys':['win','r']}, {'op':'type','text':'notepad'}, {'op':'press','key':'enter'}, {'op':'click','x':100,'y':200}
    """
    try:
        for s in steps:
            op = s.get('op')
            if op == 'hotkey':
                keys = s.get('keys', [])
                _da.press_hotkey(*keys)
            elif op == 'type':
                text = s.get('text','')
                _da.type_text(text)
            elif op == 'press':
                key = s.get('key')
                # simple mapping
                if key:
                    _da.press_hotkey(key)
            elif op == 'click':
                x = int(s.get('x',0)); y = int(s.get('y',0))
                clicks = int(s.get('clicks',1)); right = bool(s.get('right',False))
                _da.click(x,y,clicks=clicks,right=right)
            elif op == 'double_click':
                x = int(s.get('x',0)); y = int(s.get('y',0))
                _da.double_click(x,y)
            elif op == 'scroll':
                pixels = int(s.get('pixels',500))
                try:
                    import pyautogui as _pg
                    if _pg:
                        _pg.scroll(-pixels)
                except Exception:
                    pass
            else:
                # unknown op, skip
                continue
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}
