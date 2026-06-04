"use client";

import { useState, useCallback, useEffect } from "react";
import {
  AnnotationItem,
  AppStep,
  PDFContext,
  PipelineStep,
  GenerateResponse,
} from "@/types";
import FileUpload from "@/components/FileUpload";
import ContextForm from "@/components/ContextForm";
import ProcessFlow from "@/components/ProcessFlow";
import DownloadCard from "@/components/DownloadCard";
import PreviewPane from "@/components/PreviewPane";
import { generatePPT, checkHealth } from "@/lib/api";
import { Presentation, ChevronRight, AlertTriangle, Wifi, WifiOff } from "lucide-react";

// ── pipeline step definitions ────────────────────────
const PIPELINE_STEPS: Omit<PipelineStep, "status">[] = [
  {
    id: 1,
    label: "Loading PDF Pages",
    description: "Reading and converting each page to images for analysis",
  },
  {
    id: 2,
    label: "Extracting Content",
    description: "AI agent scanning every page for key concepts and data",
  },
  {
    id: 3,
    label: "Planning Slide Structure",
    description: "Organising extracted content into a coherent slide plan",
  },
  {
    id: 4,
    label: "Writing Slide Content",
    description: "Crafting slide-ready text, bullets and titles",
  },
  {
    id: 5,
    label: "Generating PowerPoint",
    description: "Building the final .pptx file with layouts and styling",
  },
];

// Approximate durations per step (ms) for progress simulation
const STEP_DURATIONS = [4000, 18000, 10000, 18000, 8000];

const INITIAL_ANNOTATIONS: AnnotationItem[] = [
  { id: "circle", type: "circle", label: "Circle", selected: false },
  { id: "tick", type: "tick", label: "Tick", selected: false },
  { id: "highlight", type: "highlight", label: "Highlight", selected: false },
  { id: "handwritten", type: "handwritten", label: "Handwritten Note", selected: false },
];

const DEFAULT_CONTEXT: PDFContext = {
  batch: "",
  purpose: "",
  subject: "",
  class_level: "",
  language: "English",
  annotations: INITIAL_ANNOTATIONS,
};

