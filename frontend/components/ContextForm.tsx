"use client";

import { PDFContext, AnnotationItem } from "@/types";
import { ChevronDown, Info, Plus, Trash2 } from "lucide-react";

interface ContextFormProps {
  context: PDFContext;
  onChange: (ctx: PDFContext) => void;
}

const inputCls =
  "w-full rounded-xl border border-white/8 bg-white/[0.04] px-4 py-2.5 text-sm text-white placeholder-zinc-600 outline-none transition-all focus:border-violet-500/60 focus:bg-white/[0.06] focus:ring-1 focus:ring-violet-500/30";

const selectCls =
  "w-full appearance-none rounded-xl border border-white/8 bg-white/[0.04] px-4 py-2.5 text-sm text-white outline-none transition-all focus:border-violet-500/60 focus:bg-white/[0.06] focus:ring-1 focus:ring-violet-500/30 cursor-pointer";

const labelCls = "mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-500";

function SelectWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative">
      {children}
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-600" />
    </div>
  );
}

export default function ContextForm({ context, onChange }: ContextFormProps) {
  const set = <K extends keyof PDFContext>(key: K, val: PDFContext[K]) =>
    onChange({ ...context, [key]: val });

  const updateAnnotation = (id: string, updates: Partial<AnnotationItem>) => {
    const newAnnotations = context.annotations.map((ann) =>
      ann.id === id ? { ...ann, ...updates } : ann
    );
    set("annotations", newAnnotations);
  };

  const addAnnotation = () => {
    const newId = `other-${Date.now()}`;
    const newAnn: AnnotationItem = {
      id: newId,
      type: "other",
      label: "Other",
      selected: true,
      customName: "",
      reason: "",
    };
    set("annotations", [...context.annotations, newAnn]);
  };

  const removeAnnotation = (id: string) => {
    set(
      "annotations",
      context.annotations.filter((ann) => ann.id !== id)
    );
  };

  return (
    <div className="space-y-6">
      {/* Row 1: Subject + Batch */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelCls}>Subject *</label>
          <SelectWrapper>
            <select
              className={selectCls}
              value={context.subject}
              onChange={(e) => set("subject", e.target.value)}
            >
              <option value="" disabled>
                Select subject
              </option>
              <option value="Physics">Physics</option>
              <option value="Chemistry">Chemistry</option>
              <option value="Mathematics">Mathematics</option>
              <option value="Biology">Biology</option>
              <option value="English">English</option>
              <option value="Social Science">Social Science</option>
              <option value="Other">Other</option>
            </select>
          </SelectWrapper>
        </div>
        <div>
          <label className={labelCls}>Batch *</label>
          <input
            className={inputCls}
            placeholder="e.g. JEE 2025 Batch A"
            value={context.batch}
            onChange={(e) => set("batch", e.target.value)}
          />
        </div>
      </div>

      {/* Row 2: Class Level + Purpose */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelCls}>Class Level *</label>
          <SelectWrapper>
            <select
              className={selectCls}
              value={context.class_level}
              onChange={(e) => set("class_level", e.target.value)}
            >
              <option value="" disabled>
                Select level
              </option>
              <option value="Class 1-5">Class 1-5</option>
              <option value="Class 6-8">Class 6-8</option>
              <option value="Class 9-10">Class 9-10</option>
              <option value="Class 11-12">Class 11-12</option>
              <option value="UG / College">UG / College</option>
              <option value="Competitive Exam">Competitive Exam</option>
            </select>
          </SelectWrapper>
        </div>
        <div>
          <label className={labelCls}>Purpose *</label>
          <SelectWrapper>
            <select
              className={selectCls}
              value={context.purpose}
              onChange={(e) => set("purpose", e.target.value)}
            >
              <option value="" disabled>
                Select purpose
              </option>
              <option value="Revision">Revision</option>
              <option value="Lecture Notes">Lecture Notes</option>
              <option value="DPP">DPP (Daily Practice)</option>
              <option value="Summary">Summary</option>
              <option value="Assignment">Assignment</option>
              <option value="Test Paper">Test Paper</option>
              <option value="Formula Sheet">Formula Sheet</option>
            </select>
          </SelectWrapper>
        </div>
      </div>

      {/* Row 3: Language */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelCls}>Language *</label>
          <SelectWrapper>
            <select
              className={selectCls}
              value={context.language}
              onChange={(e) => set("language", e.target.value)}
            >
              <option value="English">English</option>
              <option value="Hindi">Hindi</option>
              <option value="Hinglish">Hinglish</option>
            </select>
          </SelectWrapper>
        </div>
      </div>

      {/* Annotations */}
      <div className="rounded-2xl border border-white/6 bg-white/[0.02] p-4">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
              Annotation Meanings
            </p>
            <div className="group relative">
              <Info className="h-3.5 w-3.5 text-zinc-600 cursor-help" />
              <div className="pointer-events-none absolute left-5 top-0 z-10 w-52 rounded-xl border border-white/10 bg-[#18181b] p-3 text-xs text-zinc-400 opacity-0 shadow-xl transition-opacity group-hover:opacity-100">
                Select the marks present in your PDF and explain what they mean for the AI.
              </div>
            </div>
          </div>
          <button
            onClick={addAnnotation}
            className="flex items-center gap-1 rounded-lg bg-violet-500/10 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-violet-400 ring-1 ring-violet-500/20 transition-all hover:bg-violet-500/20"
          >
            <Plus className="h-3 w-3" />
            Add More
          </button>
        </div>

        <div className="space-y-3">
          {context.annotations.map((ann) => (
            <div
              key={ann.id}
              className="group relative space-y-2 rounded-xl border border-white/5 bg-white/[0.01] p-3 transition-all hover:bg-white/[0.03]"
            >
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-white/10 bg-white/5 text-violet-600 focus:ring-violet-500/30"
                  checked={ann.selected}
                  onChange={(e) =>
                    updateAnnotation(ann.id, { selected: e.target.checked })
                  }
                />
                
                {ann.type === "other" ? (
                  <input
                    className={`${inputCls} !py-1.5 !px-3 text-xs`}
                    placeholder="Annotation name (e.g. Star)"
                    value={ann.customName || ""}
                    onChange={(e) =>
                      updateAnnotation(ann.id, { customName: e.target.value })
                    }
                  />
                ) : (
                  <span className="text-sm font-medium text-zinc-300">
                    {ann.label}
                  </span>
                )}

                {ann.type === "other" && (
                  <button
                    onClick={() => removeAnnotation(ann.id)}
                    className="ml-auto text-zinc-600 transition-colors hover:text-red-400"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>

              {ann.selected && (
                <div className="pl-7">
                  <input
                    className={`${inputCls} !py-1.5 !px-3 text-xs`}
                    placeholder="Why this annotation? (e.g. Important point)"
                    value={ann.reason || ""}
                    onChange={(e) =>
                      updateAnnotation(ann.id, { reason: e.target.value })
                    }
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Extra Context */}
      <div>
        <label className={labelCls}>Extra Context (optional)</label>
        <textarea
          className={`${inputCls} min-h-[80px] resize-none`}
          placeholder="Any additional instructions for the AI…"
          value={context.extra_context || ""}
          onChange={(e) => set("extra_context", e.target.value || undefined)}
        />
      </div>
    </div>
  );
}
