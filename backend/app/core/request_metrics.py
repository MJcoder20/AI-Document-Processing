
from collections import Counter
from threading import Lock


class RequestMetrics:
    def __init__(self):
        self._lock = Lock()
        self.reset()

    def reset(self):
        with getattr(self, "_lock", Lock()):
            self.total_requests = 0
            self.requests_in_progress = 0
            self.total_duration_ms = 0.0
            self.min_duration_ms = None
            self.max_duration_ms = 0.0
            self.status_codes = Counter()
            self.methods = Counter()

    def start_request(self):
        with self._lock:
            self.requests_in_progress += 1

    def finish_request(
        self,
        method: str,
        status_code: int,
        duration_ms: float,
    ):
        with self._lock:
            self.requests_in_progress = max(
                0, self.requests_in_progress - 1
            )

            self.total_requests += 1
            self.total_duration_ms += duration_ms
            self.status_codes[str(status_code)] += 1
            self.methods[method] += 1

            if self.min_duration_ms is None:
                self.min_duration_ms = duration_ms
            else:
                self.min_duration_ms = min(
                    self.min_duration_ms, duration_ms
                )

            self.max_duration_ms = max(
                self.max_duration_ms, duration_ms
            )

    def snapshot(self):
        with self._lock:
            total = self.total_requests

            client_errors = sum(
                count
                for status, count in self.status_codes.items()
                if status.startswith("4")
            )

            server_errors = sum(
                count
                for status, count in self.status_codes.items()
                if status.startswith("5")
            )

            return {
                "total_requests": total,
                "requests_in_progress": self.requests_in_progress,
                "client_errors": client_errors,
                "server_errors": server_errors,
                "error_rate_percent": round(
                    ((client_errors + server_errors) / total) * 100,
                    2,
                ) if total else 0.0,
                "latency_ms": {
                    "average": round(
                        self.total_duration_ms / total, 2
                    ) if total else 0.0,
                    "minimum": self.min_duration_ms,
                    "maximum": self.max_duration_ms,
                },
                "by_status_code": dict(self.status_codes),
                "by_method": dict(self.methods),
            }


request_metrics = RequestMetrics()
