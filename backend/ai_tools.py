import requests
from backend.crud import get_integration_token

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "send_slack_message",
            "description": "Send a message to a Slack channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "The Slack channel name (e.g. '#general') or ID."},
                    "message": {"type": "string", "description": "The message to send."}
                },
                "required": ["channel", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_github_repos",
            "description": "List all GitHub repositories the user has access to.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_drive_files",
            "description": "List files in the user's Google Drive.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to a recipient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_email": {"type": "string", "description": "The recipient's email address."},
                    "subject": {"type": "string", "description": "The email subject."},
                    "body": {"type": "string", "description": "The body of the email."}
                },
                "required": ["to_email", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_calendar",
            "description": "Check the user's upcoming Google Calendar events.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "computer_use",
            "description": "Control the desktop cursor/keyboard and read the screen. Use this to autonomously interact with the PC GUI. Allowed actions: 'screenshot', 'click', 'right_click', 'middle_click', 'double_click', 'triple_click', 'left_click_drag', 'scroll', 'type', 'press', 'hotkey', 'move'. IMPORTANT: You have full autonomy. Execute clicks, scrolling, typing, and shortcuts immediately as requested. DO NOT ask the user for permission to proceed. For keyboard shortcuts like Windows+E, you MUST use the 'hotkey' action with keys=['win', 'e']. Do NOT use 'press' for shortcuts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["screenshot", "click", "right_click", "middle_click", "double_click", "triple_click", "left_click_drag", "scroll", "type", "press", "hotkey", "move"], "description": "The action to perform."},
                    "x": {"type": "integer", "description": "X coordinate for move/click/drag."},
                    "y": {"type": "integer", "description": "Y coordinate for move/click/drag."},
                    "text": {"type": "string", "description": "Text to type if action is 'type'."},
                    "amount": {"type": "integer", "description": "Amount to scroll (negative for down, positive for up) if action is 'scroll'."},
                    "key": {"type": "string", "description": "Keyboard key to press (e.g. 'enter', 'win', 'esc') if action is 'press'."},
                    "keys": {"type": "array", "items": {"type": "string"}, "description": "List of keys for hotkey (e.g. ['win', 'e'] or ['ctrl', 'c']) if action is 'hotkey'."}
                },
                "required": ["action"]
            }
        }
    }
]

