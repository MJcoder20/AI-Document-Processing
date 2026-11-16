export type DocumentType =
  | "invoice"
  | "purchase_order"
  | "contract"
  | "other"
  | "unknown";


export interface DuplicateInvoiceReference {
  document_id: string;
  filename: string;
  supplier_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  currency: string | null;
  total_amount: string | null;
  created_at: string | null;
}


export interface ExtractionResultResponse {
  id: string;
  document_id: string;

  supplier_name: string | null;
  invoice_number: string | null;

  invoice_date: string | null;
  due_date: string | null;

  currency: string | null;

  subtotal: number | null;
  vat_amount: number | null;
  total_amount: number | null;

  confidence_score: number | null;

  extracted_data: {
    validation?: {
      warnings?: unknown[];
      errors?: unknown[];
      status?: string;
      is_valid?: boolean;
      duplicate_detected?: boolean;
      duplicate_of?: DuplicateInvoiceReference | null;
    };
    [key: string]: unknown;
  };

  extraction_provider: string | null;
  extraction_model: string | null;

  created_at: string;
}


export interface ExtractionCorrection {
  supplier_name?: string | null;
  invoice_number?: string | null;
  invoice_date?: string | null;
  due_date?: string | null;
  currency?: string | null;
  subtotal?: number | null;
  vat_amount?: number | null;
  total_amount?: number | null;
}

export interface ExtractionEditResponse {
  id: string;
  document_id: string;
  extraction_id: string;
  edited_by: string;
  changed_fields: string[];
  before_data: Record<string, string | null>;
  after_data: Record<string, string | null>;
  created_at: string;
}


export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "extracted"
  | "pending_review"
  | "approved"
  | "rejected"
  | "integration_pending"
  | "integrated"
  | "failed";

export interface DocumentResponse {
  id: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  document_type: DocumentType;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}


export type ApprovalDecision = "approved" | "rejected";

export interface DocumentApprovalCreate {
  decision: ApprovalDecision;
  comments: string | null;
}

export interface DocumentApprovalResponse {
  id: string;
  document_id: string;
  reviewed_by: string | null;
  decision: ApprovalDecision;
  comments: string | null;
  reviewed_at: string;
  created_at: string;
}


export type IntegrationStatus =
  | "pending"
  | "processing"
  | "success"
  | "failed";

export interface IntegrationLogResponse {
  id: string;
  document_id: string;

  provider: string;
  operation: string;
  status: IntegrationStatus;

  external_record_id: string | null;
  attempt_number: number;

  request_payload: Record<string, unknown> | null;
  response_payload: Record<string, unknown> | null;

  error_message: string | null;

  started_at: string;
  completed_at: string | null;
  created_at: string;
}

