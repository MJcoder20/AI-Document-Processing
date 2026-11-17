import { useCallback, useEffect, useState } from "react";
import {
  getLiveness,
  getReadiness,
  getWorkerHealth,
  getOperationalMetrics,
  getRequestMetrics,
  getWorkerMetrics,
  type LivenessResponse,
  type ReadinessResponse,
  type WorkerHealthResponse,
  type OperationalMetricsResponse,
  type RequestMetricsResponse,
  type WorkerMetricsResponse,
} from "../services/monitoring";
import "./MonitoringDashboard.css";
import ErrorManagement from "./ErrorManagement";


type MonitoringData = {
  liveness: LivenessResponse;
  readiness: ReadinessResponse;
  workerHealth: WorkerHealthResponse;
  operational: OperationalMetricsResponse;
  requests: RequestMetricsResponse;
  workerMetrics: WorkerMetricsResponse;
};

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string;
}) {
  return (
    <div className="monitor-card">
      <span className="monitor-label">{label}</span>
      <strong className="monitor-value">{value}</strong>
      {detail && <span className="monitor-detail">{detail}</span>}
    </div>
  );
}

function HealthIndicator({
  label,
  healthy,
  detail,
}: {
  label: string;
  healthy: boolean;
  detail: string;
}) {
  return (
    <div className="health-indicator">
      <div className={`health-dot ${healthy ? "healthy" : "unhealthy"}`} />
      <div>
        <strong>{label}</strong>
        <p>{detail}</p>
      </div>
      <span className={`health-badge ${healthy ? "healthy" : "unhealthy"}`}>
        {healthy ? "Healthy" : "Unavailable"}
      </span>
    </div>
  );
}

