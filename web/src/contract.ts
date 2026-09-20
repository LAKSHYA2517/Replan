// RePlan contract types. FROZEN after Hour Zero — see AGENTS.md.
// Must mirror replan/schemas.py exactly. Field names match the Python.

export enum Effect {
  PURE = "pure",
  REVERSIBLE = "reversible",
  IRREVERSIBLE = "irreversible",
}

export enum TaskStatus {
  PENDING = "pending",
  RUNNING = "running",
  FROZEN = "frozen",
  DONE = "done",
  CANCELLED = "cancelled",
  INVALIDATED = "invalidated",
}

export enum Verdict {
  COMMIT = "commit",
  STALE = "stale",
  DUPLICATE = "duplicate",
  CANCELLED = "cancelled",
  INVALID = "invalid",
}

export enum Interruption {
  BACKCHANNEL = "backchannel",
  ABORT = "abort",
  POLICY = "policy",
  CLARIFY = "clarify",
  PIVOT = "pivot",
  REFINE = "refine",
  CONFIRM = "confirm",
}

export enum EventType {
  TASK_DISPATCH = "task_dispatch",
  CACHE_HIT = "cache_hit",
  SPEC_REFUSED = "spec_refused",
  VERDICT = "verdict",
  TASK_FREEZE = "task_freeze",
  TASK_THAW = "task_thaw",
  RECONCILE = "reconcile",
  BARGE_IN = "barge_in",
  SPEECH_ENVELOPE = "speech_envelope",
  STATE_PATCH = "state_patch",
  CHECKPOINT = "checkpoint",
  RESTORE = "restore",
  PAUSE = "pause",
  RESUME = "resume",
  USER_CONFIRMED = "user_confirmed",
  COMPENSATING = "compensating",
}

export interface Event {
  seq: number;
  t: number;
  state_version: number;
  type: EventType;
  payload: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface SessionState {
  version: number;
  slots: Record<string, unknown>;
  constraints: Record<string, unknown>;
  policy: Record<string, unknown>;
}

export interface PlanTask {
  id: string;
  tool: string;
  arg_spec: Record<string, unknown>;
  after: string[];
  speculative: boolean;
  status: TaskStatus;
  call_id: string | null;
  dispatch_fp: string | null;
}

export interface ExecutionPlan {
  id: string;
  tasks: Record<string, PlanTask>;
}

export interface ToolCall {
  call_id: string;
  task_id: string;
  tool: string;
  args: Record<string, unknown>;
  idempotency_key: string;
  dispatch_fp: string;
}

export interface ToolResult {
  call_id: string;
  task_id: string;
  ok: boolean;
  payload: Record<string, unknown>;
  dispatch_fp: string;
  error: string | null;
}

export interface CommitDecision {
  call_id: string;
  task_id: string;
  verdict: Verdict;
  reason: string;
  t: number;
}

export interface Hypothesis {
  kind: Interruption;
  confidence: number;
  changed_paths: string[];
  at: number;
}

export interface Proposal {
  kind: string;
  patch: Record<string, Record<string, unknown>>;
  rationale: string;
  confidence: number;
}

export interface Checkpoint {
  name: string;
  version: number;
  t: number;
}
