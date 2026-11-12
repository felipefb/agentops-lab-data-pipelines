"""Risk & Policy Guardian: default-deny, schema validation, RBAC on approvals, expiry."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml
from pydantic import ValidationError

from .actions import SCHEMAS
from .contracts import Approval, Plan, RiskDecision

POLICY_PATH = Path(__file__).resolve().parent.parent / "policies" / "policy.yaml"


def load_policy(path: Path = POLICY_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class Guardian:
    def __init__(self, strategy: str, policy: dict | None = None, public_demo: bool = False):
        self.policy = policy or load_policy()
        self.strategy = strategy
        self.public_demo = public_demo

    def check(self, plan: Plan) -> list[RiskDecision]:
        pol, out = self.policy, []
        if len(plan.steps) > pol["limits"]["max_plan_steps"]:
            return [RiskDecision(plan_id=plan.plan_id, step_index=-1, action="<plan>", risk="forbidden", decision="deny",
                                 reasons=["plan exceeds max_plan_steps"], policy_version=pol["version"])]
        for i, s in enumerate(plan.steps):
            reasons: list[str] = []
            if s.action in pol["forbidden_actions"]:
                risk, decision = "forbidden", "deny"
                reasons.append(f"action '{s.action}' is explicitly forbidden")
            elif s.action not in pol["risk"] or s.action not in SCHEMAS:
                risk, decision = "forbidden", "deny"
                reasons.append(f"action '{s.action}' is not in the allowlist (default-deny)")
            else:
                try:
                    SCHEMAS[s.action].model_validate(s.params)
                    risk = pol["risk"][s.action]
                    decision = pol["strategies"][self.strategy][risk]
                    if self.public_demo and risk != "none" and pol["public_demo_mode"]["force_approval"]:
                        decision = "require_approval"
                    reasons.append(f"risk={risk} under strategy={self.strategy}")
                except ValidationError as e:
                    risk, decision = "forbidden", "deny"
                    reasons.append(f"params violate schema: {e.errors()[0]['msg']}")
            out.append(RiskDecision(plan_id=plan.plan_id, step_index=i, action=s.action, risk=risk,
                                    decision=decision, reasons=reasons, policy_version=pol["version"]))
        return out

    def validate_approval(self, approval: Approval | None, plan: Plan) -> tuple[bool, str]:
        if approval is None:
            return False, "no approval"
        if approval.plan_id != plan.plan_id:
            return False, "approval is for a different plan"
        if approval.role != self.policy["approval"]["required_role"]:
            return False, f"approver role '{approval.role}' not authorized"
        if dt.datetime.fromisoformat(approval.expires_at) < dt.datetime.now(dt.UTC):
            return False, "approval expired"
        if not approval.approved:
            return False, f"approval denied: {approval.reason}"
        return True, "valid approval"
