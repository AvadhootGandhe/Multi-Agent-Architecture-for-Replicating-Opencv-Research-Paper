"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Download,
  FileUp,
  GitBranch,
  Play,
  RefreshCw,
  Send,
} from "lucide-react";

import { AgentMonitorPanel } from "@/components/agent-monitor";
import { KnowledgePanel } from "@/components/knowledge-panel";
import { LogsPanel } from "@/components/logs-panel";
import { PlannerView } from "@/components/planner-view";
import { ProgressRail } from "@/components/progress-rail";
import { ReviewPanel } from "@/components/review-panel";
import { createRun, fetchRun, submitFeedback } from "@/lib/api";
import type { RunSnapshot } from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

const ACTIVE_STATUSES = new Set(["queued", "parsing", "planning", "building", "testing", "evaluating"]);

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState<string | null>(null);
  const logsBottomRef = useRef<HTMLDivElement>(null);

  const runId = snapshot?.run_id;
  const status = snapshot?.status;
  const isActive = status ? ACTIVE_STATUSES.has(status) : false;
  const isComplete = status === "completed";
  const isFailed = status === "failed";
  const isHumanReview = status === "human_review";

  // ── Auto-poll while active ──────────────────────────────────────────
  useEffect(() => {
    if (!runId || !isActive) return;
    const id = window.setInterval(async () => {
      try {
        setSnapshot(await fetchRun(runId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to refresh run.");
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [runId, isActive]);

  const statusLabel = useMemo(
    () => snapshot?.status.replace(/_/g, " ") ?? "waiting for upload",
    [snapshot],
  );

  // ── Handlers ───────────────────────────────────────────────────────
  async function onStart() {
    if (!file) return;
    setIsUploading(true);
    setError(null);
    try {
      const created = await createRun(file);
      setSnapshot(await fetchRun(created.run_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start replication.");
    } finally {
      setIsUploading(false);
    }
  }

  async function onRefresh() {
    if (!runId) return;
    try {
      setSnapshot(await fetchRun(runId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
    }
  }

  async function onFeedback() {
    if (!runId || !feedback.trim()) return;
    setError(null);
    try {
      setSnapshot(await submitFeedback(runId, feedback.trim()));
      setFeedback("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feedback submission failed.");
    }
  }

  const state = snapshot?.state;
  const downloadHref = runId ? `${API_BASE}/runs/${runId}/download` : "#";

  return (
    <main className="min-h-screen bg-slate-50">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="border-b border-slate-200 bg-white sticky top-0 z-10 shadow-sm">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-5 py-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-950">
              Research Paper Replicator
            </h1>
            <p className="mt-0.5 text-xs text-slate-500">
              Multi-agent CV paper → PyTorch implementation scaffold (Qwen3-8B)
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* Status badge */}
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold capitalize ${
                isComplete
                  ? "bg-green-100 text-green-700"
                  : isFailed
                    ? "bg-red-100 text-red-700"
                    : isHumanReview
                      ? "bg-amber-100 text-amber-700"
                      : isActive
                        ? "bg-sky-100 text-sky-700"
                        : "bg-slate-100 text-slate-600"
              }`}
            >
              <Activity size={13} />
              {statusLabel}
            </span>

            <button
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
              onClick={onRefresh}
              disabled={!runId}
            >
              <RefreshCw size={13} />
              Refresh
            </button>
          </div>
        </div>
      </header>

      {/* ── Success Banner ──────────────────────────────────────────── */}
      {isComplete && (
        <div className="bg-green-600 text-white px-5 py-3">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
            <span className="flex items-center gap-2 font-semibold">
              <CheckCircle2 size={18} />
              Paper Successfully Replicated! Score:{" "}
              {state?.evaluation?.overall_match?.toFixed(1)}%
            </span>
            <a
              href={downloadHref}
              className="flex items-center gap-1.5 rounded-md bg-white px-3 py-1.5 text-sm font-semibold text-green-700 hover:bg-green-50"
            >
              <Download size={15} />
              Download Project
            </a>
          </div>
        </div>
      )}

      {/* ── Human Review Banner ─────────────────────────────────────── */}
      {isHumanReview && (
        <div className="bg-amber-50 border-b border-amber-200 px-5 py-3">
          <div className="mx-auto max-w-7xl flex items-center gap-2 text-sm text-amber-800">
            <AlertCircle size={16} className="shrink-0" />
            Max iterations reached. Score:{" "}
            <strong>{state?.evaluation?.overall_match?.toFixed(1) ?? "—"}%</strong>.
            Use the Human Feedback box to guide the planner on what to fix.
          </div>
        </div>
      )}

      {/* ── Failed Banner ───────────────────────────────────────────── */}
      {isFailed && (
        <div className="bg-red-50 border-b border-red-200 px-5 py-3">
          <div className="mx-auto max-w-7xl flex items-center gap-2 text-sm text-red-800">
            <AlertCircle size={16} className="shrink-0" />
            Replication failed. Check agent logs for details.
          </div>
        </div>
      )}

      {/* ── Layout ─────────────────────────────────────────────────── */}
      <section className="mx-auto grid max-w-7xl gap-4 px-5 py-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        {/* ── Left sidebar ────────────────────────────────────────── */}
        <aside className="space-y-4">
          {/* Upload */}
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <FileUp size={16} />
              Upload CV Paper (PDF)
            </p>
            <label className="mt-3 flex min-h-28 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 text-center hover:border-sky-400 hover:bg-sky-50 transition-colors">
              <input
                className="sr-only"
                type="file"
                accept="application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <FileUp size={20} className={file ? "text-sky-600" : "text-slate-300"} />
              <span className="mt-2 text-xs font-medium text-slate-700">
                {file?.name ?? "Click to choose PDF"}
              </span>
              <span className="mt-0.5 text-xs text-slate-400">
                Computer vision papers only
              </span>
            </label>
            <button
              className="mt-3 flex h-9 w-full items-center justify-center gap-2 rounded-md bg-sky-600 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-300 transition-colors"
              onClick={onStart}
              disabled={!file || isUploading || isActive}
            >
              <Play size={15} />
              {isUploading ? "Starting…" : "Start Replication"}
            </button>
            {error && (
              <p className="mt-2 flex items-start gap-1 text-xs text-red-600">
                <AlertCircle size={12} className="mt-0.5 shrink-0" />
                {error}
              </p>
            )}
          </div>

          {/* Progress rail */}
          <ProgressRail
            status={snapshot?.status}
            iteration={state?.iteration ?? 0}
            buildAttempt={state?.build_attempt}
          />

          {/* Human Feedback */}
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Send size={15} />
              Human Feedback → Planner
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Describe what's wrong or missing. Sent directly to the planner agent.
            </p>
            <textarea
              className="mt-3 min-h-24 w-full resize-none rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
              placeholder="e.g. The attention module is missing a skip connection…"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
            />
            <button
              className="mt-2 flex h-9 w-full items-center justify-center gap-2 rounded-md border border-slate-300 bg-white text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40 transition-colors"
              onClick={onFeedback}
              disabled={!runId || !feedback.trim() || isActive}
            >
              <GitBranch size={14} />
              Route to Planner
            </button>
            {state?.human_feedback && state.human_feedback.length > 0 && (
              <div className="mt-3 space-y-1">
                <p className="text-xs text-slate-400">Previous feedback:</p>
                {state.human_feedback.slice(-3).map((fb, i) => (
                  <p key={i} className="rounded bg-slate-50 px-2 py-1 text-xs text-slate-600">
                    {fb}
                  </p>
                ))}
              </div>
            )}
          </div>

          {/* Download */}
          <a
            href={downloadHref}
            className={`flex h-9 w-full items-center justify-center gap-2 rounded-md text-sm font-semibold transition-colors ${
              runId
                ? "bg-slate-900 text-white hover:bg-slate-700"
                : "pointer-events-none bg-slate-200 text-slate-400"
            }`}
          >
            <Download size={15} />
            Download Generated Project
          </a>

          {/* Run metadata */}
          {snapshot && (
            <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500 space-y-1">
              <div className="flex justify-between">
                <span>Run ID</span>
                <span className="font-mono truncate max-w-32">{snapshot.run_id.slice(0, 12)}…</span>
              </div>
              <div className="flex justify-between">
                <span>File</span>
                <span className="truncate max-w-32">{snapshot.filename}</span>
              </div>
              <div className="flex justify-between">
                <span>Updated</span>
                <span>{new Date(snapshot.updated_at).toLocaleTimeString()}</span>
              </div>
            </div>
          )}
        </aside>

        {/* ── Main content ────────────────────────────────────────── */}
        <div className="space-y-4 min-w-0">
          {/* Knowledge panel — parsed paper info */}
          <KnowledgePanel knowledge={state?.knowledge ?? null} />

          {/* Real-time agent activity monitor */}
          <AgentMonitorPanel
            logs={state?.logs ?? []}
            currentStatus={snapshot?.status}
          />

          {/* Planner + Review row */}
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
            <PlannerView plan={state?.plan ?? null} />
            <ReviewPanel
              evaluation={state?.evaluation ?? null}
              diagnostics={state?.diagnostics ?? null}
            />
          </div>

          {/* Logs */}
          <LogsPanel logs={state?.logs ?? []} />

          {/* Evaluation feedback accumulation */}
          {state?.evaluation_feedback && state.evaluation_feedback.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
                Accumulated Feedback for Planner
              </p>
              <ul className="space-y-1">
                {state.evaluation_feedback.map((fb, i) => (
                  <li key={i} className="rounded bg-slate-50 px-2 py-1.5 text-xs text-slate-700">
                    {fb}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      <div ref={logsBottomRef} />
    </main>
  );
}
