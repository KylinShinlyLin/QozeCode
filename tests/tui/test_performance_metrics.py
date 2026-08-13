import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest


from utils.performance_metrics import PerfMetrics, get_perf_metrics


def test_disabled_by_default_does_not_retain_samples(monkeypatch):
    monkeypatch.delenv("QOZE_PERF_DEBUG", raising=False)
    metrics = PerfMetrics()

    metrics.increment("stream.chunks")
    metrics.observe("stream.render", 0.25)

    assert metrics.enabled is False
    assert metrics.snapshot() == {}


def test_enabled_aggregates_count_total_max_and_can_reset(monkeypatch):
    monkeypatch.setenv("QOZE_PERF_DEBUG", "1")
    metrics = PerfMetrics()

    metrics.increment("stream.chunks", 2)
    metrics.increment("stream.chunks", 3)
    metrics.observe("stream.render", 0.25)
    metrics.observe("stream.render", 0.75)

    assert metrics.enabled is True
    assert metrics.snapshot() == {
        "stream.chunks": {"count": 2, "total": 5, "max": 3},
        "stream.render": {
            "count": 2, "total": 1.0, "max": 0.75, "p50": 0.25, "p95": 0.75
        },
    }

    before_reset = metrics.snapshot(reset=True)
    assert before_reset["stream.chunks"] == {"count": 2, "total": 5, "max": 3}
    assert metrics.snapshot() == {}


def test_get_perf_metrics_returns_process_singleton():
    assert get_perf_metrics() is get_perf_metrics()


def test_increment_is_thread_safe(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv("QOZE_PERF_DEBUG", "true")
    metrics = PerfMetrics()

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: metrics.increment("stream.chunks"), range(1_000)))

    assert metrics.snapshot()["stream.chunks"] == {
        "count": 1_000,
        "total": 1_000,
        "max": 1,
    }


def test_recording_does_not_write_files(monkeypatch):
    monkeypatch.setenv("QOZE_PERF_DEBUG", "1")
    metrics = PerfMetrics()

    def fail_open(*args, **kwargs):
        raise AssertionError("performance recording must remain in memory")

    monkeypatch.setattr("builtins.open", fail_open)
    metrics.increment("stream.chunks")
    metrics.observe("stream.render", 0.1)


def test_snapshot_includes_bounded_percentiles_and_periodic_summary(monkeypatch):
    monkeypatch.setenv("QOZE_PERF_DEBUG", "1")
    metrics = PerfMetrics(sample_limit=32)
    for value in range(100):
        metrics.observe("stream.render.flush", value / 1000)

    metric = metrics.snapshot()["stream.render.flush"]
    assert metric["count"] == 100
    assert metric["p50"] == pytest.approx(0.083)
    assert metric["p95"] == pytest.approx(0.098)
    assert len(metrics._samples["stream.render.flush"]) <= 32
    summary = metrics.periodic_summary(reset=True)
    assert "stream.render.flush" in summary
    assert metrics.snapshot() == {}
