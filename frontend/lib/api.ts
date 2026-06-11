import { PDFContext, GenerateResponse } from "@/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function generatePPT(
  file: File,
  context: PDFContext
): Promise<GenerateResponse> {
  const formData = new FormData();
  formData.append("pdf_file", file);
  formData.append("context_json", JSON.stringify(context));

  const res = await fetch(`${BASE_URL}/api/generate`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }

  return res.json();
}

export async function generatePPTFromUrl(
  pdfUrl: string,
  context: PDFContext
): Promise<GenerateResponse> {
  const formData = new FormData();
  formData.append("pdf_url", pdfUrl);
  formData.append("context_json", JSON.stringify(context));

  const res = await fetch(`${BASE_URL}/api/generate-from-url`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `Server error: ${res.status}`);
  }

  return res.json();
}

export function getDownloadURL(filename: string): string {
  return `${BASE_URL}/api/download/${encodeURIComponent(filename)}`;
}

export function getPreviewURL(filename: string): string {
  return `${BASE_URL}/api/preview/${encodeURIComponent(filename)}`;
}

export function getPdfDownloadURL(filename: string): string {
  return `${BASE_URL}/api/download-pdf/${encodeURIComponent(filename)}`;
}

export interface HealthStatus {
  online: boolean;
  previewAvailable: boolean;
}

export async function checkHealth(): Promise<HealthStatus> {
  try {
    const res = await fetch(`${BASE_URL}/api/health`, { cache: "no-store" });
    if (!res.ok) return { online: false, previewAvailable: false };
    const data = await res.json();
    return {
      online: true,
      previewAvailable: Boolean(data.preview_available),
    };
  } catch {
    return { online: false, previewAvailable: false };
  }
}
