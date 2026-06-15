"""Sync wrapper around async coroutines for Streamlit.

A single event loop runs forever in a daemon thread. All async calls are
submitted to it via run_coroutine_threadsafe(), so HTTP clients and connection
objects created by the services are always used on the same loop — no
"Event loop is closed" errors.
"""
from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any, AsyncGenerator, Awaitable, Callable, Generator, TypeVar

import streamlit as st

T = TypeVar("T")
_SENTINEL = object()

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


def stream_async(
    async_gen_factory: Callable[[], AsyncGenerator[Any, None]],
    timeout: float = 180.0,
) -> Generator[Any, None, None]:
    """Bridge an async generator to a sync generator via a Queue.

    Submit a zero-arg callable that returns an async generator:
        stream_async(lambda: my_async_gen(arg1, arg2))

    Items yielded by the async generator are relayed to the sync caller.
    Exceptions from the async side are re-raised in the sync generator.
    Blocks at most `timeout` seconds between tokens before raising TimeoutError.
    """
    q: queue.Queue[Any] = queue.Queue()

    async def _drain() -> None:
        try:
            async for item in async_gen_factory():
                q.put(item)
            q.put(_SENTINEL)
        except Exception as exc:  # noqa: BLE001
            q.put(exc)

    asyncio.run_coroutine_threadsafe(_drain(), _get_loop())

    while True:
        try:
            item = q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"Stream timed out after {timeout}s")
        if item is _SENTINEL:
            return
        if isinstance(item, BaseException):
            raise item
        yield item


def submit_to_loop(coro) -> "asyncio.Future[Any]":
    """Submit a coroutine to the shared background event loop."""
    return asyncio.run_coroutine_threadsafe(coro, _get_loop())


def init_on_loop(factory):
    """Compatibility shim — no longer needed."""
    return factory()
