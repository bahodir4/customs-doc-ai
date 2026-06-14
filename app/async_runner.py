"""Sync wrapper around async coroutines for Streamlit.

A single event loop runs forever in a daemon thread. All async calls are
submitted to it via run_coroutine_threadsafe(), so HTTP clients and connection
objects created by the services are always used on the same loop — no
"Event loop is closed" errors.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Awaitable, TypeVar

import streamlit as st

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            t = threading.Thread(target=_loop.run_forever, daemon=True)
            t.start()
    return _loop


def run_async(coro: Awaitable[T]) -> T:
    """Run a coroutine on the shared background event loop and block until done."""
    future = asyncio.run_coroutine_threadsafe(coro, _get_loop())
    return future.result()


def init_on_loop(factory):
    """Compatibility shim — no longer needed."""
    return factory()
