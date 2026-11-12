"""Meridian Support Assistant app."""
from __future__ import annotations
import argparse
import hashlib
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
for _p in (HERE, HERE.parents[1]):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from a4_agent import handle as agent_handle
from a6_evals import Tracer
from a7_audit import AuditLog
from a7_guard import authorize, redact_pii
from harness import KIT_ROOT, faults
from harness.deps import make_deps
from harness.types import AgentResult


class CapstoneApp:
    def __init__(self, deps=None, audit_path=None, trace_path=None):
        self.deps = deps or make_deps()
        self.audit_path = pathlib.Path(audit_path) if audit_path else KIT_ROOT / "audit" / "audit.jsonl"
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.trace_path = pathlib.Path(trace_path) if trace_path else KIT_ROOT / "traces" / "app_trace.jsonl"
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(self.audit_path)

    def handle(self, request: str, role: str = "support_agent"):
        self.deps.user_role = role
        request_hash = hashlib.sha256(request.encode("utf-8")).hexdigest()
        request_length = len(request)
        if faults.is_active("tool_outage"):
            result = AgentResult(
                intent="unknown",
                answer="This request is currently degraded: the Meridian tool service is unavailable, so a human colleague must take over.",
                tools_used=[],
                sources=[],
                needs_human=True,
                confidence=0.2,
            )
            tracer = Tracer()
            with tracer.span("agent.run", user=role) as s:
                with tracer.span("auth.check"):
                    s.set("status", "degraded")
                with tracer.span("tool.fail"):
                    s.set("error", "tool_outage")
                with tracer.span("handoff"):
                    s.set("outcome", "human_review")
            tracer.to_jsonl(self.trace_path)
            self.audit.append(
                tracer.trace_id,
                role,
                "tool_outage",
                {"request_hash": request_hash, "request_length": request_length, "role": role},
                [],
                "degraded",
            )
            return result

        tracer = Tracer()
        with tracer.span("agent.run", user=role) as root:
            with tracer.span("auth.check") as s:
                s.set("role", role)
                self.deps.user_role = role
            with tracer.span("retrieve") as s:
                s.set("input_hash", request_hash)
                if hasattr(self.deps, "retriever"):
                    self.deps.retriever(request, 5)
            with tracer.span("tool.execute") as s:
                s.set("input_hash", request_hash)
                raw = agent_handle(request, self.deps)
                if isinstance(raw, dict):
                    result = AgentResult.model_validate(raw)
                else:
                    result = raw
                result.answer = redact_pii(result.answer)
                s.set("result_intent", result.intent)
                s.set("needs_human", result.needs_human)
            with tracer.span("answer") as s:
                s.set("outcome", result.intent)
                s.set("confidence", result.confidence)
        tracer.to_jsonl(self.trace_path)
        self.audit.append(
            tracer.trace_id,
            role,
            "agent.handle",
            {"request_hash": request_hash, "request_length": request_length, "role": role},
            list(result.sources),
            result.intent,
        )
        return result


def build_app(deps=None, audit_path=None, trace_path=None):
    return CapstoneApp(deps=deps, audit_path=audit_path, trace_path=trace_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meridian Support Assistant")
    parser.add_argument("--demo", action="store_true", help="Run the offline demo scenario")
    args = parser.parse_args()
    if not args.demo:
        parser.print_help()
        raise SystemExit(0)
    app = build_app()
    prompts = [
        "What is the status of ACC-1001?",
        "How much is an international wire fee?",
        "Who must approve a $30,000 wire initiated at the Harbor Street branch?",
        "Please escalate: fraud suspected on ACC-1002",
    ]
    for prompt in prompts:
        result = app.handle(prompt)
        print(f"Q: {prompt}\nA: {result.answer}\n")
    raise SystemExit(0)
