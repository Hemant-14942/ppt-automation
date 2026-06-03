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

export interface GenerateResponse {
  status: "success" | "error";
  filename?: string;
  total_pages?: number;
  total_slides?: number;
  message?: string;
}

export type AppStep = "upload" | "configure" | "processing" | "done";

export type PipelineStepStatus = "waiting" | "active" | "done" | "error";

export interface PipelineStep {
  id: number;
  label: string;
  description: string;
  status: PipelineStepStatus;
}
