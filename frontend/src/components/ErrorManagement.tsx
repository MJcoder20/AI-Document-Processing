
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import {
  getErrorEvents,
  getErrorEvent,
  getErrorEventMetrics,
  updateErrorEventStatus,
  type ErrorEvent,
  type ErrorEventDetail,
  type ErrorEventMetrics,
  type ErrorEventStatus,
} from "../services/errors";
import "./ErrorManagement.css";

const PAGE_SIZE = 10;

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="error-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function ErrorManagement() {
  const { user } = useAuth();

  const [items, setItems] = useState<ErrorEvent[]>([]);
  const [metrics, setMetrics] = useState<ErrorEventMetrics | null>(null);
  const [selected, setSelected] = useState<ErrorEventDetail | null>(null);

  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");

  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);

  const [loading, setLoading] = useState(true);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [listResponse, metricsResponse] = await Promise.all([
        getErrorEvents({
          limit: PAGE_SIZE,
          offset,
          status: status ? (status as ErrorEventStatus) : undefined,
          severity: severity || undefined,
          category: category || undefined,
          search: appliedSearch || undefined,
        }),
        getErrorEventMetrics(),
      ]);

      setItems(listResponse.items);
      setTotal(listResponse.total);
      setMetrics(metricsResponse);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load error management data.",
      );
    } finally {
      setLoading(false);
    }
  }, [offset, status, severity, category, appliedSearch]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const openDetails = async (errorId: string) => {
    setDetailsLoading(true);
    setSelected(null);

    try {
      const result = await getErrorEvent(errorId);
      setSelected(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load error details.",
      );
    } finally {
      setDetailsLoading(false);
    }
  };

  const changeStatus = async (newStatus: ErrorEventStatus) => {
    if (!selected || updating) return;

    setUpdating(true);
    setError(null);

    try {
      const updated = await updateErrorEventStatus(selected.id, newStatus);
      setSelected(updated);
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to update error status.",
      );
    } finally {
      setUpdating(false);
    }
  };

  const applyFilters = () => {
    setOffset(0);
    setAppliedSearch(search.trim());
  };

  const clearFilters = () => {
    setStatus("");
    setSeverity("");
    setCategory("");
    setSearch("");
    setAppliedSearch("");
    setOffset(0);
  };

  if (user?.role !== "admin") {
    return null;
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <section className="content-card error-management">
      <div className="error-heading">
        <div>
          <h2>Error Management</h2>
          <p>
            Review application errors, investigate incidents, and track
            resolution status.
          </p>
        </div>

        <button
          className="monitor-refresh"
          onClick={() => void loadData()}
          disabled={loading}
        >
          {loading ? "Refreshing..." : "Refresh errors"}
        </button>
      </div>

      {error && <div className="error-alert">{error}</div>}

      {metrics && (
        <div className="error-metrics-grid">
          <Metric label="Total Errors" value={metrics.total} />
          <Metric label="Open" value={metrics.by_status.open ?? 0} />
          <Metric
            label="Investigating"
            value={metrics.by_status.investigating ?? 0}
          />
          <Metric label="Resolved" value={metrics.by_status.resolved ?? 0} />
          <Metric label="Last 24 Hours" value={metrics.last_24_hours} />
        </div>
      )}

      <div className="error-filters">
        <input
          type="text"
          value={search}
          placeholder="Search message, endpoint, request ID..."
          onChange={(event) => setSearch(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") applyFilters();
          }}
        />

        <select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="investigating">Investigating</option>
          <option value="resolved">Resolved</option>
        </select>

        <select
          value={severity}
          onChange={(event) => {
            setSeverity(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">All severities</option>
          <option value="error">Error</option>
          <option value="warning">Warning</option>
          <option value="critical">Critical</option>
        </select>

        <select
          value={category}
          onChange={(event) => {
            setCategory(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">All categories</option>
          <option value="application">Application</option>
          <option value="worker">Worker</option>
          <option value="integration">Integration</option>
        </select>

        <button className="error-filter-button" onClick={applyFilters}>
          Search
        </button>

        <button className="error-clear-button" onClick={clearFilters}>
          Clear
        </button>
      </div>

      <div className="error-table-wrapper">
        <table className="error-table">
          <thead>
            <tr>
              <th>Error</th>
              <th>Category</th>
              <th>Severity</th>
              <th>Status</th>
              <th>Endpoint</th>
              <th>Occurred</th>
              <th>Details</th>
            </tr>
          </thead>

          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="error-empty">
                  Loading errors...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={7} className="error-empty">
                  No errors found.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{item.error_type}</strong>
                    <span className="error-message-preview">
                      {item.message}
                    </span>
                  </td>
                  <td>{item.category}</td>
                  <td>
                    <span className={`error-tag ${item.severity}`}>
                      {item.severity}
                    </span>
                  </td>
                  <td>
                    <span className={`error-tag status-${item.status}`}>
                      {item.status}
                    </span>
                  </td>
                  <td>
                    {item.method && <strong>{item.method} </strong>}
                    {item.endpoint ?? "—"}
                  </td>
                  <td>{formatDate(item.occurred_at)}</td>
                  <td>
                    <button
                      className="error-details-button"
                      onClick={() => void openDetails(item.id)}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="error-pagination">
        <span>
          {total === 0
            ? "No results"
            : `Showing ${offset + 1}–${Math.min(offset + items.length, total)} of ${total}`}
        </span>

        <div>
          <button
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            disabled={offset === 0 || loading}
          >
            Previous
          </button>

          <span>
            Page {currentPage} of {totalPages}
          </span>

          <button
            onClick={() => setOffset(offset + PAGE_SIZE)}
            disabled={offset + PAGE_SIZE >= total || loading}
          >
            Next
          </button>
        </div>
      </div>

      {detailsLoading && (
        <div className="error-details-panel">
          Loading error details...
        </div>
      )}

      {selected && (
        <div className="error-details-panel">
          <div className="error-details-heading">
            <div>
              <h3>Error Details</h3>
              <p>{selected.error_type}</p>
            </div>

            <button
              className="error-close-button"
              onClick={() => setSelected(null)}
            >
              Close
            </button>
          </div>

          <div className="error-detail-grid">
            <div>
              <span>Event ID</span>
              <strong>{selected.id}</strong>
            </div>
            <div>
              <span>Request ID</span>
              <strong>{selected.request_id ?? "—"}</strong>
            </div>
            <div>
              <span>Message ID</span>
              <strong>{selected.message_id ?? "—"}</strong>
            </div>
            <div>
              <span>Document ID</span>
              <strong>{selected.document_id ?? "—"}</strong>
            </div>
            <div>
              <span>Severity</span>
              <strong>{selected.severity}</strong>
            </div>
            <div>
              <span>Category</span>
              <strong>{selected.category}</strong>
            </div>
            <div>
              <span>Occurred At</span>
              <strong>{formatDate(selected.occurred_at)}</strong>
            </div>
            <div>
              <span>Resolved At</span>
              <strong>
                {selected.resolved_at
                  ? formatDate(selected.resolved_at)
                  : "Not resolved"}
              </strong>
            </div>
          </div>

          <div className="error-detail-message">
            <h4>Message</h4>
            <p>{selected.message}</p>
          </div>

          {selected.traceback && (
            <div className="error-traceback">
              <h4>Traceback</h4>
              <pre>{selected.traceback}</pre>
            </div>
          )}

          <div className="error-actions">
            {selected.status !== "investigating" &&
              selected.status !== "resolved" && (
                <button
                  onClick={() => void changeStatus("investigating")}
                  disabled={updating}
                >
                  {updating ? "Updating..." : "Mark Investigating"}
                </button>
              )}

            {selected.status !== "resolved" && (
              <button
                className="resolve-button"
                onClick={() => void changeStatus("resolved")}
                disabled={updating}
              >
                {updating ? "Updating..." : "Resolve"}
              </button>
            )}

            {selected.status === "resolved" && (
              <button
                onClick={() => void changeStatus("open")}
                disabled={updating}
              >
                {updating ? "Updating..." : "Reopen"}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
