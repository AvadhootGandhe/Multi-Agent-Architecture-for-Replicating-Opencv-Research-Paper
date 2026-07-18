"use client";

import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";

import type { RunStatus } from "@/types";

const STEPS: { status: RunStatus; label: string }[] = [
  { status: "queued", label: "Queued" },
  { status: "parsing", label: "Parse PDF" },
  { status: "planning", label: "Plan" },
  { status: "building", label: "Build Code" },
  { status: "testing", label: "Test" },
  { status: "evaluating", label: "Evaluate" },
  { status: "human_review", label: "Human Review" },
  { status: "completed", label: "Complete ✅" },
];

export function ProgressRail({
  status,
  iteration,
  buildAttempt,
}: {
  status?: RunStatus;
  iteration: number;
  buildAttempt?: number;
}) {
  const activeIndex = status ? STEPS.findIndex((s) => s.status === status) : -1;
  const isFailed = status === "failed";

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Pipeline Progress</h2>
        <div className="flex gap-2 text-xs text-slate-500">
          {iteration > 0 && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium">
              Iter {iteration}
            </span>
          )}
          {buildAttempt != null && buildAttempt > 0 && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-700">
              Build #{buildAttempt}
            </span>
          )}
        </div>
      </div>

      <ol className="mt-4 space-y-2">
        {STEPS.map((step, index) => {
          const isDone =
            status === "completed" ||
            (activeIndex > index && !isFailed);
          const isActive = activeIndex === index;
          const isCurrent = isActive && !isFailed;

          // Build and Test steps get sub-labels when active
          const showBuildAttempt =
            (step.status === "building" || step.status === "testing") &&
            isActive &&
            buildAttempt != null &&
            buildAttempt > 1;

          return (
            <li key={step.status} className="flex items-center gap-3">
              {/* Icon */}
              <span className="shrink-0">
                {isFailed && isActive ? (
                  <XCircle size={18} className="text-red-500" />
                ) : isDone ? (
                  <CheckCircle2 size={18} className="text-green-500" />
                ) : isCurrent ? (
                  <Loader2 size={18} className="animate-spin text-sky-600" />
                ) : (
                  <Circle size={18} className="text-slate-200" />
                )}
              </span>

              {/* Label */}
              <span
                className={`text-sm ${
                  isCurrent
                    ? "font-semibold text-slate-950"
                    : isDone
                      ? "text-slate-500"
                      : "text-slate-300"
                }`}
              >
                {step.label}
                {showBuildAttempt && (
                  <span className="ml-1.5 text-xs text-amber-600 font-normal">
                    attempt {buildAttempt}/3
                  </span>
                )}
              </span>

              {/* Active connector pulse */}
              {isCurrent && (
                <span className="ml-auto h-1.5 w-1.5 rounded-full bg-sky-500 animate-pulse" />
              )}
            </li>
          );
        })}
      </ol>

      {/* Outer loop progress */}
      {iteration > 0 && status !== "completed" && status !== "failed" && (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <p className="text-xs text-slate-500 mb-1.5">Outer loop progress</p>
          <div className="flex gap-1">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className={`h-1.5 flex-1 rounded-full ${
                  i < iteration ? "bg-sky-500" : "bg-slate-100"
                }`}
              />
            ))}
          </div>
          <p className="mt-1 text-xs text-slate-400">Iteration {iteration} of 3 max</p>
        </div>
      )}
    </section>
  );
}
