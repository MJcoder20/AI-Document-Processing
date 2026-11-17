
from collections import Counter
from threading import Lock


class WorkerMetrics:
    def __init__(self):
        self._lock = Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.total_attempts = 0
            self.active_attempts = 0
            self.total_duration_ms = 0.0
            self.min_duration_ms = None
            self.max_duration_ms = 0.0
            self.completed_attempts = 0
            self.outcomes = Counter()
            self.recovered_leases = 0

    def start_attempt(self):
        with self._lock:
            self.total_attempts += 1
            self.active_attempts += 1

    def finish_attempt(self, outcome: str, duration_ms: float):
        with self._lock:
            self.active_attempts = max(0, self.active_attempts - 1)
            self.completed_attempts += 1
            self.outcomes[outcome] += 1
            self.total_duration_ms += duration_ms

            if self.min_duration_ms is None:
                self.min_duration_ms = duration_ms
            else:
                self.min_duration_ms = min(
                    self.min_duration_ms, duration_ms
                )

            self.max_duration_ms = max(
                self.max_duration_ms, duration_ms
            )

    def record_recovered_leases(self, count: int):
        with self._lock:
            self.recovered_leases += count

    def snapshot(self):
        with self._lock:
            return {
                "total_attempts": self.total_attempts,
                "active_attempts": self.active_attempts,
                "completed_attempts": self.completed_attempts,
                "processed": self.outcomes["processed"],
                "retried": self.outcomes["retried"],
                "failed": self.outcomes["failed"],
                "lease_lost": self.outcomes["lease_lost"],
                "interrupted": self.outcomes["interrupted"],
                "recovered_leases": self.recovered_leases,
                "duration_ms": {
                    "average": round(
                        self.total_duration_ms / self.completed_attempts,
                        2,
                    ) if self.completed_attempts else 0.0,
                    "minimum": self.min_duration_ms,
                    "maximum": self.max_duration_ms,
                },
            }


worker_metrics = WorkerMetrics()
