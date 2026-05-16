"""
AI Tools for J.A.R.V.I.S Cowork Mode.

Provides the TOOLS_SCHEMA (OpenAI function-calling format) and execute_tool()
so the AI brain can perform physical desktop actions via pyautogui.
"""

import base64
import io
import json
import time

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.15
    _HAS_PYAUTOGUI = True
except ImportError:
    _HAS_PYAUTOGUI = False

# ---------------------------------------------------------------------------
#  TOOLS_SCHEMA — OpenAI function-calling format
# ---------------------------------------------------------------------------

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "computer_use",
            "description": (
                "Perform a physical action on the user's computer. "
                "Use action='screenshot' to see the screen first, then "
                "'click', 'type', 'press', 'hotkey', or 'drag' to interact."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["screenshot", "click", "type", "press", "hotkey", "drag", "wait"],
                        "description": (
                            "The action to perform. "
                            "'screenshot' captures the screen. "
                            "'click' clicks at (x, y). "
                            "'type' types a string of text. "
                            "'press' presses a single key. "
                            "'hotkey' presses a key combination. "
                            "'drag' drags from (x, y) to (drag_to_x, drag_to_y). "
                            "'wait' pauses for 'seconds' (default 2) to let an app load."
                        ),
                    },
                    "x": {
                        "type": "integer",
                        "description": "X coordinate in real screen pixels (for click/drag).",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate in real screen pixels (for click/drag).",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type (for action='type').",
                    },
                    "key": {
                        "type": "string",
                        "description": "Key name to press (for action='press'), e.g. 'enter', 'tab', 'escape'.",
                    },
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of keys for hotkey combo (for action='hotkey'), e.g. ['ctrl', 'c'].",
                    },
                    "clicks": {
                        "type": "integer",
                        "description": "Number of clicks (for action='click'). Default 1. Use 2 for double-click.",
                    },
                    "right": {
                        "type": "boolean",
                        "description": "If true, right-click instead of left-click.",
                    },
                    "drag_to_x": {
                        "type": "integer",
                        "description": "Destination X coordinate (for action='drag').",
                    },
                    "drag_to_y": {
                        "type": "integer",
                        "description": "Destination Y coordinate (for action='drag').",
                    },
                    "seconds": {
                        "type": "number",
                        "description": "Seconds to wait (for action='wait'). Default 2, max 10.",
                    },
                },
                "required": ["action"],
            },
        },
    }
]


# ---------------------------------------------------------------------------
#  execute_tool — run tool by name and return a result string
# ---------------------------------------------------------------------------

def execute_tool(db, func_name: str, func_args: dict) -> str:
    """Execute a tool call and return the result as a string.

    Parameters
    ----------
    db : SQLAlchemy session (unused for computer_use but kept for API compat)
    func_name : name of the tool function
    func_args : parsed JSON arguments from the model
    """
    if func_name == "computer_use":
        return _execute_computer_use(func_args)
    return f"Unknown tool: {func_name}"


def _execute_computer_use(args: dict) -> str:
    if not _HAS_PYAUTOGUI:
        return "Error: pyautogui is not installed. Run: pip install pyautogui"

    action = args.get("action", "")

    if action == "screenshot":
        return _take_screenshot()

    elif action == "click":
        x = args.get("x")
        y = args.get("y")
        if x is None or y is None:
            return "Error: click requires 'x' and 'y' coordinates."
        clicks = args.get("clicks", 1)
        right = args.get("right", False)
        button = "right" if right else "left"
        try:
            pyautogui.click(x, y, clicks=clicks, button=button)
            time.sleep(0.3)
            return f"Clicked {'right' if right else 'left'} at ({x}, {y}), clicks={clicks}."
        except Exception as e:
            return f"Click error: {e}"

    elif action == "type":
        text = args.get("text", "")
        if not text:
            return "Error: type requires 'text' parameter."
        try:
            # Use pyperclip (cross-platform) for clipboard paste
            try:
                import pyperclip
                pyperclip.copy(text)
                time.sleep(0.1)
                pyautogui.hotkey("ctrl", "v")
            except (ImportError, Exception):
                # pyperclip not available, fall back to typewrite
                if text.isascii():
                    pyautogui.typewrite(text, interval=0.02)
                else:
                    pyautogui.write(text)
            time.sleep(0.3)
            return f"Typed: '{text[:80]}{'...' if len(text) > 80 else ''}'"
        except Exception as e:
            return f"Type error: {e}"

    elif action == "press":
        key = args.get("key", "")
        if not key:
            return "Error: press requires 'key' parameter."
        try:
            pyautogui.press(key)
            time.sleep(0.3)
            return f"Pressed key: '{key}'."
        except Exception as e:
            return f"Press error: {e}"

    elif action == "hotkey":
        keys = args.get("keys", [])
        if not keys:
            return "Error: hotkey requires 'keys' array."
        try:
            pyautogui.hotkey(*keys)
            time.sleep(0.5)
            return f"Pressed hotkey: {'+'.join(keys)}."
        except Exception as e:
            return f"Hotkey error: {e}"

    elif action == "drag":
        x = args.get("x")
        y = args.get("y")
        dx = args.get("drag_to_x")
        dy = args.get("drag_to_y")
        if None in (x, y, dx, dy):
            return "Error: drag requires 'x', 'y', 'drag_to_x', and 'drag_to_y'."
        try:
            pyautogui.moveTo(x, y)
            pyautogui.drag(dx - x, dy - y, duration=0.4)
            return f"Dragged from ({x}, {y}) to ({dx}, {dy})."
        except Exception as e:
            return f"Drag error: {e}"

    elif action == "wait":
        secs = min(args.get("seconds", 2), 10)
        time.sleep(secs)
        return f"Waited {secs} seconds."

    else:
        return f"Unknown action: '{action}'. Use: screenshot, click, type, press, hotkey, drag, wait."


def _take_screenshot() -> str:
    """Capture the screen and return a base64 data URL string."""
    try:
        screenshot = pyautogui.screenshot()
        # Resize for efficiency (model doesn't need full resolution)
        max_dim = 1280
        w, h = screenshot.size
        if w > max_dim or h > max_dim:
            scale = max_dim / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
            screenshot = screenshot.resize((new_w, new_h))

        buf = io.BytesIO()
        screenshot.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"
        return f"[SCREENSHOT DATA BASE64]: {data_url}"
    except Exception as e:
        return f"Screenshot error: {e}"
