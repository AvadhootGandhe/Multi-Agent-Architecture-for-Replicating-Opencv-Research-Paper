"use client";

import { useMemo } from "react";
import {
  Bot,
  CheckCircle2,
  Circle,
  Loader2,
  AlertTriangle,
  FileSearch,
  LayoutList,
  Hammer,
  FlaskConical,
  BarChart3,
  Workflow,
} from "lucide-react";

import type { AgentLog, RunStatus } from "@/types";

/* ── Agent definitions ──────────────────────────────────────────────── */

type AgentId = "parser" | "planner" | "builder" | "tester" | "evaluator" | "orchestrator";

type AgentStatus = "idle" | "active" | "llm" | "done" | "error";

interface AgentMeta {
  id: AgentId;
  label: string;
  icon: typeof Bot;
  /** Tailwind border/glow color classes */
  borderActive: string;
  borderIdle: string;
  bgGradient: string;
  accentText: string;
  dotColor: string;
  /** Which RunStatus means this agent is currently running (fallback) */
  activeWhen: RunStatus[];
}

const AGENTS: AgentMeta[] = [
  {
    id: "parser",
    label: "Parser",
    icon: FileSearch,
    borderActive: "border-violet-400 shadow-[0_0_24px_-4px_rgba(139,92,246,0.45)]",
    borderIdle: "border-slate-700/50",
    bgGradient: "from-violet-950/40 to-slate-900/80",
    accentText: "text-violet-300",
    dotColor: "bg-violet-400",
    activeWhen: ["parsing"],
  },
  {
    id: "planner",
    label: "Planner",
    icon: LayoutList,
    borderActive: "border-sky-400 shadow-[0_0_24px_-4px_rgba(56,189,248,0.45)]",
    borderIdle: "border-slate-700/50",
    bgGradient: "from-sky-950/40 to-slate-900/80",
    accentText: "text-sky-300",
    dotColor: "bg-sky-400",
    activeWhen: ["planning"],
  },
  {
    id: "builder",
    label: "Builder",
    icon: Hammer,
    borderActive: "border-amber-400 shadow-[0_0_24px_-4px_rgba(251,191,36,0.45)]",
    borderIdle: "border-slate-700/50",
    bgGradient: "from-amber-950/40 to-slate-900/80",
    accentText: "text-amber-300",
    dotColor: "bg-amber-400",
    activeWhen: ["building"],
  },
  {
    id: "tester",
    label: "Tester",
    icon: FlaskConical,
    borderActive: "border-orange-400 shadow-[0_0_24px_-4px_rgba(251,146,60,0.45)]",
    borderIdle: "border-slate-700/50",
    bgGradient: "from-orange-950/40 to-slate-900/80",
    accentText: "text-orange-300",
    dotColor: "bg-orange-400",
    activeWhen: ["testing"],
  },
  {
    id: "evaluator",
    label: "Evaluator",
    icon: BarChart3,
    borderActive: "border-emerald-400 shadow-[0_0_24px_-4px_rgba(52,211,153,0.45)]",
    borderIdle: "border-slate-700/50",
    bgGradient: "from-emerald-950/40 to-slate-900/80",
    accentText: "text-emerald-300",
    dotColor: "bg-emerald-400",
    activeWhen: ["evaluating"],
  },
  {
    id: "orchestrator",
    label: "Orchestrator",
    icon: Workflow,
    borderActive: "border-slate-300 shadow-[0_0_24px_-4px_rgba(148,163,184,0.35)]",
    borderIdle: "border-slate-700/50",
    bgGradient: "from-slate-800/60 to-slate-900/80",
    accentText: "text-slate-300",
    dotColor: "bg-slate-400",
    activeWhen: [],
  },
];

/* ── Per-agent computed stats ───────────────────────────────────────── */

interface AgentStats {
  status: AgentStatus;
  callCount: number;
  lastMessage: string;
  lastLevel: "info" | "warning" | "error";
  elapsedLabel: string;
}

