"use client";

import { CheckSquare, GitMerge, Network } from "lucide-react";

import type { ImplementationPlan } from "@/types";

export function PlannerView({ plan }: { plan: ImplementationPlan | null }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex h-12 items-center justify-between gap-2 border-b border-slate-200 px-4 text-sm font-semibold text-slate-900">
        <span className="flex items-center gap-2">
          <Network size={17} />
          Planner — Implementation Roadmap
        </span>
        {plan && (
          <span className="rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-semibold text-sky-700">
            Rev. {plan.revision}
          </span>
        )}
      </div>

      <div className="p-4">
        {!plan ? (
          <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-500">
            The roadmap appears after the parser completes.
          </p>
        ) : (
          <>
            <p className="text-sm leading-6 text-slate-600">{plan.summary}</p>

            {/* Feedback being addressed */}
            {plan.addressing_feedback && plan.addressing_feedback.length > 0 && (
              <div className="mt-3 rounded-md border border-sky-200 bg-sky-50 p-3">
                <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-sky-700">
                  <GitMerge size={13} />
                  Addressing this feedback:
                </p>
                <ul className="mt-2 space-y-1">
                  {plan.addressing_feedback.map((fb, i) => (
                    <li key={i} className="text-xs text-sky-800">
                      • {fb}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Task cards */}
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {plan.tasks.map((task, index) => (
                <article
                  key={task.id}
                  className="rounded-md border border-slate-200 p-3 hover:border-slate-300 transition-colors"
                >
                  <div className="flex items-start gap-3">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-sky-100 text-sm font-semibold text-sky-700">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <h2 className="text-sm font-semibold text-slate-950">{task.title}</h2>
                      <p className="mt-1 text-xs leading-5 text-slate-600">{task.description}</p>

                      {/* Target files */}
                      {task.target_files.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {task.target_files.map((f) => (
                            <span
                              key={f}
                              className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600"
                            >
                              {f.split("/").pop()}
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Acceptance criteria */}
                      {task.acceptance_criteria.length > 0 && (
                        <ul className="mt-2 space-y-0.5">
                          {task.acceptance_criteria.map((c, i) => (
                            <li
                              key={i}
                              className="flex items-start gap-1.5 text-xs text-slate-500"
                            >
                              <CheckSquare size={11} className="mt-0.5 shrink-0 text-green-500" />
                              {c}
                            </li>
                          ))}
                        </ul>
                      )}

                      {/* Dependencies */}
                      {task.dependencies.length > 0 && (
                        <p className="mt-2 text-xs text-slate-400">
                          Depends on:{" "}
                          <span className="font-medium text-slate-500">
                            {task.dependencies.join(", ")}
                          </span>
                        </p>
                      )}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
