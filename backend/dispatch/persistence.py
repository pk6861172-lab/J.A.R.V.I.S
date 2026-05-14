"""Persistence helpers for dispatch tasks.
Saves and loads tasks to a JSON file under the dispatch package directory.
Implements atomic writes to avoid partial files when writing from multiple threads/processes.
"""
import json
import os
import tempfile
from typing import Dict, Any

TASKS_FILE = os.path.join(os.path.dirname(__file__), 'tasks.json')


def save_tasks(tasks: Dict[str, Dict[str, Any]]) -> None:
    try:
        # Convert any non-serializable objects conservatively by stringifying
        serializable = {}
        for k, v in tasks.items():
            serializable[k] = {
                'status': v.get('status'),
                'result': v.get('result'),
                'error': v.get('error')
            }
        # atomic write: write to temp file then replace
        dirpath = os.path.dirname(TASKS_FILE)
        if not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dirpath)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            # atomic replace
            os.replace(tmp_path, TASKS_FILE)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
    except Exception:
        # Best-effort: do not raise
        pass


def load_tasks() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(TASKS_FILE):
        return {}
    try:
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception:
        return {}
