"""Pydantic contracts exchanged between roles. extra='forbid' everywhere: unknown fields are contract violations."""
from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class State(StrEnum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    PLANNED = "PLANNED"
    POLICY_CHECKED = "POLICY_CHECKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    RESOLVED = "RESOLVED"
    ROLLED_BACK = "ROLLED_BACK"
    ESCALATED = "ESCALATED"


TERMINAL = {State.RESOLVED, State.ROLLED_BACK, State.ESCALATED}
TRANSITIONS: dict[State, set[State]] = {
    State.DETECTED: {State.TRIAGED, State.RESOLVED},            # RESOLVED only when nothing is wrong
    State.TRIAGED: {State.INVESTIGATING, State.ESCALATED},
    State.INVESTIGATING: {State.PLANNED, State.ESCALATED},
    State.PLANNED: {State.POLICY_CHECKED},                       # no path around the Guardian
    State.POLICY_CHECKED: {State.APPROVED, State.REJECTED},
    State.APPROVED: {State.EXECUTING, State.RESOLVED, State.ESCALATED},  # RESOLVED/ESCALATED for abstain/escalate plans
    State.REJECTED: {State.INVESTIGATING, State.ESCALATED},     # replan goes back through investigation
    State.EXECUTING: {State.VALIDATING, State.ROLLED_BACK},
    State.VALIDATING: {State.RESOLVED, State.ROLLED_BACK},
    State.ROLLED_BACK: {State.INVESTIGATING, State.ESCALATED},
    State.RESOLVED: set(),
    State.ESCALATED: set(),
}


class Evidence(Strict):
    evidence_id: str = Field(default_factory=lambda: new_id("ev"))
    source: Literal["pipeline_run", "quality_check", "log", "profile", "lineage", "sql_versions", "tool_error"]
    subject: str
    detail: str
    severity: Literal["info", "warning", "critical"] = "info"
    data: dict[str, Any] = Field(default_factory=dict)


class Hypothesis(Strict):
    fault_class: str
    root_cause_table: str | None = None
    explanation: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ActionName(StrEnum):
    retry_task = "retry_task"
    dedupe_table = "dedupe_table"
    quarantine_rows = "quarantine_rows"
    rename_column = "rename_column"
    reload_partition = "reload_partition"
    backfill_partitions = "backfill_partitions"
    rollback_sql_version = "rollback_sql_version"
    escalate_to_human = "escalate_to_human"
    abstain = "abstain"


class PlanStep(Strict):
    action: str                     # free string on purpose: the Guardian must reject unknown actions
    params: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class Plan(Strict):
    plan_id: str = Field(default_factory=lambda: new_id("plan"))
    incident_id: str
    steps: list[PlanStep]
    preconditions: list[str] = Field(default_factory=list)
    rollback: str = "restore pre-execution sandbox snapshot"
    expected_outcome: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)
    author: str = "remediation_planner"


class RiskDecision(Strict):
    plan_id: str
    step_index: int
    action: str
    risk: Literal["none", "low", "medium", "high", "forbidden"]
    decision: Literal["allow", "require_approval", "deny"]
    reasons: list[str]
    policy_version: str


class Approval(Strict):
    approval_id: str = Field(default_factory=lambda: new_id("appr"))
    plan_id: str
    approver: str
    role: str
    approved: bool
    reason: str
    expires_at: str
    ts: str = Field(default_factory=now)


class Execution(Strict):
    execution_id: str = Field(default_factory=lambda: new_id("exec"))
    plan_id: str
    step_index: int
    action: str
    params: dict[str, Any]
    idempotency_key: str
    status: Literal["success", "failed", "skipped_duplicate", "blocked"]
    detail: str = ""
    snapshot: str | None = None
    duration_ms: float = 0


class Verification(Strict):
    passed: bool
    checks: list[dict[str, Any]]
    pipeline_status: dict[str, str]
    summary: str


class TraceEvent(Strict):
    ts: str = Field(default_factory=now)
    run_id: str
    incident_id: str
    trace_id: str
    strategy_id: str
    actor: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
