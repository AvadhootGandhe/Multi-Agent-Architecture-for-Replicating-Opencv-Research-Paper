"use client";

import { CheckCircle2, ClipboardCheck, XCircle } from "lucide-react";

import type { EvaluationReport, TestDiagnostics } from "@/types";

export function ReviewPanel({
  evaluation,
  diagnostics,
}: {
  evaluation: EvaluationReport | null;
  diagnostics: TestDiagnostics | null;
}) {
  const score = evaluation?.overall_match ?? 0;
  const isComplete = evaluation?.complete === true;

  const scoreColor =
    score >= 90
      ? "text-green-700"
      : score >= 60
        ? "text-amber-600"
        : "text-red-600";

  const barColor =
    score >= 90
      ? "bg-green-500"
      : score >= 60
        ? "bg-amber-400"
        : "bg-red-400";

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex h-12 items-center gap-2 border-b border-slate-200 px-4 text-sm font-semibold text-slate-900">
        <ClipboardCheck size={17} />
        Evaluator &amp; Tests
      </div>

      <div className="p-4 space-y-5">
        {/* ── Success banner ─────────────────────────────────────── */}
        {isComplete && (
          <div className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 p-3">
            <CheckCircle2 size={20} className="shrink-0 text-green-600" />
            <div>
              <p className="text-sm font-semibold text-green-800">
                ✅ Paper Successfully Replicated!
              </p>
              <p className="text-xs text-green-700 mt-0.5">
                Implementation matches the research paper. Download your project below.
              </p>
            </div>
          </div>
        )}

        {/* ── Evaluator Score ────────────────────────────────────── */}
        <div>
          <div className="flex items-end justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Architecture Match
            </p>
            <span className={`text-3xl font-bold tabular-nums ${scoreColor}`}>
              {evaluation ? `${score.toFixed(1)}%` : "—"}
            </span>
          </div>
          {/* Progress bar */}
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full rounded-full transition-all duration-700 ${barColor}`}
              style={{ width: `${score}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-slate-400">
            {evaluation
              ? isComplete
                ? "Complete — ready for download"
                : "Not yet complete — evaluator is requesting another iteration"
              : "Waiting for evaluator agent…"}
          </p>
        </div>

        {/* ── Test Diagnostics ───────────────────────────────────── */}
        <div className="rounded-md border border-slate-200 p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Test Diagnostics
            </p>
            {diagnostics ? (
              diagnostics.passed ? (
                <span className="flex items-center gap-1 text-xs font-semibold text-green-700">
                  <CheckCircle2 size={13} /> Passed
                </span>
              ) : (
                <span className="flex items-center gap-1 text-xs font-semibold text-red-600">
                  <XCircle size={13} /> Failed
                </span>
              )
            ) : (
              <span className="text-xs text-slate-400">Waiting…</span>
            )}
          </div>
          {diagnostics?.errors && diagnostics.errors.length > 0 && (
            <ul className="mt-2 space-y-1">
              {diagnostics.errors.slice(0, 5).map((err, i) => (
                <li key={i} className="rounded bg-red-50 px-2 py-1 font-mono text-xs text-red-700 break-all">
                  {err}
                </li>
              ))}
              {diagnostics.errors.length > 5 && (
                <li className="text-xs text-slate-400">…and {diagnostics.errors.length - 5} more</li>
              )}
            </ul>
          )}
          {diagnostics?.checks && diagnostics.checks.length > 0 && diagnostics.passed && (
            <ul className="mt-2 space-y-1">
              {diagnostics.checks.slice(0, 4).map((c, i) => (
                <li key={i} className="rounded bg-green-50 px-2 py-1 text-xs text-green-700">
                  ✓ {c}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* ── Missing components ────────────────────────────────── */}
        {evaluation?.missing && evaluation.missing.length > 0 && (
          <List
            title="Missing Components"
            values={evaluation.missing}
            empty="No missing components."
            variant="warning"
          />
        )}

        {/* ── Planner Feedback ──────────────────────────────────── */}
        {evaluation?.planner_feedback && evaluation.planner_feedback.length > 0 && (
          <List
            title="Feedback Sent to Planner"
            values={evaluation.planner_feedback}
            empty=""
            variant="info"
          />
        )}

        {/* ── Recommendations ───────────────────────────────────── */}
        {evaluation?.recommendations && evaluation.recommendations.length > 0 && (
          <List
            title="Recommendations"
            values={evaluation.recommendations}
            empty=""
            variant="neutral"
          />
        )}
      </div>
    </section>
  );
}

function List({
  title,
  values,
  empty,
  variant,
}: {
  title: string;
  values: string[];
  empty: string;
  variant: "warning" | "info" | "neutral";
}) {
  const itemClass =
    variant === "warning"
      ? "rounded bg-amber-50 px-2 py-1.5 text-xs text-amber-800"
      : variant === "info"
        ? "rounded bg-sky-50 px-2 py-1.5 text-xs text-sky-800"
        : "rounded bg-slate-50 px-2 py-1.5 text-xs text-slate-700";

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      {values.length ? (
        <ul className="mt-2 space-y-1">
          {values.map((v, i) => (
            <li key={i} className={itemClass}>
              {v}
            </li>
          ))}
        </ul>
      ) : empty ? (
        <p className="mt-1 text-xs text-slate-400">{empty}</p>
      ) : null}
    </div>
  );
}
