export interface AnnotationItem {
  id: string;
  type: "circle" | "tick" | "highlight" | "handwritten" | "other";
  label: string;
  selected: boolean;
  reason?: string;
  customName?: string; // for 'other'
}

export interface PDFContext {
  batch: string;
  purpose: string;
  subject: string;
  class_level: string;
  language: string;
  annotations: AnnotationItem[];
  extra_context?: string;
}

export interface AnalyticsRow {
  stage: string;
  model: string;
  attempts: number;
  responses: number;
  failures: number;
  input_tokens: number;
  output_tokens: number;
  thinking_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface AnalyticsTotals {
  attempts: number;
  responses: number;
  failures: number;
  input_tokens: number;
  output_tokens: number;
  thinking_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface Analytics {
  elapsed_seconds: number;
  pricing_note: string;
  totals: AnalyticsTotals;
  rows: AnalyticsRow[];
}

export interface GenerateResponse {
  status: "success" | "error";
  job_id?: string;
  filename?: string;
  download_url?: string;
  preview_url?: string;
  total_pages?: number;
  total_slides?: number;
  message?: string;
  analytics?: Analytics;
}

export type AppStep = "upload" | "configure" | "processing" | "done";

export type PipelineStepStatus = "waiting" | "active" | "done" | "error";

export interface PipelineStep {
  id: number;
  label: string;
  description: string;
  status: PipelineStepStatus;
}
