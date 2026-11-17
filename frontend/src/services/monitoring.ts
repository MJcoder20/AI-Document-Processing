
const MONITORING_BASE_URL =
  import.meta.env.VITE_API_URL?.replace(/\/api\/v1\/?$/, "") ||
  "http://localhost:8000";

async function monitoringRequest<T>(endpoint: string): Promise<T> {
  const response = await fetch(`${MONITORING_BASE_URL}${endpoint}`, {
    headers: {
      Authorization: `Bearer ${sessionStorage.getItem("docuflow_access_token") || ""}`,
    },
  });

  if (!response.ok) {
    throw new Error(`Monitoring request failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

export interface LivenessResponse {
  status: string;
}

export interface ReadinessResponse {
  status: string;
  database: string;
}

export interface WorkerHealthResponse {
  status: string;
  queue: {
    pending: number;
    processing: number;
    processed: number;
    failed: number;
    retrying: number;
  };
}

export interface OperationalMetricsResponse {
  status: string;
  documents: {
    total: number;
    by_status: Record<string, number>;
    by_type: Record<string, number>;
  };
  outbox: {
    total: number;
    by_status: Record<string, number>;
    pending_backlog: number;
    retrying: number;
  };
}

export interface RequestMetricsResponse {
  status: string;
  requests: {
    total_requests: number;
    requests_in_progress: number;
    client_errors: number;
    server_errors: number;
    error_rate_percent: number;
    latency_ms: {
      average: number;
      minimum: number | null;
      maximum: number;
    };
    by_status_code: Record<string, number>;
    by_method: Record<string, number>;
  };
}

export interface WorkerMetricsResponse {
  status: string;
  worker: {
    total_attempts: number;
    active_attempts: number;
    completed_attempts: number;
    processed: number;
    retried: number;
    failed: number;
    lease_lost: number;
    interrupted: number;
    recovered_leases: number;
    duration_ms: {
      average: number;
      minimum: number | null;
      maximum: number;
    };
  };
}

export const getLiveness = () =>
  monitoringRequest<LivenessResponse>("/health/live");

export const getReadiness = () =>
  monitoringRequest<ReadinessResponse>("/health/ready");

export const getWorkerHealth = () =>
  monitoringRequest<WorkerHealthResponse>("/health/worker");

export const getOperationalMetrics = () =>
  monitoringRequest<OperationalMetricsResponse>("/health/metrics");

export const getRequestMetrics = () =>
  monitoringRequest<RequestMetricsResponse>("/health/requests");

export const getWorkerMetrics = () =>
  monitoringRequest<WorkerMetricsResponse>("/health/worker/metrics");
