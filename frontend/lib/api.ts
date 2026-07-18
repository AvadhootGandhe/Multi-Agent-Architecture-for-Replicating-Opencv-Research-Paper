import type { RunCreateResponse, RunSnapshot } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

export async function createRun(file: File): Promise<RunCreateResponse> {
  const body = new FormData();
  body.append("paper", file);
  const response = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    body,
  });
  return readJson(response);
}

export async function fetchRun(runId: string): Promise<RunSnapshot> {
  const response = await fetch(`${API_BASE}/runs/${runId}`, { cache: "no-store" });
  return readJson(response);
}

export async function submitFeedback(runId: string, message: string): Promise<RunSnapshot> {
  const response = await fetch(`${API_BASE}/runs/${runId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  return readJson(response);
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