export default function Home() {
  const [step, setStep] = useState<AppStep>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [context, setContext] = useState<PDFContext>(DEFAULT_CONTEXT);
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>(
    PIPELINE_STEPS.map((s) => ({ ...s, status: "waiting" }))
  );
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [serverOnline, setServerOnline] = useState<boolean | null>(null);
  const [previewAvailable, setPreviewAvailable] = useState(false);

  // ── health check ─────────────────────────────────────
  useEffect(() => {
    checkHealth().then((h) => {
      setServerOnline(h.online);
      setPreviewAvailable(h.previewAvailable);
    });
  }, []);

  // ── validate required fields ──────────────────────────
  const isFormValid =
    context.subject &&
    context.batch.trim() &&
    context.class_level &&
    context.purpose;

  // ── simulate step progression during API call ─────────
  const simulateProgress = useCallback(
    (onComplete: () => void) => {
      let stepIndex = 0;

      const advance = () => {
        if (stepIndex >= PIPELINE_STEPS.length) {
          onComplete();
          return;
        }

        // mark current as active
        setPipelineSteps((prev) =>
          prev.map((s, i) =>
            i === stepIndex
              ? { ...s, status: "active" }
              : i < stepIndex
              ? { ...s, status: "done" }
              : s
          )
        );

        const duration = STEP_DURATIONS[stepIndex];
        stepIndex++;
        setTimeout(advance, duration);
      };

      advance();
    },
    []
  );

  // ── start generation ──────────────────────────────────
  const handleGenerate = useCallback(async () => {
    if (!file) return;
    setError(null);
    setStep("processing");
    setPipelineSteps(PIPELINE_STEPS.map((s) => ({ ...s, status: "waiting" })));

    // Fire API call + simulate progress in parallel
    const apiPromise = generatePPT(file, context);

    let simulationDone = false;
    let apiDone = false;
    let apiResult: GenerateResponse | null = null;
    let apiError: string | null = null;

    const tryFinish = () => {
      if (simulationDone && apiDone) {
        // Mark all steps done
        setPipelineSteps((prev) => prev.map((s) => ({ ...s, status: "done" })));
        setTimeout(() => {
          if (apiError) {
            setError(apiError);
            setStep("configure");
          } else if (apiResult) {
            setResult(apiResult);
            setStep("done");
          }
        }, 600);
      }
    };

    simulateProgress(() => {
      simulationDone = true;
      tryFinish();
    });

    apiPromise
      .then((res) => {
        apiResult = res;
        apiDone = true;
        tryFinish();
      })
      .catch((err: Error) => {
        apiError = err.message || "Something went wrong";
        apiDone = true;
        tryFinish();
      });
  }, [file, context, simulateProgress]);

  // ── reset ────────────────────────────────────────────
  const handleReset = () => {
    setStep("upload");
    setFile(null);
    setContext(DEFAULT_CONTEXT);
    setResult(null);
    setError(null);
    setPipelineSteps(PIPELINE_STEPS.map((s) => ({ ...s, status: "waiting" })));
  };

  // ── step labels for breadcrumb ────────────────────────
  const stepMeta: Record<AppStep, { num: number; label: string }> = {
    upload: { num: 1, label: "Upload PDF" },
    configure: { num: 2, label: "Configure" },
    processing: { num: 3, label: "Processing" },
    done: { num: 4, label: "Download" },
  };

  const visibleSteps: AppStep[] = ["upload", "configure", "processing", "done"];

  return (
    <div className="flex min-h-screen flex-col bg-[#090909]">
      {/* ── Navbar ─────────────────────────────────── */}
      <header className="flex items-center justify-between border-b border-white/5 px-6 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-600 shadow-lg shadow-violet-500/30">
            <Presentation className="h-4 w-4 text-white" />
          </div>
          <span className="text-sm font-semibold text-white">SlideForge</span>
          <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] font-medium text-violet-400 ring-1 ring-violet-500/20">
            AI
          </span>
        </div>

        {/* Server status */}
        <div className="flex items-center gap-1.5">
          {serverOnline === null ? (
            <span className="text-xs text-zinc-600">Checking server…</span>
          ) : serverOnline ? (
            <>
              <Wifi className="h-3.5 w-3.5 text-emerald-500" />
              <span className="text-xs text-zinc-500">Backend connected</span>
            </>
          ) : (
            <>
              <WifiOff className="h-3.5 w-3.5 text-red-500" />
              <span className="text-xs text-red-400">Backend offline</span>
            </>
          )}
        </div>
      </header>

      {/* ── Main ───────────────────────────────────── */}
      <main className="flex flex-1 flex-col items-center px-4 py-12">
        {/* Step indicator */}
        {step !== "processing" && (
          <div className="mb-8 flex items-center gap-2">
            {visibleSteps.map((s, i) => {
              const meta = stepMeta[s];
              const isActive = s === step;
              const isDone =
                visibleSteps.indexOf(s) < visibleSteps.indexOf(step);

              return (
                <div key={s} className="flex items-center gap-2">
                  <div
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all ${
                      isActive
                        ? "bg-violet-500/15 text-violet-300 ring-1 ring-violet-500/30"
                        : isDone
                        ? "text-zinc-500"
                        : "text-zinc-700"
                    }`}
                  >
                    <span
                      className={`flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold ${
                        isActive
                          ? "bg-violet-500 text-white"
                          : isDone
                          ? "bg-zinc-700 text-zinc-400"
                          : "bg-zinc-800 text-zinc-600"
                      }`}
                    >
                      {isDone ? "✓" : meta.num}
                    </span>
                    {meta.label}
                  </div>
                  {i < visibleSteps.length - 1 && (
                    <ChevronRight className="h-3 w-3 text-zinc-700" />
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Card — wider when preview is shown */}
        <div
          className={`w-full rounded-3xl border border-white/[0.07] bg-[#111113] shadow-2xl shadow-black/50 ${
            step === "done" ? "max-w-5xl" : "max-w-xl"
          }`}
        >
          {/* Card Header */}
          {step !== "processing" && step !== "done" && (
            <div className="border-b border-white/5 px-6 py-5">
              <h1 className="text-base font-semibold text-white">
                {step === "upload" && "Upload your teaching PDF"}
                {step === "configure" && "Configure slide settings"}
              </h1>
              <p className="mt-0.5 text-sm text-zinc-500">
                {step === "upload" &&
                  "Drop in any lecture PDF — annotated or plain"}
                {step === "configure" &&
                  "Tell the AI about your class so slides are perfectly tailored"}
              </p>
            </div>
          )}

          {/* Card Body */}
          <div className="p-6">
            {/* Error Banner */}
            {error && (
              <div className="mb-5 flex items-start gap-3 rounded-xl border border-red-500/20 bg-red-500/8 p-4">
                <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" />
                <div>
                  <p className="text-sm font-medium text-red-300">
                    Generation failed
                  </p>
                  <p className="mt-0.5 text-xs text-red-400/80">{error}</p>
                </div>
              </div>
            )}

            {/* ── STEP: upload ── */}
            {step === "upload" && (
              <div className="space-y-5">
                <FileUpload
                  file={file}
                  onFileSelect={setFile}
                  onFileClear={() => setFile(null)}
                />
                <button
                  disabled={!file}
                  onClick={() => setStep("configure")}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-500/20 transition-all hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-30 active:scale-[0.98]"
                >
                  Continue
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            )}

            {/* ── STEP: configure ── */}
            {step === "configure" && (
              <div className="space-y-5">
                <ContextForm context={context} onChange={setContext} />

                {/* Backend offline warning */}
                {serverOnline === false && (
                  <div className="flex items-center gap-2 rounded-xl border border-amber-500/20 bg-amber-500/8 px-4 py-3">
                    <WifiOff className="h-4 w-4 text-amber-400 flex-shrink-0" />
                    <p className="text-xs text-amber-300">
                      Backend server is offline. Start it with{" "}
                      <code className="rounded bg-white/5 px-1 font-mono">
                        uvicorn app:app --reload
                      </code>
                    </p>
                  </div>
                )}

                <div className="flex gap-3">
                  <button
                    onClick={() => setStep("upload")}
                    className="flex items-center gap-1.5 rounded-xl border border-white/8 bg-white/[0.04] px-4 py-3 text-sm font-medium text-zinc-400 transition-all hover:bg-white/[0.08]"
                  >
                    Back
                  </button>
                  <button
                    disabled={!isFormValid || serverOnline === false}
                    onClick={handleGenerate}
                    className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-500/20 transition-all hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-30 active:scale-[0.98]"
                  >
                    <Presentation className="h-4 w-4" />
                    Generate Slides
                  </button>
                </div>
              </div>
            )}

            {/* ── STEP: processing ── */}
            {step === "processing" && (
              <ProcessFlow
                steps={pipelineSteps}
                fileName={file?.name ?? ""}
              />
            )}

            {/* ── STEP: done ── */}
            {step === "done" && result && (
              <div
                className={
                  previewAvailable && result.filename
                    ? "grid gap-6 md:grid-cols-[1fr_minmax(0,1.4fr)]"
                    : "mx-auto max-w-md"
                }
              >
                <DownloadCard
                  result={result}
                  previewAvailable={previewAvailable}
                  onReset={handleReset}
                />
                {previewAvailable && result.filename && (
                  <PreviewPane
                    filename={result.filename}
                    previewAvailable={previewAvailable}
                  />
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer note */}
        <p className="mt-8 text-xs text-zinc-700">
          Powered by Gemini AI · Physics Wallah DPT Tool
        </p>
      </main>
    </div>
  );
}
