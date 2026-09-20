"""Keeps the model health fresh while the server runs, so a lapsed key shows before a case."""

from __future__ import annotations

import os
import threading

from trueup.gateway import llm

INTERVAL_SECONDS = 60.0

_stop = threading.Event()
_thread: threading.Thread | None = None


def start(interval: float = INTERVAL_SECONDS) -> bool:
    """Probe the model on a timer. Does nothing without credentials, so tests never call out."""
    global _thread
    if not llm.available() or os.environ.get("TRUEUP_MODEL_PROBE") == "0":
        return False
    if _thread is not None and _thread.is_alive():
        return False
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(interval,), daemon=True, name="model-probe")
    _thread.start()
    return True


def stop() -> None:
    _stop.set()


def _loop(interval: float) -> None:
    while not _stop.is_set():
        llm.probe()
        _stop.wait(interval)
