"use client";

import { BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

import type { KnowledgeBundle } from "@/types";

export function KnowledgePanel({ knowledge }: { knowledge: KnowledgeBundle | null }) {
  const [open, setOpen] = useState(true);
  const [showRawText, setShowRawText] = useState(false);

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <button
        className="flex h-12 w-full items-center justify-between gap-2 border-b border-slate-200 px-4 text-sm font-semibold text-slate-900"
        onClick={() => setOpen((p) => !p)}
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <BookOpen size={17} />
          Parsed Paper Knowledge
        </span>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>

      {open && (
        <div className="p-4 space-y-4">
          {!knowledge ? (
            <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-500">
              Appears after the parser agent completes.
            </p>
          ) : (
            <>
              {/* Title + meta */}
              <div>
                <h2 className="text-base font-semibold text-slate-900 leading-snug">
                  {knowledge.paper.metadata.title}
                </h2>
                {knowledge.paper.metadata.authors.length > 0 && (
                  <p className="mt-1 text-xs text-slate-500">
                    {knowledge.paper.metadata.authors.join(", ")}
                  </p>
                )}
                <div className="mt-1 flex gap-3 text-xs text-slate-400">
                  <span>{knowledge.paper.metadata.page_count} pages</span>
                  <span>{knowledge.paper.metadata.source_filename}</span>
                </div>
              </div>

              {/* Abstract */}
              {knowledge.paper.metadata.abstract && (
                <div>
                  <Tag>Abstract</Tag>
                  <p className="mt-1 text-xs leading-5 text-slate-600 line-clamp-4">
                    {knowledge.paper.metadata.abstract}
                  </p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                {/* Architecture */}
                <Chip label="Backbone" value={knowledge.paper.backbone ?? "—"} accent="sky" />
                <Chip
                  label="Architecture"
                  value={knowledge.paper.architecture.slice(0, 4).join(", ") || "—"}
                  accent="violet"
                />
              </div>

              {/* Losses */}
              {knowledge.paper.loss_functions.length > 0 && (
                <TagList label="Loss Functions" items={knowledge.paper.loss_functions} color="rose" />
              )}

              {/* Preprocessing */}
              {knowledge.paper.preprocessing.length > 0 && (
                <TagList label="Preprocessing" items={knowledge.paper.preprocessing} color="amber" />
              )}

              {/* Libraries */}
              {knowledge.paper.external_libraries.length > 0 && (
                <TagList label="Libraries" items={knowledge.paper.external_libraries} color="slate" />
              )}

              {/* Hyperparameters */}
              {Object.keys(knowledge.paper.hyperparameters).length > 0 && (
                <div>
                  <Tag>Hyperparameters</Tag>
                  <div className="mt-2 grid grid-cols-2 gap-1">
                    {Object.entries(knowledge.paper.hyperparameters).map(([k, v]) => (
                      <div key={k} className="flex justify-between rounded bg-slate-50 px-2 py-1 text-xs">
                        <span className="text-slate-500 capitalize">{k.replace(/_/g, " ")}</span>
                        <span className="font-mono font-medium text-slate-800">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Raw Text */}
              {knowledge.paper.raw_text && (
                <div className="border-t border-slate-100 pt-3">
                  <button
                    onClick={() => setShowRawText(!showRawText)}
                    className="flex w-full items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-400 hover:text-slate-600 transition"
                  >
                    <span>Full Paper Text ({knowledge.paper.raw_text.length} chars)</span>
                    <span className="text-[10px] text-indigo-600 font-normal normal-case">
                      {showRawText ? "hide" : "show"}
                    </span>
                  </button>
                  {showRawText && (
                    <pre className="mt-2 max-h-60 overflow-y-auto rounded bg-slate-50 p-2 font-mono text-[10px] leading-relaxed text-slate-600 whitespace-pre-wrap select-all">
                      {knowledge.paper.raw_text}
                    </pre>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{children}</p>
  );
}

function Chip({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: "sky" | "violet" | "green";
}) {
  const colors: Record<string, string> = {
    sky: "bg-sky-50 text-sky-800 border-sky-200",
    violet: "bg-violet-50 text-violet-800 border-violet-200",
    green: "bg-green-50 text-green-800 border-green-200",
  };
  return (
    <div className={`rounded-md border p-2 ${colors[accent] ?? colors.sky}`}>
      <p className="text-xs font-semibold uppercase tracking-wide opacity-60">{label}</p>
      <p className="mt-0.5 text-xs font-medium leading-5 break-words">{value}</p>
    </div>
  );
}

function TagList({
  label,
  items,
  color,
}: {
  label: string;
  items: string[];
  color: "rose" | "amber" | "slate" | "green";
}) {
  const badge: Record<string, string> = {
    rose: "bg-rose-50 text-rose-700 border-rose-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    slate: "bg-slate-100 text-slate-600 border-slate-200",
    green: "bg-green-50 text-green-700 border-green-200",
  };
  return (
    <div>
      <Tag>{label}</Tag>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {items.map((item) => (
          <span
            key={item}
            className={`rounded border px-2 py-0.5 text-xs font-medium ${badge[color] ?? badge.slate}`}
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}
