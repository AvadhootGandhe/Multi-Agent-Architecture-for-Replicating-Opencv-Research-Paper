export type RunStatus =
  | "queued"
  | "parsing"
  | "planning"
  | "building"
  | "testing"
  | "evaluating"
  | "human_review"
  | "completed"
  | "failed";

export type AgentLog = {
  timestamp: string;
  agent: "parser" | "planner" | "builder" | "tester" | "evaluator" | "orchestrator";
  level: "info" | "warning" | "error";
  message: string;
  payload: Record<string, unknown>;
};

export type PlanTask = {
  id: string;
  title: string;
  description: string;
  dependencies: string[];
  target_files: string[];
  acceptance_criteria: string[];
};

export type ImplementationPlan = {
  summary: string;
  tasks: PlanTask[];
  dependency_graph: Record<string, string[]>;
  revision: number;
  addressing_feedback: string[];
};

export type TestDiagnostics = {
  passed: boolean;
  checks: string[];
  errors: string[];
  file_errors: Record<string, string[]>;
};

export type EvaluationReport = {
  overall_match: number;
  missing: string[];
  extra: string[];
  recommendations: string[];
  complete: boolean;
  planner_feedback: string[];
};

export type PaperMetadata = {
  title: string;
  authors: string[];
  abstract: string;
  source_filename: string;
  page_count: number;
};

export type PaperKnowledge = {
  metadata: PaperMetadata;
  problem_statement: string;
  contributions: string[];
  architecture: string[];
  backbone: string | null;
  loss_functions: string[];
  preprocessing: string[];
  postprocessing: string[];
  external_libraries: string[];
  hyperparameters: Record<string, string>;
  implementation_notes: string[];
  raw_text?: string;
};

export type KnowledgeBundle = {
  paper: PaperKnowledge;
  artifacts: Record<string, unknown>;
  version: number;
};

export type ReplicationState = {
  run_id: string;
  status: RunStatus;
  iteration: number;
  build_attempt: number;
  knowledge: KnowledgeBundle | null;
  plan: ImplementationPlan | null;
  build: { project_root: string; artifacts: { path: string; kind: string; description: string }[]; notes: string[] } | null;
  diagnostics: TestDiagnostics | null;
  evaluation: EvaluationReport | null;
  logs: AgentLog[];
  human_feedback: string[];
  evaluation_feedback: string[];
  build_errors: string[];
};

export type RunSnapshot = {
  run_id: string;
  filename: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  state: ReplicationState;
};

export type RunCreateResponse = {
  run_id: string;
  status: RunStatus;
  detail: string;
};
