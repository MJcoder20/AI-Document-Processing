
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./apiClient";
import {
  getDocuments,
  uploadDocument,
  getDocument,
  processDocument,
  getDocumentExtraction,
  reviewDocument,
  integrateDocument,
  getIntegrationHistory,
} from "./api";

vi.mock("./apiClient", () => ({
  apiRequest: vi.fn(),
}));

const mockDocument = {
  id: "doc-123",
  original_filename: "invoice.pdf",
  content_type: "application/pdf",
  file_size: 1024,
  document_type: "invoice" as const,
  status: "pending_review" as const,
  error_message: null,
  created_at: "2026-11-15T10:00:00Z",
  updated_at: "2026-11-15T10:00:00Z",
};

const mockDocumentList = {
  items: [mockDocument],
  total: 1,
  limit: 20,
  offset: 0,
};

describe("Document API services", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("retrieves documents with pagination parameters", async () => {
    vi.mocked(apiRequest).mockResolvedValue({
      ...mockDocumentList,
      limit: 10,
      offset: 5,
    });

    const result = await getDocuments(10, 5);

    expect(apiRequest).toHaveBeenCalledWith(
      "/documents/?limit=10&offset=5",
    );
    expect(result).toEqual({
      ...mockDocumentList,
      limit: 10,
      offset: 5,
    });
  });

  it("uses default pagination parameters", async () => {
    vi.mocked(apiRequest).mockResolvedValue(mockDocumentList);

    await getDocuments();

    expect(apiRequest).toHaveBeenCalledWith(
      "/documents/?limit=20&offset=0",
    );
  });

  it("retrieves documents using search and advanced filters", async () => {
    vi.mocked(apiRequest).mockResolvedValue(mockDocumentList);

    await getDocuments(20, 0, {
      search: "Example Supplier",
      status: "pending_review",
      document_type: "invoice",
      date_from: "2026-11-01",
      date_to: "2026-11-15",
    });

    expect(apiRequest).toHaveBeenCalledWith(
      "/documents/?limit=20&offset=0&search=Example+Supplier&status=pending_review&document_type=invoice&date_from=2026-11-01&date_to=2026-11-15",
    );
  });

  it("uploads a document using FormData", async () => {
    vi.mocked(apiRequest).mockResolvedValue(mockDocument);

    const file = new File(["invoice content"], "invoice.pdf", {
      type: "application/pdf",
    });

    const result = await uploadDocument(file);

    expect(apiRequest).toHaveBeenCalledOnce();

    const [endpoint, options] = vi.mocked(apiRequest).mock.calls[0];

    expect(endpoint).toBe("/documents/");
    expect(options?.method).toBe("POST");

    const formData = options?.body;
    expect(formData).toBeInstanceOf(FormData);

    if (!(formData instanceof FormData)) {
      throw new Error("Expected upload request body to be FormData");
    }

    expect(formData.get("file")).toBe(file);
    expect(result).toEqual(mockDocument);
  });

  it("retrieves a document by ID", async () => {
    vi.mocked(apiRequest).mockResolvedValue(mockDocument);

    const result = await getDocument("doc-123");

    expect(apiRequest).toHaveBeenCalledWith("/documents/doc-123");
    expect(result).toEqual(mockDocument);
  });

  it("starts document processing", async () => {
    vi.mocked(apiRequest).mockResolvedValue(mockDocument);

    await processDocument("doc-123");

    expect(apiRequest).toHaveBeenCalledWith(
      "/documents/doc-123/process",
      { method: "POST" },
    );
  });

  it("retrieves extracted document data", async () => {
    const extraction = {
      id: "extraction-123",
      document_id: "doc-123",
      supplier_name: "Example Supplier",
      invoice_number: "INV-001",
      invoice_date: "2026-11-10",
      due_date: null,
      currency: "USD",
      subtotal: 100,
      vat_amount: 15,
      total_amount: 115,
      confidence_score: null,
      extracted_data: {
        field_confidence: {
          supplier_name: "0.95",
          invoice_number: "0.95",
          invoice_date: "0.95",
          due_date: "0.95",
          currency: "0.95",
          subtotal: "0.95",
          vat_amount: "0.95",
          total_amount: "0.95",
        },
      },
      extraction_provider: "ollama",
      extraction_model: "test-model",
      created_at: "2026-11-15T10:00:00Z",
    };

    vi.mocked(apiRequest).mockResolvedValue(extraction);

    const result = await getDocumentExtraction("doc-123");

    expect(apiRequest).toHaveBeenCalledWith(
      "/documents/doc-123/extraction",
    );
    expect(result).toEqual(extraction);
  });

  it("submits a document review decision", async () => {
    const review = {
      decision: "approved" as const,
      comments: "Invoice verified.",
    };

    const response = {
      id: "review-123",
      document_id: "doc-123",
      reviewed_by: "user-123",
      decision: "approved" as const,
      comments: "Invoice verified.",
      reviewed_at: "2026-11-15T10:00:00Z",
      created_at: "2026-11-15T10:00:00Z",
    };

    vi.mocked(apiRequest).mockResolvedValue(response);

    const result = await reviewDocument("doc-123", review);

    expect(apiRequest).toHaveBeenCalledWith(
      "/documents/doc-123/review",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(review),
      },
    );
    expect(result).toEqual(response);
  });

  it("integrates an approved document with the ERP", async () => {
    const integration = {
      id: "integration-123",
      document_id: "doc-123",
      provider: "simulated_erp",
      operation: "create_invoice",
      status: "success" as const,
      external_record_id: "ERP-001",
      attempt_number: 1,
      request_payload: null,
      response_payload: null,
      error_message: null,
      started_at: "2026-11-15T10:00:00Z",
      completed_at: "2026-11-15T10:00:01Z",
      created_at: "2026-11-15T10:00:00Z",
    };

    vi.mocked(apiRequest).mockResolvedValue(integration);

    const result = await integrateDocument("doc-123");

    expect(apiRequest).toHaveBeenCalledWith(
      "/documents/doc-123/integrate",
      { method: "POST" },
    );
    expect(result).toEqual(integration);
  });

  it("retrieves ERP integration history", async () => {
    vi.mocked(apiRequest).mockResolvedValue([]);

    const result = await getIntegrationHistory("doc-123");

    expect(apiRequest).toHaveBeenCalledWith(
      "/documents/doc-123/integrations",
    );
    expect(result).toEqual([]);
  });

  it("propagates API service errors", async () => {
    vi.mocked(apiRequest).mockRejectedValue(
      new Error("Document not found"),
    );

    await expect(getDocument("missing-doc")).rejects.toThrow(
      "Document not found",
    );
  });
});