export default function MonitoringDashboard() {
  const [data, setData] = useState<MonitoringData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const refresh = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);

    try {
      const [
        liveness,
        readiness,
        workerHealth,
        operational,
        requests,
        workerMetrics,
      ] = await Promise.all([
        getLiveness(),
        getReadiness(),
        getWorkerHealth(),
        getOperationalMetrics(),
        getRequestMetrics(),
        getWorkerMetrics(),
      ]);

      setData({
        liveness,
        readiness,
        workerHealth,
        operational,
        requests,
        workerMetrics,
      });

      setError(null);
      setLastUpdated(new Date());
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to retrieve monitoring data.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();

    const interval = window.setInterval(() => {
      void refresh();
    }, 15000);

    return () => window.clearInterval(interval);
  }, [refresh]);

  if (loading) {
    return <section className="content-card">Loading system monitoring...</section>;
  }

  if (!data) {
    return (
      <section className="content-card">
        <p className="monitor-error">
          {error ?? "Monitoring data is unavailable."}
        </p>
        <button className="monitor-refresh" onClick={() => void refresh(true)}>
          Retry
        </button>
      </section>
    );
  }

  const requests = data.requests.requests;
  const worker = data.workerMetrics.worker;
  const queue = data.workerHealth.queue;
  const documents = data.operational.documents;
  const outbox = data.operational.outbox;

  const apiHealthy = data.liveness.status === "alive";
  const databaseHealthy = data.readiness.database === "connected";
  const workerHealthy = data.workerHealth.status === "healthy";

  return (
    <div className="monitoring-dashboard">
      <div className="monitor-toolbar">
        <div>
          <span className="monitor-updated">
            Last updated:{" "}
            {lastUpdated?.toLocaleTimeString() ?? "Not available"}
          </span>
          <p>Automatic refresh every 15 seconds</p>
        </div>

        <button
          className="monitor-refresh"
          onClick={() => void refresh(true)}
          disabled={refreshing}
        >
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && <div className="monitor-warning">{error} Showing last available data.</div>}

      <section className="content-card">
        <div className="monitor-section-heading">
          <div>
            <h2>System Health</h2>
            <p>Current availability of core platform services.</p>
          </div>
        </div>

        <div className="health-list">
          <HealthIndicator
            label="API Service"
            healthy={apiHealthy}
            detail="FastAPI application liveness"
          />
          <HealthIndicator
            label="Database"
            healthy={databaseHealthy}
            detail={data.readiness.database}
          />
          <HealthIndicator
            label="Background Worker"
            healthy={workerHealthy}
            detail="Outbox processing and queue statistics"
          />
        </div>
      </section>

      <section className="content-card">
        <div className="monitor-section-heading">
          <div>
            <h2>Request Performance</h2>
            <p>HTTP request volume, errors, and response latency.</p>
          </div>
        </div>

        <div className="monitor-grid">
          <MetricCard label="Total Requests" value={requests.total_requests} />
          <MetricCard label="In Progress" value={requests.requests_in_progress} />
          <MetricCard
            label="Error Rate"
            value={`${requests.error_rate_percent}%`}
            detail={`${requests.client_errors} client / ${requests.server_errors} server errors`}
          />
          <MetricCard
            label="Average Latency"
            value={`${requests.latency_ms.average} ms`}
          />
          <MetricCard
            label="Minimum Latency"
            value={`${requests.latency_ms.minimum ?? 0} ms`}
          />
          <MetricCard
            label="Maximum Latency"
            value={`${requests.latency_ms.maximum} ms`}
          />
        </div>

        <div className="monitor-breakdown">
          <div>
            <h3>Requests by Method</h3>
            {Object.entries(requests.by_method).map(([method, count]) => (
              <div className="breakdown-row" key={method}>
                <span>{method}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>

          <div>
            <h3>Requests by Status Code</h3>
            {Object.entries(requests.by_status_code).map(([status, count]) => (
              <div className="breakdown-row" key={status}>
                <span>{status}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="content-card">
        <div className="monitor-section-heading">
          <div>
            <h2>Background Worker</h2>
            <p>Persistent execution history and current queue state.</p>
          </div>
        </div>

        <div className="monitor-grid">
          <MetricCard label="Total Attempts" value={worker.total_attempts} />
          <MetricCard label="Active Attempts" value={worker.active_attempts} />
          <MetricCard label="Processed" value={worker.processed} />
          <MetricCard label="Retried" value={worker.retried} />
          <MetricCard label="Failed" value={worker.failed} />
          <MetricCard label="Interrupted" value={worker.interrupted} />
          <MetricCard label="Lease Lost" value={worker.lease_lost} />
          <MetricCard label="Recovered Leases" value={worker.recovered_leases} />
          <MetricCard
            label="Average Execution"
            value={`${worker.duration_ms.average} ms`}
          />
        </div>

        <div className="monitor-breakdown">
          <div>
            <h3>Queue Status</h3>
            <div className="breakdown-row"><span>Pending</span><strong>{queue.pending}</strong></div>
            <div className="breakdown-row"><span>Processing</span><strong>{queue.processing}</strong></div>
            <div className="breakdown-row"><span>Processed</span><strong>{queue.processed}</strong></div>
            <div className="breakdown-row"><span>Failed</span><strong>{queue.failed}</strong></div>
            <div className="breakdown-row"><span>Retrying</span><strong>{queue.retrying}</strong></div>
          </div>
          <div>
            <h3>Execution Duration</h3>
            <div className="breakdown-row"><span>Minimum</span><strong>{worker.duration_ms.minimum ?? 0} ms</strong></div>
            <div className="breakdown-row"><span>Maximum</span><strong>{worker.duration_ms.maximum} ms</strong></div>
          </div>
        </div>
      </section>

      <section className="content-card">
        <div className="monitor-section-heading">
          <div>
            <h2>Document & Outbox Statistics</h2>
            <p>Database-backed operational totals.</p>
          </div>
        </div>

        <div className="monitor-grid">
          <MetricCard label="Total Documents" value={documents.total} />
          <MetricCard label="Outbox Messages" value={outbox.total} />
          <MetricCard label="Pending Backlog" value={outbox.pending_backlog} />
          <MetricCard label="Retrying Messages" value={outbox.retrying} />
        </div>

        <div className="monitor-breakdown">
          <div>
            <h3>Documents by Status</h3>
            {Object.entries(documents.by_status).map(([status, count]) => (
              <div className="breakdown-row" key={status}>
                <span>{status.replaceAll("_", " ")}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>

          <div>
            <h3>Documents by Type</h3>
            {Object.entries(documents.by_type).map(([type, count]) => (
              <div className="breakdown-row" key={type}>
                <span>{type.replaceAll("_", " ")}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </div>
      </section>
      <ErrorManagement />
    </div>
  );
}
