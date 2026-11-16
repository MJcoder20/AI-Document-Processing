import { apiRequest, apiRequestBlob } from "./apiClient";
import type {
  DocumentResponse,
  DocumentListResponse,
  ExtractionResultResponse,
  DocumentApprovalCreate,
  DocumentApprovalResponse,
  IntegrationLogResponse,
  ExtractionCorrection,
  ExtractionEditResponse,
  DocumentStatus,
  DocumentType,
} from "../types/document";

import type {
  UserResponse,
  TokenResponse,
  LoginRequest,
  RegisterRequest,
} from "../types/auth";

export function loginUser(data: LoginRequest): Promise<TokenResponse> {
  return apiRequest<TokenResponse>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function registerUser(data: RegisterRequest): Promise<UserResponse> {
  return apiRequest<UserResponse>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export function getCurrentUser(): Promise<UserResponse> {
  return apiRequest<UserResponse>("/auth/me");
}

export function previewDocumentFile(documentId: string): Promise<Blob> {
  return apiRequestBlob(`/documents/${documentId}/preview`);
}

export function downloadDocumentFile(documentId: string): Promise<Blob> {
  return apiRequestBlob(`/documents/${documentId}/download`);
}


export interface DocumentFilters {
  search?: string;
  status?: DocumentStatus;
  document_type?: DocumentType;
  date_from?: string;
  date_to?: string;
}

// Retrieve filtered and paginated documents
export function getDocuments(
  limit = 20,
  offset = 0,
  filters: DocumentFilters = {},
): Promise<DocumentListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });

  if (filters.search?.trim()) {
    params.set("search", filters.search.trim());
  }

  if (filters.status) {
    params.set("status", filters.status);
  }

  if (filters.document_type) {
    params.set("document_type", filters.document_type);
  }

  if (filters.date_from) {
    params.set("date_from", filters.date_from);
  }

  if (filters.date_to) {
    params.set("date_to", filters.date_to);
  }

  return apiRequest<DocumentListResponse>(
    `/documents/?${params.toString()}`,
  );
}

// Upload a document
export async function uploadDocument(
  file: File,
): Promise<DocumentResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return apiRequest<DocumentResponse>("/documents/", {
    method: "POST",
    body: formData,
  });
}

// Retrieve document details
export function getDocument(
  documentId: string,
): Promise<DocumentResponse> {
  return apiRequest<DocumentResponse>(`/documents/${documentId}`);
}

// Start document processing
export function processDocument(
  documentId: string,
): Promise<DocumentResponse | ExtractionResultResponse> {
  return apiRequest(`/documents/${documentId}/process`, {
    method: "POST",
  });
}

// Retrieve extracted invoice data
export function getDocumentExtraction(
  documentId: string,
): Promise<ExtractionResultResponse> {
  return apiRequest<ExtractionResultResponse>(
    `/documents/${documentId}/extraction`,
  );
}

// Approve or reject a document
export function reviewDocument(
  documentId: string,
  data: DocumentApprovalCreate,
): Promise<DocumentApprovalResponse> {
  return apiRequest<DocumentApprovalResponse>(
    `/documents/${documentId}/review`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    },
  );
}

// Integrate an approved document with the ERP
export function integrateDocument(
  documentId: string,
): Promise<IntegrationLogResponse> {
  return apiRequest<IntegrationLogResponse>(
    `/documents/${documentId}/integrate`,
    {
      method: "POST",
    },
  );
}

// Retrieve ERP integration history
export function getIntegrationHistory(
  documentId: string,
): Promise<IntegrationLogResponse[]> {
  return apiRequest<IntegrationLogResponse[]>(
    `/documents/${documentId}/integrations`,
  );
}


// Correct extracted invoice fields and revalidate
export function correctDocumentExtraction(
  documentId: string,
  corrections: ExtractionCorrection,
): Promise<ExtractionResultResponse> {
  return apiRequest<ExtractionResultResponse>(
    `/documents/${documentId}/extraction`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(corrections),
    },
  );
}

// Retrieve extraction correction audit history
export function getExtractionHistory(
  documentId: string,
): Promise<ExtractionEditResponse[]> {
  return apiRequest<ExtractionEditResponse[]>(
    `/documents/${documentId}/extraction/history`,
  );
}
