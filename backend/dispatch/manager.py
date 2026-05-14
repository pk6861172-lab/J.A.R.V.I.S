"""Dispatch manager: lightweight sub-agent dispatcher for background tasks.

Provides an in-process task queue with simple status tracking and the ability to run
callables in background worker threads. This version adds a worker pool, retry
logic, backoff, and safer persistence.
"""
import threading
import uuid
import time
import os
from typing import Any, Callable, Dict, Optional
import queue
import math

from . import persistence
from backend import telemetry

# Load persisted tasks on import (best-effort)
try:
    _tasks: Dict[str, Dict[str, Any]] = persistence.load_tasks() or {}
except Exception:
    _tasks: Dict[str, Dict[str, Any]] = {}

_lock = threading.Lock()
_task_queue: "queue.Queue" = queue.Queue()
_workers: list = []
_shutdown = threading.Event()

# Worker pool size (bounded)
_WORKER_COUNT = max(2, min(4, (os.cpu_count() or 2)))


def _worker_loop(worker_id: int):
    while not _shutdown.is_set():
        try:
            item = _task_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        rid = item['id']
        func = item['func']
        args = item.get('args', ())
        kwargs = item.get('kwargs', {})
        attempts = item.get('attempts', 0)
        max_retries = item.get('retries', 0)
        backoff = item.get('backoff', 0.5)

        with _lock:
            _tasks.setdefault(rid, {})
            _tasks[rid]['status'] = 'running'
            _tasks[rid]['error'] = None
            try:
                persistence.save_tasks(_tasks)
            except Exception:
                pass
        try:
            telemetry.log_event('dispatch.task_running', {'id': rid, 'worker': worker_id})
        except Exception:
            pass

        try:
            res = func(*args, **kwargs)
            with _lock:
                _tasks[rid]['status'] = 'done'
                _tasks[rid]['result'] = res
                try:
                    persistence.save_tasks(_tasks)
                except Exception:
                    pass
            try:
                telemetry.log_event('dispatch.task_done', {'id': rid, 'result': res})
            except Exception:
                pass
        except Exception as e:
            attempts += 1
            with _lock:
                _tasks[rid]['status'] = 'failed'
                _tasks[rid]['error'] = str(e)
                try:
                    persistence.save_tasks(_tasks)
                except Exception:
                    pass
            try:
                telemetry.log_event('dispatch.task_failed', {'id': rid, 'error': str(e), 'attempts': attempts})
            except Exception:
                pass
            # retry logic
            if attempts <= max_retries and not _shutdown.is_set():
                # exponential backoff
                delay = backoff * (2 ** (attempts - 1)) if attempts > 0 else backoff
                # cap delay
                delay = min(delay, 30)
                # requeue the task with updated attempts
                item['attempts'] = attempts
                # sleep before requeuing to avoid busy loop
                time.sleep(delay)
                try:
                    _task_queue.put(item)
                except Exception:
                    pass
        finally:
            _task_queue.task_done()


# Start worker threads
for i in range(_WORKER_COUNT):
    t = threading.Thread(target=_worker_loop, args=(i,), daemon=True)
    t.start()
    _workers.append(t)


def start_task(func: Callable[..., Any], args: Optional[tuple] = None, kwargs: Optional[dict] = None, retries: int = 0, backoff: float = 0.5) -> str:
    """Schedule a callable to run in background. Returns request_id.

    Parameters:
    - retries: number of times to retry on failure (default 0)
    - backoff: base backoff in seconds for retries (default 0.5)
    """
    rid = str(uuid.uuid4())
    args = args or ()
    kwargs = kwargs or {}
    with _lock:
        _tasks[rid] = {"status": "queued", "result": None, "error": None}
        try:
            persistence.save_tasks(_tasks)
        except Exception:
            pass
    try:
        telemetry.log_event('dispatch.task_queued', {'id': rid, 'func': getattr(func, '__name__', str(func))})
    except Exception:
        pass

    item = {'id': rid, 'func': func, 'args': args, 'kwargs': kwargs, 'retries': retries, 'backoff': backoff, 'attempts': 0}
    _task_queue.put(item)
    return rid


def get_status(request_id: str) -> Dict[str, Any]:
    with _lock:
        if request_id not in _tasks:
            raise KeyError('request_id not found')
        return dict(_tasks[request_id])


def list_tasks() -> Dict[str, Dict[str, Any]]:
    with _lock:
        return {k: dict(v) for k, v in _tasks.items()}


def shutdown(wait: bool = False, timeout: Optional[float] = None):
    """Signal workers to shut down. Optionally wait for termination."""
    _shutdown.set()
    if wait:
        start = time.time()
        for w in _workers:
            remaining = None
            if timeout is not None:
                elapsed = time.time() - start
                remaining = max(0, timeout - elapsed)
            w.join(remaining)


# Simple example worker function
def example_job(duration: int = 1):
    time.sleep(duration)
    return {'slept': duration}
