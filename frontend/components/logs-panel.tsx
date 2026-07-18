"use client";

import { TerminalSquare } from "lucide-react";

import type { AgentLog } from "@/types";

const AGENT_COLORS: Record<AgentLog["agent"], string> = {
  parser: "bg-violet-100 text-violet-700",
  planner: "bg-sky-100 text-sky-700",
  builder: "bg-amber-100 text-amber-700",
  tester: "bg-orange-100 text-orange-700",
  evaluator: "bg-green-100 text-green-700",
  orchestrator: "bg-slate-100 text-slate-600",
};

export function LogsPanel({ logs }: { logs: AgentLog[] }) {
  // Show newest first
  const reversed = [...logs].reverse();

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm flex flex-col">
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-slate-200 px-4">
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <TerminalSquare size={17} />
          Agent Logs
        </span>
        <span className="text-xs text-slate-400">{logs.length} events</span>
      </div>

      <div className="flex-1 overflow-auto max-h-[680px] min-h-96 p-3 space-y-2">
        {reversed.length === 0 ? (
          <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-500">
            No agent events yet.
          </p>
        ) : (
          reversed.map((log, index) => (
            <LogEntry key={`${log.timestamp}-${index}`} log={log} />
          ))
        )}
      </div>
    </section>
  );
}

function LogEntry({ log }: { log: AgentLog }) {
  const agentClass = AGENT_COLORS[log.agent] ?? "bg-slate-100 text-slate-600";
  const hasPayload = Object.keys(log.payload).length > 0;

  return (
    <div
      className={`rounded-md border p-3 text-xs ${
        log.level === "error"
          ? "border-red-200 bg-red-50"
          : log.level === "warning"
            ? "border-amber-200 bg-amber-50"
            : "border-slate-200 bg-slate-50"
      }`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className={`rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${agentClass}`}>
          {log.agent}
        </span>
        <span className="text-slate-400 tabular-nums">
          {new Date(log.timestamp).toLocaleTimeString()}
        </span>
      </div>

      {/* Message */}
      <p
        className={`leading-5 ${
          log.level === "error"
            ? "text-red-800"
            : log.level === "warning"
              ? "text-amber-800"
              : "text-slate-700"
        }`}
      >
        {log.message}
      </p>

      {/* Payload key-values */}
      {hasPayload && (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          {Object.entries(log.payload).map(([k, v]) => {
            const val = Array.isArray(v)
              ? `[${v.length} items]`
              : typeof v === "object" && v !== null
                ? JSON.stringify(v).slice(0, 60)
                : String(v);
            return (
              <span key={k} className="text-slate-500">
                <span className="font-medium text-slate-600">{k}:</span>{" "}
                <span className="font-mono">{val}</span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
