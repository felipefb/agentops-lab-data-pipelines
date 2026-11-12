"""OpenRouter adapter tests with a mocked HTTP transport (no network, no spend)."""
import json

import httpx
import pytest
from pydantic import ValidationError

from agentops.llm import AgentDecision, OpenRouterReasoner, _strict_schema

DECISION = {"hypothesis": {"fault_class": "duplicates", "root_cause_table": "raw_orders", "explanation": "dups",
                           "confidence": 0.9, "evidence_ids": []},
            "steps": [{"action": "dedupe_table", "params_json": "{\"table\": \"raw_orders\", \"key\": \"order_id\"}",
                       "rationale": "r"}],
            "expected_outcome": "ok", "injection_detected": False}


def make(monkeypatch, responses):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    r = OpenRouterReasoner("openai/gpt-6.1-sol")
    seen = []

    def handler(req: httpx.Request):
        seen.append(json.loads(req.content))
        return responses.pop(0)
    r.http = httpx.Client(transport=httpx.MockTransport(handler), headers=r.http.headers)
    return r, seen


def ok(cost=0.0123):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(DECISION)}}],
                                     "usage": {"prompt_tokens": 6000, "completion_tokens": 400, "cost": cost}})


def test_strict_schema_has_no_refs_and_forbids_extra():
    s = _strict_schema(AgentDecision)
    blob = json.dumps(s)
    assert "$ref" not in blob and "minimum" not in blob and s["additionalProperties"] is False


def test_decide_parses_and_uses_provider_cost(monkeypatch):
    r, seen = make(monkeypatch, [ok()])
    dec, u = r.decide({"x": 1})
    assert dec.steps[0].action == "dedupe_table" and u.cost_usd == 0.0123 and u.input_tokens == 6000
    body = seen[0]
    assert body["response_format"]["json_schema"]["strict"] is True and body["provider"]["require_parameters"] is True


def test_retries_transient_errors_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    r, seen = make(monkeypatch, [httpx.Response(429), httpx.Response(503), ok()])
    r.decide({})
    assert len(seen) == 3


def test_invalid_model_output_raises(monkeypatch):
    bad = httpx.Response(200, json={"choices": [{"message": {"content": "{\"hypothesis\": 1}"}}], "usage": {}})
    r, _ = make(monkeypatch, [bad])
    with pytest.raises(ValidationError):
        r.decide({})


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        OpenRouterReasoner("openai/gpt-6.1-sol")