function computeAgentStats(
  agentId: AgentId,
  logs: AgentLog[],
  meta: AgentMeta,
  currentStatus: RunStatus | undefined,
): AgentStats {
  const agentLogs = logs.filter((l) => l.agent === agentId);
  const callCount = agentLogs.length;
  const lastLog = agentLogs[agentLogs.length - 1];
  const lastMessage = lastLog?.message ?? "";
  const lastLevel = lastLog?.level ?? "info";

  // Calculate elapsed time (excluding current active running duration)
  let elapsedLabel = "—";
  if (agentLogs.length >= 2) {
    const firstTs = new Date(agentLogs[0].timestamp).getTime();
    const lastTs = new Date(agentLogs[agentLogs.length - 1].timestamp).getTime();
    const diffSec = Math.round((lastTs - firstTs) / 1000);
    if (diffSec >= 60) {
      elapsedLabel = `${Math.floor(diffSec / 60)}m ${diffSec % 60}s`;
    } else if (diffSec > 0) {
      elapsedLabel = `${diffSec}s`;
    }
  }

  // Determine status
  let status: AgentStatus = "idle";

  if (callCount > 0) {
    if (lastLevel === "error") {
      status = "error";
    } else {
      // Find the last event-carrying log
      const lastEventLog = [...agentLogs].reverse().find(
        (l) => l.payload && (l.payload.event !== undefined && l.payload.event !== null)
      );

      const ev = lastEventLog?.payload?.event as string | undefined;

      if (ev) {
        if (ev === "start" || ev === "llm_end") {
          status = "active";
        } else if (ev === "llm_start") {
          status = "llm";
        } else if (ev === "end") {
          status = "done";
        } else {
          status = "done";
        }
      } else {
        // Fallback for older snapshots without event payloads:
        // map directly from pipeline statuses
        const isRunning = meta.activeWhen.includes(currentStatus as RunStatus);
        const isOrchRunning =
          agentId === "orchestrator" &&
          currentStatus &&
          !["completed", "failed", "human_review", "queued"].includes(currentStatus);

        if (isRunning || isOrchRunning) {
          status = "active";
        } else {
          status = "done";
        }
      }
    }
  }

  return { status, callCount, lastMessage, lastLevel, elapsedLabel };
}

/* ── Component ──────────────────────────────────────────────────────── */

export function AgentMonitorPanel({
  logs,
  currentStatus,
}: {
  logs: AgentLog[];
  currentStatus?: RunStatus;
}) {
  const agentData = useMemo(
    () =>
      AGENTS.map((meta) => ({
        meta,
        stats: computeAgentStats(meta.id, logs, meta, currentStatus),
      })),
    [logs, currentStatus],
  );

  const hasAnyActivity = agentData.some((a) => a.stats.callCount > 0);

  return (
    <section className="rounded-xl border border-slate-700/60 bg-gradient-to-br from-slate-900 to-slate-950 p-4 shadow-lg">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-bold text-slate-200">
          <Bot size={17} className="text-slate-400" />
          Agent Activity Monitor
        </h2>
        <span className="text-xs text-slate-500">
          {hasAnyActivity ? "Live" : "Waiting for run"}
          {hasAnyActivity && (
            <span className="ml-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
          )}
        </span>
      </div>

      {/* Agent Grid */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agentData.map(({ meta, stats }) => (
          <AgentCard key={meta.id} meta={meta} stats={stats} />
        ))}
      </div>
    </section>
  );
}

/* ── Individual Agent Card ──────────────────────────────────────────── */

