"""Single-slot scheduler for coalescing streaming render updates."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class StreamRenderScheduler:
    """Coalesce dirty notifications into serial, frame-paced flushes.

    Every flush callback is owned by ``_runner``.  Final flush callers publish a
    generation, wake that runner for an immediate drain, and wait until their
    generation has been processed.
    """

    def __init__(
        self,
        flush: Callable[[], Awaitable[None]],
        interval: float,
        busy_interval: float,
        metrics: Any = None,
    ) -> None:
        self._flush = flush
        self._interval = interval
        self._busy_interval = busy_interval
        self._metrics = metrics
        self._runner: asyncio.Task[None] | None = None
        self._generation = 0
        self._processed_generation = 0
        self._immediate_generation = 0
        self._final_waiters: list[tuple[int, asyncio.Future[None]]] = []
        self._wake_runner = asyncio.Event()
        self._closed = False

    @property
    def pending(self) -> bool:
        """Whether scheduler-owned work is in flight."""
        return self._runner is not None and not self._runner.done()

    @property
    def dirty(self) -> bool:
        """Whether a newer state is waiting to be rendered."""
        return not self._closed and self._generation > self._processed_generation

    async def mark_dirty(self) -> None:
        """Mark the latest state dirty and ensure the runner is scheduled."""
        if self._closed:
            return

        if self.dirty:
            self._increment("stream.render.merged")
        self._generation += 1
        self._increment("stream.render.dirty")
        self._ensure_runner()

    async def flush_final(self) -> None:
        """Ask the runner to immediately drain through a target generation."""
        if self._closed:
            return

        self._generation += 1
        target = self._generation
        self._immediate_generation = max(self._immediate_generation, target)
        waiter = asyncio.get_running_loop().create_future()
        self._final_waiters.append((target, waiter))
        self._ensure_runner()
        self._wake_runner.set()

        try:
            await waiter
        finally:
            self._final_waiters = [
                item for item in self._final_waiters if item[1] is not waiter
            ]

    async def close(self) -> None:
        """Atomically stop new work, cancel, and observe the unique runner.

        Runner cancellation is consumed, while cancellation of this ``close``
        invocation itself continues to propagate to its caller.
        """
        if not self._closed:
            self._closed = True
            self._processed_generation = self._generation
            self._immediate_generation = self._processed_generation
            self._wake_runner.set()
            self._finish_waiters(self._processed_generation)

        runner = self._runner
        if runner is None or runner.done():
            return

        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)

    def _ensure_runner(self) -> None:
        if self._closed:
            return
        if self._runner is None or self._runner.done():
            runner = asyncio.create_task(self._run())
            self._runner = runner
            runner.add_done_callback(self._runner_done)

    async def _run(self) -> None:
        delay = self._interval
        while not self._closed and self.dirty:
            if self._immediate_generation <= self._processed_generation:
                await self._wait_for_frame_or_final(delay)

            if self._closed or not self.dirty:
                return

            target = self._generation
            elapsed, error = await self._flush_once()
            self._processed_generation = target
            if error is not None:
                self._fail_waiters(target, error)
            else:
                self._finish_waiters(target)

            if not self.dirty:
                return
            delay = (
                self._busy_interval if elapsed > self._interval else self._interval
            )

    async def _wait_for_frame_or_final(self, delay: float) -> None:
        """Wait for frame pacing unless a final request asks for an early drain."""
        self._wake_runner.clear()
        if (
            self._closed
            or self._immediate_generation > self._processed_generation
            or delay <= 0
        ):
            return
        try:
            await asyncio.wait_for(self._wake_runner.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _flush_once(self) -> tuple[float, Exception | None]:
        """Run one owned callback and return its true duration and outcome."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        error: Exception | None = None
        try:
            await self._flush()
        except Exception as exc:
            error = exc
        finally:
            elapsed = loop.time() - started
            self._observe("stream.render.flush", elapsed)
        if error is None:
            self._increment("stream.render.frames")
            self._increment("stream.render.flushes")
        return elapsed, error

    def _runner_done(self, runner: asyncio.Task[None]) -> None:
        """Consume every runner result and perform the sole runner transition."""
        try:
            error = runner.exception()
        except asyncio.CancelledError:
            error = None

        if self._runner is runner:
            self._runner = None

        if error is not None:
            self._closed = True
            self._processed_generation = self._generation
            self._immediate_generation = self._processed_generation
            self._wake_runner.set()
            self._fail_waiters(self._generation, error)
        elif not self._closed and self.dirty:
            self._ensure_runner()

    def _finish_waiters(self, through: int) -> None:
        for target, waiter in self._final_waiters:
            if target <= through and not waiter.done():
                waiter.set_result(None)

    def _fail_waiters(self, through: int, error: Exception) -> None:
        for target, waiter in self._final_waiters:
            if target <= through and not waiter.done():
                waiter.set_exception(error)

    def _increment(self, name: str) -> None:
        try:
            increment = getattr(self._metrics, "increment", None)
            if callable(increment):
                increment(name)
        except Exception:
            pass

    def _observe(self, name: str, seconds: float) -> None:
        try:
            observe = getattr(self._metrics, "observe", None)
            if callable(observe):
                observe(name, seconds)
        except Exception:
            pass
