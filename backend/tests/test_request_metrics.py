
from app.core.request_metrics import RequestMetrics, request_metrics


def test_request_metrics_tracks_requests_and_latency():
    metrics = RequestMetrics()

    metrics.start_request()
    metrics.finish_request("GET", 200, 10.0)

    metrics.start_request()
    metrics.finish_request("POST", 201, 30.0)

    result = metrics.snapshot()

    assert result["total_requests"] == 2
    assert result["requests_in_progress"] == 0
    assert result["by_status_code"] == {
        "200": 1,
        "201": 1,
    }
    assert result["by_method"] == {
        "GET": 1,
        "POST": 1,
    }
    assert result["latency_ms"]["average"] == 20.0
    assert result["latency_ms"]["minimum"] == 10.0
    assert result["latency_ms"]["maximum"] == 30.0


def test_request_metrics_tracks_error_rates():
    metrics = RequestMetrics()

    metrics.finish_request("GET", 200, 10.0)
    metrics.finish_request("GET", 404, 10.0)
    metrics.finish_request("POST", 500, 20.0)

    result = metrics.snapshot()

    assert result["client_errors"] == 1
    assert result["server_errors"] == 1
    assert result["error_rate_percent"] == 66.67


def test_request_metrics_tracks_in_progress_requests():
    metrics = RequestMetrics()

    metrics.start_request()

    result = metrics.snapshot()

    assert result["requests_in_progress"] == 1
    assert result["total_requests"] == 0

    metrics.finish_request("GET", 200, 5.0)

    assert metrics.snapshot()["requests_in_progress"] == 0


def test_request_metrics_reset():
    metrics = RequestMetrics()

    metrics.finish_request("GET", 200, 10.0)
    metrics.reset()

    result = metrics.snapshot()

    assert result["total_requests"] == 0
    assert result["requests_in_progress"] == 0
    assert result["by_status_code"] == {}
    assert result["by_method"] == {}
    assert result["latency_ms"]["average"] == 0.0


def test_request_metrics_endpoint(client=None):
    # Endpoint integration is covered by the application TestClient.
    from fastapi.testclient import TestClient
    from app.main import app

    response = TestClient(app).get("/health/requests")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert "requests" in response.json()
