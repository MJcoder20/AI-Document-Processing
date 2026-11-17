
from app.core.worker_metrics import WorkerMetrics


def test_worker_metrics_tracks_successful_processing():
    metrics = WorkerMetrics()

    metrics.start_attempt()
    metrics.finish_attempt("processed", 25.0)

    result = metrics.snapshot()

    assert result["total_attempts"] == 1
    assert result["processed"] == 1
    assert result["active_attempts"] == 0
    assert result["duration_ms"]["average"] == 25.0


def test_worker_metrics_tracks_retries_and_failures():
    metrics = WorkerMetrics()

    metrics.start_attempt()
    metrics.finish_attempt("retried", 10.0)

    metrics.start_attempt()
    metrics.finish_attempt("failed", 20.0)

    result = metrics.snapshot()

    assert result["retried"] == 1
    assert result["failed"] == 1
    assert result["completed_attempts"] == 2


def test_worker_metrics_tracks_lease_recovery():
    metrics = WorkerMetrics()

    metrics.record_recovered_leases(3)

    assert metrics.snapshot()["recovered_leases"] == 3


def test_worker_metrics_tracks_processing_duration():
    metrics = WorkerMetrics()

    metrics.start_attempt()
    metrics.finish_attempt("processed", 10.0)

    metrics.start_attempt()
    metrics.finish_attempt("processed", 30.0)

    result = metrics.snapshot()

    assert result["duration_ms"]["average"] == 20.0
    assert result["duration_ms"]["minimum"] == 10.0
    assert result["duration_ms"]["maximum"] == 30.0


def test_worker_metrics_tracks_active_attempts():
    metrics = WorkerMetrics()

    metrics.start_attempt()
    metrics.start_attempt()

    assert metrics.snapshot()["active_attempts"] == 2

    metrics.finish_attempt("processed", 10.0)

    assert metrics.snapshot()["active_attempts"] == 1


def test_worker_metrics_reset():
    metrics = WorkerMetrics()

    metrics.start_attempt()
    metrics.finish_attempt("processed", 10.0)
    metrics.record_recovered_leases(2)
    metrics.reset()

    result = metrics.snapshot()

    assert result["total_attempts"] == 0
    assert result["processed"] == 0
    assert result["recovered_leases"] == 0
    assert result["active_attempts"] == 0
