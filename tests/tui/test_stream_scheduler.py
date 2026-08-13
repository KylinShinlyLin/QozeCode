"""Behavior tests for the single-slot stream render scheduler."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tui_components.messages.stream_scheduler import StreamRenderScheduler


def test_mark_dirty_coalesces_updates_within_one_interval() -> None:
    async def scenario() -> None:
        flush_count = 0

        async def flush() -> None:
            nonlocal flush_count
            flush_count += 1

        scheduler = StreamRenderScheduler(flush, interval=0.03, busy_interval=0.06)
        for _ in range(100):
            await scheduler.mark_dirty()

        assert scheduler.pending is True
        assert scheduler.dirty is True
        await asyncio.sleep(0.05)
        assert flush_count == 1
        assert scheduler.pending is False
        assert scheduler.dirty is False
        await scheduler.close()

    asyncio.run(scenario())


def test_dirty_during_flush_is_rendered_on_the_next_frame() -> None:
    async def scenario() -> None:
        flush_started = asyncio.Event()
        release_first_flush = asyncio.Event()
        flush_count = 0

        async def flush() -> None:
            nonlocal flush_count
            flush_count += 1
            if flush_count == 1:
                flush_started.set()
                await release_first_flush.wait()

        scheduler = StreamRenderScheduler(flush, interval=0.02, busy_interval=0.04)
        await scheduler.mark_dirty()
        await asyncio.wait_for(flush_started.wait(), timeout=0.2)
        await scheduler.mark_dirty()
        assert scheduler.dirty is True
        release_first_flush.set()

        await asyncio.sleep(0)
        assert flush_count == 1
        await asyncio.sleep(0.03)
        assert flush_count == 2
        assert scheduler.pending is False
        assert scheduler.dirty is False
        await scheduler.close()

    asyncio.run(scenario())


def test_flush_final_joins_runner_and_forces_latest_dirty_state() -> None:
    async def scenario() -> None:
        flush_started = asyncio.Event()
        release_first_flush = asyncio.Event()
        flush_count = 0

        async def flush() -> None:
            nonlocal flush_count
            flush_count += 1
            if flush_count == 1:
                flush_started.set()
                await release_first_flush.wait()

        scheduler = StreamRenderScheduler(flush, interval=0.01, busy_interval=0.08)
        await scheduler.mark_dirty()
        await asyncio.wait_for(flush_started.wait(), timeout=0.2)
        await scheduler.mark_dirty()

        final_task = asyncio.create_task(scheduler.flush_final())
        await asyncio.sleep(0)
        assert final_task.done() is False
        release_first_flush.set()
        await asyncio.wait_for(final_task, timeout=0.1)

        assert flush_count == 2
        assert scheduler.pending is False
        assert scheduler.dirty is False
        await scheduler.close()

    asyncio.run(scenario())


def test_slow_flush_uses_busy_interval_without_concurrent_flushes() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        starts: list[float] = []
        active_flushes = 0
        max_active_flushes = 0
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_finished = asyncio.Event()

        async def flush() -> None:
            nonlocal active_flushes, max_active_flushes
            starts.append(loop.time())
            active_flushes += 1
            max_active_flushes = max(max_active_flushes, active_flushes)
            try:
                if len(starts) == 1:
                    first_started.set()
                    await release_first.wait()
                else:
                    second_finished.set()
            finally:
                active_flushes -= 1

        scheduler = StreamRenderScheduler(flush, interval=0.01, busy_interval=0.05)
        await scheduler.mark_dirty()
        await asyncio.wait_for(first_started.wait(), timeout=0.2)
        await scheduler.mark_dirty()
        await asyncio.sleep(0.02)  # The first flush has already exceeded interval.
        release_time = loop.time()
        release_first.set()
        await asyncio.wait_for(second_finished.wait(), timeout=0.2)

        assert max_active_flushes == 1
        assert starts[1] - release_time >= 0.04
        await scheduler.close()

    asyncio.run(scenario())


def test_close_is_idempotent_stops_scheduling_and_propagates_caller_cancel() -> None:
    async def scenario() -> None:
        flush_started = asyncio.Event()
        hold_flush = asyncio.Event()
        flush_count = 0
        flush_cancelled = asyncio.Event()

        async def flush() -> None:
            nonlocal flush_count
            flush_count += 1
            flush_started.set()
            try:
                await hold_flush.wait()
            except asyncio.CancelledError:
                flush_cancelled.set()
                raise

        scheduler = StreamRenderScheduler(flush, interval=0.01, busy_interval=0.02)
        await scheduler.mark_dirty()
        await asyncio.wait_for(flush_started.wait(), timeout=0.2)

        close_task = asyncio.create_task(scheduler.close())
        await asyncio.wait_for(flush_cancelled.wait(), timeout=0.2)
        close_task.cancel()
        try:
            await close_task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("close() swallowed the caller's CancelledError")

        await scheduler.close()
        await scheduler.close()
        await scheduler.mark_dirty()
        await asyncio.sleep(0.03)
        assert flush_count == 1
        assert scheduler.pending is False
        assert scheduler.dirty is False

    asyncio.run(scenario())


def test_optional_metrics_use_only_increment_and_observe() -> None:
    class Metrics:
        def __init__(self) -> None:
            self.increments: list[tuple[object, ...]] = []
            self.observations: list[tuple[object, ...]] = []

        def increment(self, *args: object) -> None:
            self.increments.append(args)

        def observe(self, *args: object) -> None:
            self.observations.append(args)

    async def scenario() -> None:
        metrics = Metrics()

        async def flush() -> None:
            return None

        scheduler = StreamRenderScheduler(
            flush, interval=0.01, busy_interval=0.02, metrics=metrics
        )
        await scheduler.mark_dirty()
        await scheduler.flush_final()
        await scheduler.close()

        assert metrics.increments
        assert metrics.observations

        scheduler_without_metrics = StreamRenderScheduler(
            flush, interval=0.01, busy_interval=0.02
        )
        await scheduler_without_metrics.mark_dirty()
        await scheduler_without_metrics.flush_final()
        await scheduler_without_metrics.close()

    asyncio.run(scenario())


def test_fresh_flush_final_is_owned_by_the_single_runner() -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        callback_task: asyncio.Task[object] | None = None

        async def flush() -> None:
            nonlocal callback_task
            callback_task = asyncio.current_task()
            started.set()
            await release.wait()

        scheduler = StreamRenderScheduler(flush, interval=1.0, busy_interval=1.0)
        final_task = asyncio.create_task(scheduler.flush_final())
        await asyncio.wait_for(started.wait(), timeout=0.2)

        assert scheduler.pending is True
        assert callback_task is scheduler._runner

        release.set()
        await asyncio.wait_for(final_task, timeout=0.2)
        assert scheduler.pending is False
        assert scheduler.dirty is False
        await scheduler.close()

    asyncio.run(scenario())


def test_final_mark_and_close_share_and_stop_the_single_runner() -> None:
    async def scenario() -> None:
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_finished = asyncio.Event()
        cancelled = asyncio.Event()
        callback_tasks: list[asyncio.Task[object] | None] = []
        active = 0

        async def flush() -> None:
            nonlocal active
            callback_tasks.append(asyncio.current_task())
            active += 1
            try:
                if len(callback_tasks) == 1:
                    first_started.set()
                    await release_first.wait()
                else:
                    second_finished.set()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            finally:
                active -= 1

        scheduler = StreamRenderScheduler(flush, interval=0.01, busy_interval=0.02)
        final_task = asyncio.create_task(scheduler.flush_final())
        await asyncio.wait_for(first_started.wait(), timeout=0.2)
        await scheduler.mark_dirty()
        release_first.set()
        await asyncio.wait_for(second_finished.wait(), timeout=0.2)
        await asyncio.wait_for(final_task, timeout=0.2)

        assert len(callback_tasks) == 2
        assert callback_tasks[0] is callback_tasks[1]

        # A second final flush is deliberately held so close must find, cancel,
        # and observe the same scheduler-owned runner before returning.
        first_started.clear()
        release_first.clear()
        callback_tasks.clear()
        final_task = asyncio.create_task(scheduler.flush_final())
        await asyncio.wait_for(first_started.wait(), timeout=0.2)
        close_task = asyncio.create_task(scheduler.close())
        await asyncio.wait_for(cancelled.wait(), timeout=0.2)
        await asyncio.wait_for(close_task, timeout=0.2)
        await asyncio.wait_for(final_task, timeout=0.2)

        assert active == 0
        assert scheduler.pending is False
        assert scheduler.dirty is False
        await scheduler.mark_dirty()
        await asyncio.sleep(0.03)
        assert active == 0

    asyncio.run(scenario())


def test_concurrent_flush_final_calls_share_one_generation_drain() -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        flush_count = 0

        async def flush() -> None:
            nonlocal flush_count
            flush_count += 1
            started.set()
            await release.wait()

        scheduler = StreamRenderScheduler(flush, interval=1.0, busy_interval=1.0)
        first = asyncio.create_task(scheduler.flush_final())
        second = asyncio.create_task(scheduler.flush_final())
        await asyncio.wait_for(started.wait(), timeout=0.2)
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=0.2)

        assert flush_count == 1
        assert scheduler.pending is False
        assert scheduler.dirty is False
        await scheduler.close()

    asyncio.run(scenario())


def test_flush_exception_is_observed_and_final_waiter_receives_it() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        unobserved: list[dict[str, object]] = []
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: unobserved.append(context))
        calls = 0

        async def flush() -> None:
            nonlocal calls
            calls += 1
            raise RuntimeError(f"flush failed {calls}")

        try:
            scheduler = StreamRenderScheduler(flush, interval=0.0, busy_interval=0.0)
            await scheduler.mark_dirty()
            for _ in range(5):
                await asyncio.sleep(0)
            assert scheduler.pending is False
            assert unobserved == []

            try:
                await scheduler.flush_final()
            except RuntimeError as exc:
                assert str(exc) == "flush failed 2"
            else:
                raise AssertionError("flush_final() did not receive the flush error")

            assert scheduler.pending is False
            assert scheduler.dirty is False
            assert unobserved == []
            await scheduler.close()
        finally:
            loop.set_exception_handler(previous_handler)

    asyncio.run(scenario())


def test_metrics_exceptions_are_best_effort_and_do_not_restart_runner() -> None:
    class BrokenMetrics:
        def increment(self, *_args: object) -> None:
            raise RuntimeError("increment failed")

        def observe(self, *_args: object) -> None:
            raise RuntimeError("observe failed")

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        unobserved: list[dict[str, object]] = []
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: unobserved.append(context))
        flush_count = 0

        async def flush() -> None:
            nonlocal flush_count
            flush_count += 1

        try:
            scheduler = StreamRenderScheduler(
                flush,
                interval=1.0,
                busy_interval=1.0,
                metrics=BrokenMetrics(),
            )
            await scheduler.mark_dirty()
            await asyncio.wait_for(scheduler.flush_final(), timeout=0.2)
            for _ in range(3):
                await asyncio.sleep(0)

            assert flush_count == 1
            assert scheduler.pending is False
            assert scheduler.dirty is False
            assert unobserved == []
            await asyncio.wait_for(scheduler.close(), timeout=0.2)
        finally:
            loop.set_exception_handler(previous_handler)

    asyncio.run(scenario())


def test_runner_level_exception_fails_waiters_and_terminates_scheduler() -> None:
    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        unobserved: list[dict[str, object]] = []
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: unobserved.append(context))
        flush_count = 0

        async def flush() -> None:
            nonlocal flush_count
            flush_count += 1

        try:
            scheduler = StreamRenderScheduler(flush, interval=1.0, busy_interval=1.0)
            original_flush_once = scheduler._flush_once

            async def fail_after_successful_flush() -> tuple[float, Exception | None]:
                await original_flush_once()
                raise RuntimeError("unexpected runner failure")

            scheduler._flush_once = fail_after_successful_flush  # type: ignore[method-assign]

            final_tasks = [
                asyncio.create_task(scheduler.flush_final()),
                asyncio.create_task(scheduler.flush_final()),
            ]
            results = await asyncio.wait_for(
                asyncio.gather(*final_tasks, return_exceptions=True), timeout=0.2
            )
            assert len(results) == 2
            assert all(
                isinstance(result, RuntimeError)
                and str(result) == "unexpected runner failure"
                for result in results
            )

            for _ in range(3):
                await asyncio.sleep(0)

            assert flush_count == 1
            assert scheduler.pending is False
            assert scheduler.dirty is False
            assert unobserved == []
            await asyncio.wait_for(scheduler.close(), timeout=0.2)
            assert scheduler.pending is False
            assert scheduler.dirty is False
        finally:
            loop.set_exception_handler(previous_handler)

    asyncio.run(scenario())


def test_metrics_record_merged_notifications_and_flush_count() -> None:
    class Metrics:
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}
        def increment(self, name: str, value: int = 1) -> None:
            self.counts[name] = self.counts.get(name, 0) + value
        def observe(self, name: str, value: float) -> None:
            return None

    async def scenario() -> None:
        metrics = Metrics()
        scheduler = StreamRenderScheduler(
            lambda: asyncio.sleep(0), interval=1.0, busy_interval=1.0, metrics=metrics
        )
        await scheduler.mark_dirty()
        await scheduler.mark_dirty()
        await scheduler.mark_dirty()
        await scheduler.flush_final()
        await scheduler.close()
        assert metrics.counts["stream.render.dirty"] == 3
        assert metrics.counts["stream.render.merged"] >= 2
        assert metrics.counts["stream.render.flushes"] == 1

    asyncio.run(scenario())
