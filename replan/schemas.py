"""RePlan contract types. FROZEN after Hour Zero — see AGENTS.md.

Every type that crosses a boundary between two people lives here.
Do not add fields, rename fields, or redefine any of this elsewhere.
Changing this file requires all four owners in the same conversation.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Effect(str, Enum):
    PURE = "pure"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FROZEN = "frozen"
    DONE = "done"
    CANCELLED = "cancelled"
    INVALIDATED = "invalidated"


class Verdict(str, Enum):
    COMMIT = "commit"
    STALE = "stale"
    DUPLICATE = "duplicate"
    CANCELLED = "cancelled"
    INVALID = "invalid"


class Interruption(str, Enum):
    BACKCHANNEL = "backchannel"
    ABORT = "abort"
    POLICY = "policy"
    CLARIFY = "clarify"
    PIVOT = "pivot"
    REFINE = "refine"
    CONFIRM = "confirm"


class EventType(str, Enum):
    TASK_DISPATCH = "task_dispatch"
    CACHE_HIT = "cache_hit"
    SPEC_REFUSED = "spec_refused"
    VERDICT = "verdict"
    TASK_FREEZE = "task_freeze"
    TASK_THAW = "task_thaw"
    RECONCILE = "reconcile"
    BARGE_IN = "barge_in"
    SPEECH_ENVELOPE = "speech_envelope"
    STATE_PATCH = "state_patch"
    CHECKPOINT = "checkpoint"
    RESTORE = "restore"
    PAUSE = "pause"
    RESUME = "resume"
    USER_CONFIRMED = "user_confirmed"
    COMPENSATING = "compensating"


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

class Event(BaseModel):
    seq: int
    t: float
    state_version: int
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = ""
    hash: str = ""


class SessionState(BaseModel):
    version: int = 0
    slots: dict[str, Any] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)

    def read(self, path: str) -> Any:
        section, _, key = path.partition(".")
        return getattr(self, section, {}).get(key)

    @classmethod
    def load(cls, path: str) -> "SessionState":
        return cls.model_validate_json(Path(path).read_text())


class PlanTask(BaseModel):
    id: str
    tool: str
    arg_spec: dict[str, Any] = Field(default_factory=dict)
    after: list[str] = Field(default_factory=list)
    speculative: bool = False
    status: TaskStatus = TaskStatus.PENDING
    call_id: str | None = None
    dispatch_fp: str | None = None


class ExecutionPlan(BaseModel):
    id: str
    tasks: dict[str, PlanTask] = Field(default_factory=dict)


class ToolCall(BaseModel):
    call_id: str
    task_id: str
    tool: str
    args: dict[str, Any]
    idempotency_key: str
    dispatch_fp: str


class ToolResult(BaseModel):
    call_id: str
    task_id: str
    ok: bool
    payload: dict[str, Any] = Field(default_factory=dict)
    dispatch_fp: str
    error: str | None = None


class CommitDecision(BaseModel):
    call_id: str
    task_id: str
    verdict: Verdict
    reason: str
    t: float


class Hypothesis(BaseModel):
    kind: Interruption
    confidence: float
    changed_paths: set[str] = Field(default_factory=set)
    at: float


class Proposal(BaseModel):
    kind: str = "state_patch"
    patch: dict[str, dict[str, Any]] = Field(default_factory=dict)
    rationale: str = ""
    confidence: float = 1.0


class Checkpoint(BaseModel):
    name: str
    version: int
    t: float


class ToolSpec(BaseModel):
    name: str
    effect: Effect
    cost: float
    latency: float
    compensator: str | None = None