def execute_tool(db, name: str, args: dict) -> str:
    if name == "send_slack_message":
        token_info = get_integration_token(db, None, 'slack')
        if not token_info or not token_info.get('access_token'):
            return "Error: Slack token not found. Please authenticate Slack first."
        
        headers = {'Authorization': f"Bearer {token_info['access_token']}"}
        resp = requests.post('https://slack.com/api/chat.postMessage', json={
            'channel': args.get('channel'),
            'text': args.get('message')
        }, headers=headers)
        
        if resp.ok and resp.json().get('ok'):
            return "Successfully sent Slack message."
        return f"Failed to send Slack message: {resp.text}"

    elif name == "list_github_repos":
        token_info = get_integration_token(db, None, 'github')
        if not token_info or not token_info.get('access_token'):
            return "Error: GitHub token not found. Please authenticate GitHub first."
        
        headers = {
            'Authorization': f'token {token_info.get("access_token")}',
            'Accept': 'application/vnd.github.v3+json'
        }
        resp = requests.get('https://api.github.com/user/repos', headers=headers)
        if resp.ok:
            repos = [repo['name'] for repo in resp.json()]
            return "Repositories: " + ", ".join(repos[:20])  # limit to 20 to avoid token limits
        return f"Failed to list GitHub repos: {resp.text}"

    elif name == "list_drive_files":
        token_info = get_integration_token(db, None, 'google_drive')
        if not token_info or not token_info.get('access_token'):
            return "Error: Google Drive token not found. Please authenticate Google Drive first."
        
        headers = {'Authorization': f"Bearer {token_info['access_token']}"}
        resp = requests.get('https://www.googleapis.com/drive/v3/files', headers=headers, params={'pageSize': 15})
        if resp.ok:
            files = [f.get('name', 'Unknown') for f in resp.json().get('files', [])]
            if not files:
                return "No files found in Google Drive."
            return "Recent files: " + ", ".join(files)
        return f"Failed to list Google Drive files: {resp.text}"
    

    elif name == "send_email":
        return f"Drafted email to {args.get('to_email')} with subject '{args.get('subject')}'. (Note: SMTP configuration required in settings to actually send)."

    elif name == "check_calendar":
        token_info = get_integration_token(db, None, 'google_drive') # Reuse google token if calendar scope exists
        if not token_info or not token_info.get('access_token'):
            return "Error: Google OAuth token not found. Please authenticate Google first."
        
        headers = {'Authorization': f"Bearer {token_info['access_token']}"}
        resp = requests.get('https://www.googleapis.com/calendar/v3/users/me/calendarList', headers=headers)
        if resp.ok:
            cals = [c.get('summary') for c in resp.json().get('items', [])]
            return "Found calendars: " + ", ".join(cals)
        return f"Failed to list calendar: {resp.text}"

    elif name == "computer_use":
        action = args.get("action")
        try:
            import pyautogui
            import base64
            import time as _time
            from io import BytesIO
            from PIL import ImageGrab
            
            if action == "screenshot":
                img = ImageGrab.grab()
                real_w, real_h = img.size
                # Scale down for LLM but keep enough detail for coordinate accuracy
                img.thumbnail((1024, 1024))
                thumb_w, thumb_h = img.size
                buffered = BytesIO()
                img.save(buffered, format="JPEG", quality=55)
                b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                return f"[SCREENSHOT DATA BASE64]: data:image/jpeg;base64,{b64}  ... Real screen: {real_w}x{real_h}, thumbnail: {thumb_w}x{thumb_h}. Provide coordinates in REAL screen space ({real_w}x{real_h})."
            
            elif action == "move":
                x, y = args.get("x", 0), args.get("y", 0)
                pyautogui.moveTo(x, y, duration=0.3)
                _time.sleep(0.5)
                return f"Mouse moved to {x}, {y}."
                
            elif action in ["click", "left_click"]:
                x, y = args.get("x"), args.get("y")
                if x is not None and y is not None:
                    pyautogui.click(x=x, y=y)
                else:
                    pyautogui.click()
                _time.sleep(1.0)
                return f"Left-clicked at {x}, {y}. Wait 1s for UI to update."
                    
            elif action in ["right_click", "rightclick"]:
                x, y = args.get("x"), args.get("y")
                if x is not None and y is not None:
                    pyautogui.rightClick(x=x, y=y)
                else:
                    pyautogui.rightClick()
                _time.sleep(1.0)
                return f"Right-clicked at {x}, {y}. A context menu should now be open. Take a screenshot to see it."
                
            elif action == "middle_click":
                pyautogui.middleClick()
                _time.sleep(0.5)
                return "Middle-clicked at current position."
                
            elif action == "double_click":
                x, y = args.get("x"), args.get("y")
                if x is not None and y is not None:
                    pyautogui.doubleClick(x=x, y=y)
                else:
                    pyautogui.doubleClick()
                _time.sleep(1.0)
                return f"Double-clicked at {x}, {y}."
                
            elif action == "triple_click":
                pyautogui.tripleClick()
                _time.sleep(0.5)
                return "Triple-clicked at current position."
                
            elif action == "left_click_drag":
                x, y = args.get("x"), args.get("y")
                if x is not None and y is not None:
                    pyautogui.dragTo(x, y, duration=0.5, button='left')
                    _time.sleep(0.5)
                    return f"Dragged mouse to {x}, {y}."
                return "Missing x, y for drag."
                
            elif action == "scroll":
                amount = args.get("amount", -500)
                pyautogui.scroll(amount)
                _time.sleep(0.5)
                return f"Scrolled by {amount}."
                
            elif action == "type":
                text = args.get("text", "")
                # Use clipboard paste for reliable Unicode/special character support
                try:
                    import pyperclip
                    pyperclip.copy(text)
                    pyautogui.hotkey('ctrl', 'v')
                except Exception:
                    # Fallback to direct typing if pyperclip unavailable
                    pyautogui.write(text, interval=0.05)
                _time.sleep(0.5)
                return f"Typed: '{text}'"
                
            elif action == "press":
                key = args.get("key", "")
                if key:
                    pyautogui.press(key)
                    _time.sleep(0.5)
                    return f"Pressed key: '{key}'"
                return "No key provided."
                
            elif action == "hotkey":
                keys = args.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
                    _time.sleep(1.5)  # Extra wait for OS shortcuts like Win+E
                    return f"Pressed hotkey: {'+'.join(keys)}. Window should now be open. Take a screenshot to verify."
                return "No keys provided for hotkey."
                
            return "Unknown action."
        except Exception as e:
            return f"Computer use error: {e}"

    return f"Error: Tool {name} not implemented."
