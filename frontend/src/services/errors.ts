
import { apiRequest } from "./apiClient";

export type ErrorEventStatus = "open" | "investigating" | "resolved";

export interface ErrorEvent {
  id: string;
  request_id: string | null;
  message_id: string | null;
  document_id: string | null;
  severity: string;
  category: string;
  error_type: string;
  message: string;
  endpoint: string | null;
  method: string | null;
  status: ErrorEventStatus;
  occurred_at: string;
  resolved_at: string | null;
}

export interface ErrorEventDetail extends ErrorEvent {
  traceback: string | null;
}

export interface ErrorEventListResponse {
  items: ErrorEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface ErrorEventMetrics {
  total: number;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  by_category: Record<string, number>;
  last_24_hours: number;
}

export interface ErrorEventFilters {
  limit?: number;
  offset?: number;
  status?: ErrorEventStatus;
  severity?: string;
  category?: string;
  search?: string;
}

export async function getErrorEvents(
  filters: ErrorEventFilters = {},
): Promise<ErrorEventListResponse> {
  const params = new URLSearchParams();

  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  });

  const query = params.toString();

  return apiRequest<ErrorEventListResponse>(
    `/errors/${query ? `?${query}` : ""}`,
  );
}

export async function getErrorEvent(
  errorId: string,
): Promise<ErrorEventDetail> {
  return apiRequest<ErrorEventDetail>(
    `/errors/${encodeURIComponent(errorId)}`,
  );
}

export async function updateErrorEventStatus(
  errorId: string,
  newStatus: ErrorEventStatus,
): Promise<ErrorEventDetail> {
  return apiRequest<ErrorEventDetail>(
    `/errors/${encodeURIComponent(errorId)}/status`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status: newStatus }),
    },
  );
}

export async function getErrorEventMetrics(): Promise<ErrorEventMetrics> {
  return apiRequest<ErrorEventMetrics>("/errors/metrics");
}
