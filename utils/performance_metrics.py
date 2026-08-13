"""Optional, bounded, in-memory performance metric aggregation."""

from __future__ import annotations

import math
import os
import threading
from collections import deque
from typing import TypeAlias

MetricValue: TypeAlias = int | float
MetricSnapshot: TypeAlias = dict[str, dict[str, MetricValue]]


class PerfMetrics:
    """Thread-safe counters/timings, disabled by default and never written to disk."""

    def __init__(self, sample_limit: int = 256) -> None:
        value = os.environ.get("QOZE_PERF_DEBUG", "")
        self.enabled = value.strip().lower() in {"1", "true", "yes", "on"}
        self._metrics: MetricSnapshot = {}
        self._sample_limit = max(1, sample_limit)
        self._samples: dict[str, deque[MetricValue]] = {}
        self._lock = threading.Lock()

    def increment(self, name: str, value: MetricValue = 1) -> None:
        self._record(name, value, percentile=False)

    def observe(self, name: str, seconds: float) -> None:
        self._record(name, seconds, percentile=True)

    def _record(self, name: str, value: MetricValue, *, percentile: bool) -> None:
        if not self.enabled:
            return
        with self._lock:
            metric = self._metrics.get(name)
            if metric is None:
                self._metrics[name] = {"count": 1, "total": value, "max": value}
            else:
                metric["count"] += 1
                metric["total"] += value
                metric["max"] = max(metric["max"], value)
            if percentile:
                self._samples.setdefault(name, deque(maxlen=self._sample_limit)).append(value)

    @staticmethod
    def _percentile(values: list[MetricValue], fraction: float) -> MetricValue:
        ordered = sorted(values)
        return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]

    def snapshot(self, reset: bool = False) -> MetricSnapshot:
        if not self.enabled:
            return {}
        with self._lock:
            result = {name: values.copy() for name, values in self._metrics.items()}
            for name, samples in self._samples.items():
                if samples and name in result:
                    values = list(samples)
                    result[name]["p50"] = self._percentile(values, 0.50)
                    result[name]["p95"] = self._percentile(values, 0.95)
            if reset:
                self._metrics.clear()
                self._samples.clear()
            return result

    def periodic_summary(self, reset: bool = False) -> MetricSnapshot:
        """Return a caller-paced aggregate summary; no timer and no I/O are created."""
        return self.snapshot(reset=reset)


_perf_metrics: PerfMetrics | None = None
_perf_metrics_lock = threading.Lock()


def get_perf_metrics() -> PerfMetrics:
    global _perf_metrics
    if _perf_metrics is None:
        with _perf_metrics_lock:
            if _perf_metrics is None:
                _perf_metrics = PerfMetrics()
    return _perf_metrics