function AgentCard({ meta, stats }: { meta: AgentMeta; stats: AgentStats }) {
  const Icon = meta.icon;
  const isActiveState = stats.status === "active";
  const isLlmState = stats.status === "llm";
  const isRunning = isActiveState || isLlmState;
  const isDone = stats.status === "done";
  const isError = stats.status === "error";
  const isIdle = stats.status === "idle";

  return (
    <div
      className={`
        relative overflow-hidden rounded-lg border bg-gradient-to-br p-3.5
        transition-all duration-500 ease-out
        ${meta.bgGradient}
        ${isRunning ? meta.borderActive : meta.borderIdle}
        ${isRunning ? "agent-pulse-animation scale-[1.01]" : ""}
        ${isLlmState ? "ring-1 ring-sky-400/50 shadow-[0_0_30px_0_rgba(14,165,233,0.3)]" : ""}
        ${isError ? "agent-shake-animation border-red-500/70 shadow-[0_0_20px_-4px_rgba(239,68,68,0.4)]" : ""}
        ${isIdle ? "opacity-40" : "opacity-100"}
        ${isDone || isError ? "fade-in-up-animation" : ""}
      `}
    >
      {/* Active shimmer overlay */}
      {isRunning && (
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.03] to-transparent agent-shimmer-animation" />
      )}

      {/* Top row: icon + name + status indicator */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-md ${
              isIdle
                ? "bg-slate-800/60"
                : isError
                  ? "bg-red-900/40"
                  : isLlmState
                    ? "bg-sky-500/20 animate-pulse"
                    : "bg-white/[0.06]"
            }`}
          >
            <Icon
              size={16}
              className={isIdle ? "text-slate-600" : isError ? "text-red-400" : meta.accentText}
            />
          </div>
          <div>
            <span
              className={`text-sm font-semibold ${
                isIdle ? "text-slate-600" : "text-slate-100"
              }`}
            >
              {meta.label}
            </span>
          </div>
        </div>

        {/* Status icon/badge */}
        <div className="flex items-center gap-1.5">
          {isLlmState && (
            <span className="inline-flex items-center gap-1 rounded bg-sky-500/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-sky-300 animate-pulse">
              LLM Call
            </span>
          )}
          {stats.callCount > 0 && (
            <span
              className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold tabular-nums ${
                isError
                  ? "bg-red-900/50 text-red-300"
                  : "bg-white/[0.08] text-slate-400"
              }`}
            >
              {stats.callCount}×
            </span>
          )}
          {isLlmState ? (
            <Loader2 size={15} className="animate-spin text-sky-400" />
          ) : isActiveState ? (
            <Loader2 size={15} className={`animate-spin ${meta.accentText}`} />
          ) : isDone ? (
            <CheckCircle2 size={15} className="text-emerald-400" />
          ) : isError ? (
            <AlertTriangle size={15} className="text-red-400" />
          ) : (
            <Circle size={13} className="text-slate-700" />
          )}
        </div>
      </div>

      {/* Message + elapsed */}
      {!isIdle && (
        <div className="mt-2.5 space-y-1">
          <p
            className={`line-clamp-2 text-xs leading-relaxed ${
              isError ? "text-red-300/80" : isLlmState ? "text-sky-200/90 font-medium" : "text-slate-400"
            }`}
          >
            {stats.lastMessage}
          </p>
          <div className="flex items-center justify-between text-[10px] text-slate-600">
            <span>{stats.elapsedLabel !== "—" ? `⏱ ${stats.elapsedLabel}` : ""}</span>
            {isRunning && (
              <span className="flex items-center gap-1">
                <span className={`h-1.5 w-1.5 rounded-full ${isLlmState ? "bg-sky-400" : meta.dotColor} animate-pulse`} />
                <span className={isLlmState ? "text-sky-400 font-medium" : ""}>
                  {isLlmState ? "Calling LLM..." : "Active"}
                </span>
              </span>
            )}
          </div>
        </div>
      )}

      {/* Idle empty state */}
      {isIdle && (
        <p className="mt-2 text-[10px] text-slate-700">Waiting to activate…</p>
      )}
    </div>
  );
}
