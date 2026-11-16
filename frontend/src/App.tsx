import { useEffect, useRef, useState } from "react";
import {
  getDocument,
  getDocuments,
  getDocumentExtraction,
  getIntegrationHistory,
  integrateDocument,
  processDocument,
  reviewDocument,
  uploadDocument,
  correctDocumentExtraction,
  getExtractionHistory,
} from "./services/api";
import type { DocumentResponse, ExtractionResultResponse, IntegrationLogResponse, ExtractionCorrection,
ExtractionEditResponse} from "./types/document";
import "./App.css";
import AuthScreen from "./components/AuthScreen";
import { useAuth } from "./context/AuthContext";


type InvoiceFormValues = {
  supplier_name: string;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  currency: string;
  subtotal: string;
  vat_amount: string;
  total_amount: string;
};
type DashboardView =
  | "overview"
  | "documents"
  | "review"
  | "integrations"
  | "settings";
function Dashboard() {
  const { user, logout } = useAuth();

  const [activeView, setActiveView] = useState<DashboardView>("overview");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [selectedDocument, setSelectedDocument] =
    useState<DocumentResponse | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "all" | DocumentResponse["status"]
  >("all");

  const [extraction, setExtraction] =
  useState<ExtractionResultResponse | null>(null);
  const [integrationHistory, setIntegrationHistory] =
  useState<IntegrationLogResponse[]>([]);
  const [allIntegrationHistory, setAllIntegrationHistory] =
  useState<IntegrationLogResponse[]>([]);
  const [integrationHistoryLoading, setIntegrationHistoryLoading] =
  useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [reviewComments, setReviewComments] = useState("");

  const [invoiceForm, setInvoiceForm] = useState<InvoiceFormValues>({
    supplier_name: "",
    invoice_number: "",
    invoice_date: "",
    due_date: "",
    currency: "",
    subtotal: "",
    vat_amount: "",
    total_amount: "",
  });

  const [extractionHistory, setExtractionHistory] =
    useState<ExtractionEditResponse[]>([]);

  const populateInvoiceForm = (data: ExtractionResultResponse) => {
    setInvoiceForm({
      supplier_name: data.supplier_name ?? "",
      invoice_number: data.invoice_number ?? "",
      invoice_date: data.invoice_date ?? "",
      due_date: data.due_date ?? "",
      currency: data.currency ?? "",
      subtotal: data.subtotal?.toString() ?? "",
      vat_amount: data.vat_amount?.toString() ?? "",
      total_amount: data.total_amount?.toString() ?? "",
    });
  };


  const handleSaveCorrections = async () => {
    if (!selectedDocument || !extraction) {
      setError("Cannot save: no document or extraction is selected.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      const corrections: ExtractionCorrection = {};

      const stringFields = [
        "supplier_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "currency",
      ] as const;

      stringFields.forEach((field) => {
        const value = invoiceForm[field].trim();
        const normalizedValue =
          field === "currency" ? value.toUpperCase() : value;
        const currentValue = extraction[field] ?? "";

        if (normalizedValue !== currentValue) {
          corrections[field] = normalizedValue || null;
        }
      });
      const numberFields = [
        "subtotal",
        "vat_amount",
        "total_amount",
      ] as const;

      numberFields.forEach((field) => {
        const value = invoiceForm[field].trim();
        const normalizedValue = value === "" ? null : Number(value);

        const currentValue =
          extraction[field] == null ? null : Number(extraction[field]);

        if (normalizedValue !== currentValue) {
          corrections[field] = normalizedValue;
        }
      });

      if (Object.keys(corrections).length === 0) {
        setSuccess("No changes detected.");
        return;
      }

      const updatedExtraction = await correctDocumentExtraction(
        selectedDocument.id,
        corrections,
      );


      setExtraction(updatedExtraction);
      populateInvoiceForm(updatedExtraction);

      const history = await getExtractionHistory(selectedDocument.id);
      setExtractionHistory(history);

      setSuccess("Corrections saved and invoice revalidated.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not save invoice corrections.",
      );
    } finally {
      setLoading(false);
    }
  };


    const loadExtractionHistory = async (documentId: string) => {
      try {
        const history = await getExtractionHistory(documentId);
        setExtractionHistory(history);
      } catch (err) {
        setExtractionHistory([]);
        console.error("Could not load extraction history:", err);
      }
    };

    const loadAllIntegrationHistory = async () => {
      if (documents.length === 0) {
        setAllIntegrationHistory([]);
        return;
      }

      setIntegrationHistoryLoading(true);

      try {
        const results = await Promise.allSettled(
          documents.map((document) => getIntegrationHistory(document.id)),
        );

        const combinedHistory = results
          .filter(
            (result): result is PromiseFulfilledResult<IntegrationLogResponse[]> =>
              result.status === "fulfilled",
          )
          .flatMap((result) => result.value)
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          );

        setAllIntegrationHistory(combinedHistory);

        if (results.some((result) => result.status === "rejected")) {
          console.warn("Some integration histories could not be loaded.");
        }
      } catch (err) {
        console.error("Could not load ERP integration history:", err);
        setAllIntegrationHistory([]);
      } finally {
        setIntegrationHistoryLoading(false);
      }
    };

  useEffect(() => {
    const loadDocuments = async () => {
      setLoading(true);
      setError("");

      try {
        const existingDocuments = await getDocuments();

        setDocuments(existingDocuments);

        if (existingDocuments.length > 0) {
          const latestDocument = existingDocuments[0];
          setSelectedDocument(latestDocument);

          if (latestDocument.status === "pending_review") {
            const extractedData = await getDocumentExtraction(
              latestDocument.id,
            );

            setExtraction(extractedData);
            populateInvoiceForm(extractedData);

            const history = await getExtractionHistory(latestDocument.id);
            setExtractionHistory(history);
          }
          if (latestDocument.status === "approved") {
            const history = await getIntegrationHistory(latestDocument.id);
            setIntegrationHistory(history);
          }
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Could not load existing documents.",
        );
      } finally {
        setLoading(false);
      }
    };

    loadDocuments();
  }, []);

  useEffect(() => {
    if (activeView === "integrations") {
      loadAllIntegrationHistory();
    }
  }, [activeView, documents]);

  const handleUpload = async (file?: File) => {
    if (!file) return;

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      const document = await uploadDocument(file);

      setDocuments((previous) => [document, ...previous]);
      setSelectedDocument(document);
      setSuccess("Document uploaded successfully.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Document upload failed.",
      );
    } finally {
      setLoading(false);

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleProcess = async (documentId: string) => {
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      const result = await processDocument(documentId);

      // In background mode, the endpoint returns DocumentResponse.
      // In inline mode, it returns ExtractionResultResponse.
      if ("original_filename" in result) {
        setDocuments((previous) =>
          previous.map((document) =>
            document.id === documentId ? result : document,
          ),
        );

        setSelectedDocument(result);
        setSuccess("Document queued for processing.");
      } else {
        const document = await getDocument(documentId);

        setDocuments((previous) =>
          previous.map((item) =>
            item.id === documentId ? document : item,
          ),
        );

        setSelectedDocument(document);
        setSuccess("Document processed successfully.");
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Document processing failed.",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    if (!selectedDocument) return;

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      const updated = await getDocument(selectedDocument.id);

      setDocuments((previous) =>
        previous.map((document) =>
          document.id === updated.id ? updated : document,
        ),
      );

      setSelectedDocument(updated);

      if (updated.status === "pending_review") {
        const extractedData = await getDocumentExtraction(updated.id);
        setExtraction(extractedData);
        populateInvoiceForm(extractedData);
        await loadExtractionHistory(updated.id);
      } else {
        setExtraction(null);
      }

      setSuccess("Document status and extraction data refreshed.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not refresh document.",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleSelectDocument = async (
    document: DocumentResponse,
  ) => {
    setSelectedDocument(document);
    setExtraction(null);
    setIntegrationHistory([]);
    setExtractionHistory([]);
    setInvoiceForm({
      supplier_name: "",
      invoice_number: "",
      invoice_date: "",
      due_date: "",
      currency: "",
      subtotal: "",
      vat_amount: "",
      total_amount: "",
    });
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      if (
        [
          "pending_review",
          "approved",
          "rejected",
          "integration_pending",
          "integrated",
        ].includes(document.status)
      ) {
        const extractedData = await getDocumentExtraction(document.id);
        setExtraction(extractedData);
        populateInvoiceForm(extractedData);
        await loadExtractionHistory(document.id);
      }

      if (
        ["approved", "integration_pending", "integrated"].includes(
          document.status,
        )
      ) {
        const history = await getIntegrationHistory(document.id);
        setIntegrationHistory(history);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not load document details.",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleReview = async (
    decision: "approved" | "rejected",
  ) => {
    if (!selectedDocument) return;



    setLoading(true);
    setError("");
    setSuccess("");

    try {
      await reviewDocument(selectedDocument.id, {
        decision,
        comments: reviewComments.trim() || null,
      });

      const updated = await getDocument(selectedDocument.id);

      setDocuments((previous) =>
        previous.map((document) =>
          document.id === updated.id ? updated : document,
        ),
      );

      setSelectedDocument(updated);

      setSuccess(
        `Document ${decision} successfully.`,
      );

      setReviewComments("");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Document review failed.",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleIntegration = async () => {
    if (!selectedDocument) return;

    if (selectedDocument.status !== "approved") {
      setError("Only approved documents can be integrated.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");

    try {
      await integrateDocument(selectedDocument.id);

      const updated = await getDocument(selectedDocument.id);
      const history = await getIntegrationHistory(selectedDocument.id);
      setIntegrationHistory(history);

      setDocuments((previous) =>
        previous.map((document) =>
          document.id === updated.id ? updated : document,
        ),
      );

      setSelectedDocument(updated);

      setSuccess("Document integrated successfully.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "ERP integration failed.",
      );
    } finally {
      setLoading(false);
    }
  };

  const stats = [
    { label: "Total Documents", value: documents.length, icon: "▤" },
    {
      label: "Processing",
      value: documents.filter((doc) => doc.status === "processing").length,
      icon: "◷",
    },
    {
      label: "Pending Review",
      value: documents.filter((doc) => doc.status === "pending_review").length,
      icon: "◎",
    },
    {
      label: "Completed",
      value: documents.filter(
        (doc) => doc.status === "approved" || doc.status === "integrated",
      ).length,
      icon: "✓",
    },
  ];

  const filteredDocuments = documents.filter((document) => {
    const matchesSearch = document.original_filename
      .toLowerCase()
      .includes(searchQuery.trim().toLowerCase());

    const matchesStatus =
      statusFilter === "all" || document.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const pendingReviewDocuments = documents.filter(
    (document) => document.status === "pending_review",
  );

  const visibleDocuments =
    activeView === "review"
      ? pendingReviewDocuments
      : activeView === "overview"
        ? filteredDocuments.slice(0, 5)
        : filteredDocuments;

  const getDocumentFilename = (documentId: string) =>
    documents.find((document) => document.id === documentId)
      ?.original_filename ?? "Unknown document";

  const pageTitles: Record<DashboardView, { title: string; subtitle: string }> = {
    overview: {
      title: "Dashboard Overview",
      subtitle: "Manage, process, and review your business documents.",
    },
    documents: {
      title: "Documents",
      subtitle: "Upload, search, and manage your business documents.",
    },
    review: {
      title: "Review & Approval",
      subtitle: "Review extracted information and approve or reject documents.",
    },
    integrations: {
      title: "ERP Integrations",
      subtitle: "Monitor document integration activity and ERP records.",
    },
    settings: {
      title: "Settings",
      subtitle: "View your account and application information.",
    },
  };

  return (
    <div className="dashboard">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">D</div>
          <div>
            <div className="brand-name">DocuFlow AI</div>
            <div className="brand-subtitle">Document Intelligence</div>
          </div>
        </div>

        <nav>
          <div className="nav-label">WORKSPACE</div>

          <button
            type="button"
            className={`nav-item ${activeView === "overview" ? "active" : ""}`}
            onClick={() => setActiveView("overview")}
          >
            <span className="nav-icon">▦</span>
            Overview
          </button>

          <button
            type="button"
            className={`nav-item ${activeView === "documents" ? "active" : ""}`}
            onClick={() => setActiveView("documents")}
          >
            <span className="nav-icon">▤</span>
            Documents
          </button>

          <button
            type="button"
            className={`nav-item ${activeView === "review" ? "active" : ""}`}
            onClick={() => setActiveView("review")}
          >
            <span className="nav-icon">◎</span>
            Review & Approval
          </button>

          <div className="nav-label">MANAGEMENT</div>

          <button
            type="button"
            className={`nav-item ${activeView === "integrations" ? "active" : ""}`}
            onClick={() => setActiveView("integrations")}
          >
            <span className="nav-icon">⇄</span>
            ERP Integrations
          </button>

          <button
            type="button"
            className={`nav-item ${activeView === "settings" ? "active" : ""}`}
            onClick={() => setActiveView("settings")}
          >
            <span className="nav-icon">⚙</span>
            Settings
          </button>
        </nav>

        <div className="sidebar-footer">
          <strong>AI Document Processing</strong>
          <p>Local development environment</p>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <h1 className="page-title">{pageTitles[activeView].title}</h1>
            <p className="page-subtitle">{pageTitles[activeView].subtitle}</p>
          </div>

          <div className="user-profile">
            <div className="avatar">
              {user?.email?.charAt(0).toUpperCase() ?? "U"}
            </div>

            <div>
              <div className="user-name">{user?.email}</div>
              <div className="user-role">
                {user?.role === "admin" ? "Workspace Admin" : "Workspace User"}
              </div>
            </div>

            <button className="btn btn-secondary" onClick={logout}>
              Sign Out
            </button>
          </div>
        </header>

        {activeView === "overview" && (
          <section className="stats-grid">
            {stats.map((stat) => (
              <div className="stat-card" key={stat.label}>
                <div className="stat-label">{stat.label}</div>
                <div className="stat-value">{stat.value}</div>
                <div className="stat-description">{stat.icon} Live session data</div>
              </div>
            ))}
          </section>
        )}

        {(activeView === "overview" || activeView === "documents") && (
          <section className="content-card">
            <div className="section-heading">
              <div>
                <h2 className="section-title">Upload Documents</h2>
                <p className="section-description">
                  Upload invoices, purchase orders, contracts, and other files.
                </p>
              </div>
            </div>

            <div
              className="upload-area"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                handleUpload(event.dataTransfer.files[0]);
              }}
            >
              <div className="upload-icon">☁</div>
              <div className="upload-title">
                Drag and drop your document here
              </div>
              <p className="upload-description">
                Select a document from your computer to upload.
              </p>

              <input
                ref={fileInputRef}
                type="file"
                hidden
                accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.txt,.docx"
                onChange={(event) =>
                  handleUpload(event.target.files?.[0])
                }
              />

              <button
                className="btn btn-primary"
                type="button"
                disabled={loading}
                onClick={() => fileInputRef.current?.click()}
              >
                {loading ? "Please wait..." : "Browse Files"}
              </button>
            </div>

            {error && <p className="error-message">{error}</p>}
            {success && <p className="success-message">{success}</p>}
          </section>
        )}

        {(activeView === "documents" || activeView === "review" || activeView === "overview") && (
          <section className="content-card" style={{ marginTop: 24 }}>
            <div className="section-heading">
              <div>
                <h2 className="section-title">
                  {activeView === "review"
                    ? "Documents Awaiting Review"
                    : activeView === "overview"
                      ? "Recent Documents"
                      : "All Documents"}
                </h2>
                <p className="section-description">
                  {activeView === "review"
                    ? "Select a document to inspect its extracted data and approve or reject it."
                    : "Search, filter, and manage your uploaded documents."}
                </p>
              </div>
            </div>
            {activeView !== "review" && (
              <div className="document-filters">
                <input
                  type="search"
                  className="document-search"
                  placeholder="Search by filename..."
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                />

                <select
                  className="document-status-filter"
                  value={statusFilter}
                  onChange={(event) =>
                    setStatusFilter(
                      event.target.value as "all" | DocumentResponse["status"],
                    )
                  }
                >
                  <option value="all">All statuses</option>
                  <option value="uploaded">Uploaded</option>
                  <option value="processing">Processing</option>
                  <option value="extracted">Extracted</option>
                  <option value="pending_review">Pending Review</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                  <option value="integration_pending">Integration Pending</option>
                  <option value="integrated">Integrated</option>
                  <option value="failed">Failed</option>
                </select>
              </div>
            )}
            {documents.length === 0 ? (
              <p className="empty-state">
                No documents uploaded yet.
              </p>
            ) : visibleDocuments.length === 0 ? (
              <p className="empty-state">
                No documents match your search or selected status.
              </p>
            ) : (
              <div className="document-list">
                {visibleDocuments.map((document) => (
                  <div className="document-row" key={document.id}>
                    <div className="document-info">
                      <strong>{document.original_filename}</strong>
                      <span>
                        {new Date(document.created_at).toLocaleString()}
                      </span>
                    </div>

                    <span className={`status status-${document.status}`}>
                      {document.status.replaceAll("_", " ")}
                    </span>

                    <button
                      className="btn btn-secondary"
                      type="button"
                      disabled={loading}
                      onClick={() => handleSelectDocument(document)}
                      >
                      Details
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
        {selectedDocument && (activeView === "documents" || (activeView === "review" && selectedDocument.status === "pending_review")) && (
          <section className="content-card" style={{ marginTop: 24 }}>
            <div className="section-heading">
              <div>
                <h2 className="section-title">Document Details</h2>
                <p className="section-description">
                  {selectedDocument.original_filename}
                </p>
              </div>

              <span className={`status status-${selectedDocument.status}`}>
                {selectedDocument.status.replaceAll("_", " ")}
              </span>
            </div>

            <p className="detail-text">
              Document ID: {selectedDocument.id}
            </p>
            <p className="detail-text">
              Type: {selectedDocument.document_type}
            </p>
            <p className="detail-text">
              Size: {(selectedDocument.file_size / 1024).toFixed(1)} KB
            </p>
            {extraction && (
              <div className="extraction-section">
                <h3>AI Extraction Results</h3>

                <div className="extraction-grid">
                  <div className="extraction-field">
                    <span>Supplier</span>
                    <strong>{extraction.supplier_name || "Not detected"}</strong>
                  </div>

                  <div className="extraction-field">
                    <span>Invoice Number</span>
                    <strong>{extraction.invoice_number || "Not detected"}</strong>
                  </div>

                  <div className="extraction-field">
                    <span>Invoice Date</span>
                    <strong>{extraction.invoice_date || "Not detected"}</strong>
                  </div>

                  <div className="extraction-field">
                    <span>Due Date</span>
                    <strong>{extraction.due_date || "Not detected"}</strong>
                  </div>

                  <div className="extraction-field">
                    <span>Currency</span>
                    <strong>{extraction.currency || "Not detected"}</strong>
                  </div>

                  <div className="extraction-field">
                    <span>Subtotal</span>
                    <strong>{extraction.subtotal ?? "Not detected"}</strong>
                  </div>

                  <div className="extraction-field">
                    <span>VAT Amount</span>
                    <strong>{extraction.vat_amount ?? "Not detected"}</strong>
                  </div>

                  <div className="extraction-field">
                    <span>Total Amount</span>
                    <strong>{extraction.total_amount ?? "Not detected"}</strong>
                  </div>
                </div>

                <div className="extraction-metadata">
                  <span>
                    Provider: {extraction.extraction_provider || "Unknown"}
                  </span>
                  <span>
                    Model: {extraction.extraction_model || "Unknown"}
                  </span>
                  <span>
                    Confidence: {extraction.confidence_score == null
                      ? "Not available"
                      : `${(extraction.confidence_score * 100).toFixed(1)}%`}
                  </span>
                </div>
                {extraction.extracted_data.validation && (
                  <div
                    className={`validation-status validation-${extraction.extracted_data.validation.status}`}
                  >
                    <strong>
                      Validation Status:{" "}
                      {(extraction.extracted_data.validation.status ?? "unknown")
                        .replace("_", " ")
                        .toUpperCase()}
                    </strong>

                    <span>
                      {extraction.extracted_data.validation.is_valid
                        ? "All validation checks passed."
                        : "This invoice requires attention before approval."}
                    </span>

                    {(extraction.extracted_data.validation.errors ?? []).length > 0 && (
                      <ul>
                        {(extraction.extracted_data.validation.errors ?? []).map(
                          (error, index) => (
                            <li key={index}>{String(error)}</li>
                          ),
                        )}
                      </ul>
                    )}
                  </div>
                )}

                {extraction.extracted_data.validation?.status === "duplicate" && (
                  <div className="duplicate-warning">
                    <strong>⚠ Duplicate Invoice Detected</strong>

                    <p>
                      An earlier invoice with the same supplier and invoice number
                      was found in your documents.
                    </p>

                    {extraction.extracted_data.validation.duplicate_of && (
                      <div className="duplicate-details">
                        <h4>Previously Uploaded Invoice</h4>

                        <div className="duplicate-detail-row">
                          <span>Filename</span>
                          <strong>
                            {extraction.extracted_data.validation.duplicate_of.filename}
                          </strong>
                        </div>

                        <div className="duplicate-detail-row">
                          <span>Supplier</span>
                          <strong>
                            {extraction.extracted_data.validation.duplicate_of.supplier_name || "Unknown"}
                          </strong>
                        </div>

                        <div className="duplicate-detail-row">
                          <span>Invoice Number</span>
                          <strong>
                            {extraction.extracted_data.validation.duplicate_of.invoice_number || "Unknown"}
                          </strong>
                        </div>

                        <div className="duplicate-detail-row">
                          <span>Invoice Date</span>
                          <strong>
                            {extraction.extracted_data.validation.duplicate_of.invoice_date || "Unknown"}
                          </strong>
                        </div>

                        <div className="duplicate-detail-row">
                          <span>Total Amount</span>
                          <strong>
                            {extraction.extracted_data.validation.duplicate_of.total_amount != null
                              ? `${extraction.extracted_data.validation.duplicate_of.total_amount} ${extraction.extracted_data.validation.duplicate_of.currency || ""}`
                              : "Unknown"}
                          </strong>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {extraction.extracted_data.validation?.status !== "duplicate" &&
                  Array.isArray(extraction.extracted_data.validation?.warnings) &&
                  extraction.extracted_data.validation.warnings.length > 0 && (
                    <div className="validation-warning">
                      <strong>Validation Warnings</strong>
                      <ul>
                        {extraction.extracted_data.validation.warnings.map(
                          (warning, index) => (
                            <li key={index}>{String(warning)}</li>
                          ),
                        )}
                      </ul>
                    </div>
                  )}

              </div>
            )}


            {selectedDocument.status === "pending_review" && extraction && (
              <div className="review-section">
                <h3>Edit Extracted Invoice Data</h3>
                <p className="section-description">
                  Correct the extracted fields before approving this invoice.
                </p>

                <div className="review-form">
                  {(
                    [
                      ["supplier_name", "Supplier", "text"],
                      ["invoice_number", "Invoice Number", "text"],
                      ["invoice_date", "Invoice Date", "date"],
                      ["due_date", "Due Date", "date"],
                      ["currency", "Currency", "text"],
                      ["subtotal", "Subtotal", "number"],
                      ["vat_amount", "VAT Amount", "number"],
                      ["total_amount", "Total Amount", "number"],
                    ] as const
                  ).map(([field, label, type]) => (
                    <div className="review-field" key={field}>
                      <label htmlFor={`invoice-${field}`}>{label}</label>
                      <input
                        id={`invoice-${field}`}
                        type={type}
                        step={type === "number" ? "0.01" : undefined}
                        value={invoiceForm[field]}
                        onChange={(event) =>
                          setInvoiceForm((previous) => ({
                            ...previous,
                            [field]: event.target.value,
                          }))
                        }
                        disabled={loading}
                      />
                    </div>
                  ))}
                </div>

                <div className="review-actions">
                  <button
                    className="btn btn-primary"
                    type="button"
                    disabled={loading}
                    onClick={handleSaveCorrections}
                  >
                    {loading ? "Saving..." : "Save Corrections & Revalidate"}
                  </button>
                </div>
              </div>
            )}


            {selectedDocument.status === "pending_review" && (
              <div className="review-section">
                <h3>Correction Audit History</h3>

                {extractionHistory.length === 0 ? (
                  <p className="detail-text">
                    No manual corrections have been recorded.
                  </p>
                ) : (
                  <div className="integration-history">
                    {extractionHistory.map((edit) => (
                      <div className="integration-item" key={edit.id}>
                        <strong>Edited by: {edit.edited_by}</strong>

                        <p className="detail-text">
                          Date: {new Date(edit.created_at).toLocaleString()}
                        </p>

                        <p className="detail-text">
                          Changed fields: {edit.changed_fields.join(", ")}
                        </p>

                        <details>
                          <summary>View before and after values</summary>

                          {edit.changed_fields.map((field) => (
                            <div className="duplicate-detail-row" key={field}>
                              <strong>{field.replaceAll("_", " ")}</strong>
                              <span>
                                {String(edit.before_data[field] ?? "Empty")}
                                {" → "}
                                {String(edit.after_data[field] ?? "Empty")}
                              </span>
                            </div>
                          ))}
                        </details>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}


            {selectedDocument.status === "pending_review" && extraction && (
              <div className="review-section">
                <h3>Review & Approval</h3>

                <div className="review-form">

                  <div className="review-field">
                    <label htmlFor="review-comments">Comments</label>
                    <textarea
                      id="review-comments"
                      value={reviewComments}
                      onChange={(event) => setReviewComments(event.target.value)}
                      placeholder="Add review notes (optional)"
                      rows={3}
                      disabled={loading}
                    />
                  </div>

                  <div className="review-actions">
                    <button
                      className="btn btn-primary"
                      disabled={
                        loading ||
                        extraction.extracted_data.validation?.is_valid !== true
                      }
                      onClick={() => handleReview("approved")}
                      title={
                        extraction.extracted_data.validation?.is_valid !== true
                          ? "Approval is unavailable because validation failed."
                          : "Approve this document"
                      }
                    >
                      Approve Document
                    </button>

                    <button
                      className="btn btn-danger"
                      disabled={loading}
                      onClick={() => handleReview("rejected")}
                    >
                      Reject Document
                    </button>
                  </div>

                  {extraction.extracted_data.validation?.is_valid !== true && (
                    <p className="review-validation-note">
                      Approval is disabled because this invoice has validation errors
                      or possible duplicate warnings. You can still reject it.
                    </p>
                  )}
                </div>
              </div>
            )}

            {["approved", "integration_pending", "integrated"].includes(
              selectedDocument.status,
            ) && (
              <div className="review-section">
                <h3>ERP Integration History</h3>

                {integrationHistory.length === 0 ? (
                  <p className="detail-text">
                    No integration attempts recorded yet.
                  </p>
                ) : (
                  <div className="integration-history">
                    {integrationHistory.map((item) => (
                      <div className="integration-item" key={item.id}>
                        <div className="integration-item-header">
                          <strong>{item.provider}</strong>
                          <span className={`status status-${item.status}`}>
                            {item.status.replaceAll("_", " ")}
                          </span>
                        </div>

                        <p className="detail-text">
                          Operation: {item.operation}
                        </p>

                        <p className="detail-text">
                          Attempt: {item.attempt_number}
                        </p>

                        <p className="detail-text">
                          External Record ID: {item.external_record_id || "Not available"}
                        </p>

                        {item.error_message && (
                          <p className="integration-error">
                            {item.error_message}
                          </p>
                        )}

                        <p className="detail-text">
                          Started: {new Date(item.started_at).toLocaleString()}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="action-buttons">
              {(selectedDocument.status === "uploaded" ||
                selectedDocument.status === "failed") && (
                <button
                  className="btn btn-primary"
                  disabled={loading}
                  onClick={() => handleProcess(selectedDocument.id)}
                >
                  Process Document
                </button>
              )}
              {selectedDocument.status === "approved" && (
                <button
                  className="btn btn-primary"
                  disabled={loading}
                  onClick={handleIntegration}
                >
                  Integrate with ERP
                </button>
              )}
              <button
                className="btn btn-secondary"
                disabled={loading}
                onClick={handleRefresh}
              >
                Refresh Status
              </button>
            </div>
          </section>
        )}
        {activeView === "integrations" && (
          <section className="content-card">
            <div className="section-heading">
              <div>
                <h2 className="section-title">Integration Activity</h2>
                <p className="section-description">
                  Track ERP integration attempts across all documents.
                </p>
              </div>

              <button
                type="button"
                className="btn btn-secondary"
                disabled={integrationHistoryLoading}
                onClick={loadAllIntegrationHistory}
              >
                {integrationHistoryLoading ? "Refreshing..." : "Refresh"}
              </button>
            </div>

            {integrationHistoryLoading ? (
              <p className="empty-state">Loading integration history...</p>
            ) : allIntegrationHistory.length === 0 ? (
              <p className="empty-state">
                No ERP integration activity recorded yet.
              </p>
            ) : (
              <div className="integration-history">
                {allIntegrationHistory.map((item) => (
                  <div className="integration-item" key={item.id}>
                    <div className="integration-item-header">
                      <strong>{getDocumentFilename(item.document_id)}</strong>
                      <span className={`status status-${item.status}`}>
                        {item.status.replaceAll("_", " ")}
                      </span>
                    </div>

                    <p className="detail-text">Provider: {item.provider}</p>
                    <p className="detail-text">Operation: {item.operation}</p>
                    <p className="detail-text">
                      Attempt: {item.attempt_number}
                    </p>
                    <p className="detail-text">
                      External Record ID: {item.external_record_id || "Not available"}
                    </p>

                    {item.error_message && (
                      <p className="integration-error">{item.error_message}</p>
                    )}

                    <p className="detail-text">
                      Started: {new Date(item.started_at).toLocaleString()}
                    </p>
                    <p className="detail-text">
                      Completed:{" "}
                      {item.completed_at
                        ? new Date(item.completed_at).toLocaleString()
                        : "Not completed"}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
        {activeView === "settings" && (
          <section className="content-card">
            <div className="section-heading">
              <div>
                <h2 className="section-title">Account Information</h2>
                <p className="section-description">
                  View your account and application details.
                </p>
              </div>
            </div>

            <div className="details-grid">
              <div className="detail-item">
                <span className="detail-label">Email Address</span>
                <strong className="detail-value">
                  {user?.email ?? "Not available"}
                </strong>
              </div>

              <div className="detail-item">
                <span className="detail-label">Workspace Role</span>
                <strong className="detail-value">
                  {user?.role === "admin" ? "Workspace Admin" : "Workspace User"}
                </strong>
              </div>
            </div>

            <div className="section-heading settings-section-heading">
              <div>
                <h2 className="section-title">Application Information</h2>
                <p className="section-description">
                  Details about this document processing platform.
                </p>
              </div>
            </div>

            <div className="details-grid">
              <div className="detail-item">
                <span className="detail-label">Application</span>
                <strong className="detail-value">AI Document Processing</strong>
              </div>

              <div className="detail-item">
                <span className="detail-label">Environment</span>
                <strong className="detail-value">Local Development</strong>
              </div>

              <div className="detail-item">
                <span className="detail-label">Frontend</span>
                <strong className="detail-value">React + TypeScript</strong>
              </div>

              <div className="detail-item">
                <span className="detail-label">Backend</span>
                <strong className="detail-value">FastAPI + Python</strong>
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="auth-page">
        <p>Restoring your session...</p>
      </div>
    );
  }

  if (!user) {
    return <AuthScreen />;
  }

  return <Dashboard />;
}

export default App;
