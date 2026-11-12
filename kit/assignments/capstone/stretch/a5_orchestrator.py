"""Offline router, specialist flows, and human approval orchestration."""
from __future__ import annotations

import re
import uuid

from a4_tools import escalate_ticket, search_policy
from harness.types import ApprovalDecision, ApprovalRequest, RunResult


class Orchestrator:
    def __init__(self, deps, approver=None):
        self.deps = deps
        self.approver = approver
        self._results = {}
        self._pending = {}

    @staticmethod
    def _copy(result):
        return RunResult.model_validate(result.model_dump())

    @staticmethod
    def _route(request):
        text = request.lower()
        if any(word in text for word in ("fraud", "escalate", "complaint", "complain")):
            return "escalation"
        if re.search(r"\b(transfer|send|move)\b", text):
            return "transaction"
        if any(word in text for word in ("policy", "fee", "wire", "account", "branch", "approve", "approval")):
            return "retrieval"
        return "unknown"

    @staticmethod
    def _parse_transfer(request):
        account = re.search(r"\bACC-\d{4}\b", request, re.I)
        beneficiary = re.search(r"\bBEN-\d+\b", request, re.I)
        amount = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", request)
        if not account or not beneficiary or not amount:
            return None
        return account.group(0).upper(), beneficiary.group(0).upper(), float(amount.group(1).replace(",", ""))

    def run(self, request: str, request_id: str, user_role: str = "support_agent") -> RunResult:
        if request_id in self._results:
            return self._copy(self._results[request_id])

        route = self._route(request)
        steps = [f"route:{route}"]
        if route == "retrieval":
            try:
                hits = search_policy(self.deps.retriever, request, k=4)
            except Exception as exc:
                result = RunResult(route=route, status="failed", answer=f"Policy retrieval failed: {type(exc).__name__}.", steps=steps + ["retrieval:failed"])
            else:
                sources = list(dict.fromkeys(hit["doc_id"] for hit in hits if hit.get("doc_id")))
                answer = "I found policy material in: " + ", ".join(sources) if sources else "I could not find relevant policy material."
                result = RunResult(route=route, status="completed", answer=answer, steps=steps + [f"retrieval:hits:{len(hits)}"])
            self._results[request_id] = result
            return self._copy(result)

        if route == "escalation":
            account = re.search(r"\bACC-\d{4}\b", request, re.I)
            if not account:
                result = RunResult(route=route, status="failed", answer="An account ID is required for escalation.", steps=steps + ["escalation:invalid"])
            else:
                try:
                    ticket = escalate_ticket(
                        self.deps.tickets,
                        account.group(0).upper(),
                        request[:300],
                        "P1" if "fraud" in request.lower() else "P3",
                    )
                except Exception as exc:
                    result = RunResult(route=route, status="failed", answer=f"Escalation failed: {type(exc).__name__}.", steps=steps + ["escalation:failed"])
                else:
                    result = RunResult(route=route, status="completed", answer=f"Escalation ticket {ticket.ticket_id} is ready for human review.", steps=steps + ["escalation:created"])
            self._results[request_id] = result
            return self._copy(result)

        if route != "transaction":
            result = RunResult(route=route, status="failed", answer="I could not classify this request.", steps=steps + ["route:unsupported"])
            self._results[request_id] = result
            return self._copy(result)

        if user_role != "payments_agent":
            result = RunResult(route=route, status="denied", answer="Only a payments agent may request a transfer.", steps=steps + ["authorize:denied"])
            self._results[request_id] = result
            return self._copy(result)
        steps.append("authorize:ok")

        parsed = self._parse_transfer(request)
        if parsed is None:
            result = RunResult(route=route, status="failed", answer="Transfer requires an account, beneficiary, and amount.", steps=steps + ["transfer:invalid"])
            self._results[request_id] = result
            return self._copy(result)
        account, beneficiary, amount = parsed
        try:
            known = beneficiary in self.deps.ledger.known_beneficiaries(account)
        except (KeyError, ValueError) as exc:
            result = RunResult(route=route, status="failed", answer=f"Transfer account is invalid: {type(exc).__name__}.", steps=steps + ["account:invalid"])
            self._results[request_id] = result
            return self._copy(result)

        if amount > 1000 or not known:
            approval = ApprovalRequest(
                approval_id=f"APR-{uuid.uuid4().hex}",
                request_id=request_id,
                from_account=account,
                beneficiary=beneficiary,
                amount=amount,
                reason=request[:300],
            )
            steps.append("approval:required")
            self._pending[approval.approval_id] = (approval, steps)
            if self.approver is None:
                result = RunResult(route=route, status="pending_approval", answer="Transfer is waiting for human approval.", steps=steps, approval=approval)
            else:
                try:
                    decision = self.approver(approval)
                    if not isinstance(decision, ApprovalDecision):
                        decision = ApprovalDecision.model_validate(decision)
                except Exception as exc:
                    result = RunResult(route=route, status="failed", answer=f"Approval review failed: {type(exc).__name__}.", steps=steps + ["approval:failed"], approval=approval)
                else:
                    result = self._finish_approval(approval, decision, steps)
                    self._pending.pop(approval.approval_id, None)
            self._results[request_id] = result
            return self._copy(result)

        result = self._execute(account, beneficiary, amount, route, steps)
        self._results[request_id] = result
        return self._copy(result)

    def _execute(self, account, beneficiary, amount, route, steps):
        try:
            balance = self.deps.ledger.balance(account)
            if amount > balance:
                return RunResult(route=route, status="failed", answer="Insufficient funds; no transfer was made.", steps=steps + ["funds:insufficient"])
            posting = self.deps.ledger.post_transfer(account, beneficiary, amount)
        except (KeyError, ValueError) as exc:
            return RunResult(route=route, status="failed", answer=f"Transfer failed: {type(exc).__name__}.", steps=steps + ["transfer:failed"])
        return RunResult(route=route, status="completed", answer=f"Transfer of ${posting['amount']:.2f} was completed.", steps=steps + ["funds:checked", "posted"])

    def _finish_approval(self, approval, decision, steps):
        if not decision.approved:
            return RunResult(route="transaction", status="rejected", answer="The transfer was rejected and no funds were moved.", steps=steps + ["approval:rejected"], approval=approval)
        result = self._execute(
            approval.from_account,
            approval.beneficiary,
            approval.amount,
            "transaction",
            steps + [f"approval:approved:{decision.approver}"],
        )
        result.approval = approval
        return result

    def resume(self, approval_id: str, decision: ApprovalDecision) -> RunResult:
        pending = self._pending.pop(approval_id, None)
        if pending is None:
            for result in self._results.values():
                if result.approval and result.approval.approval_id == approval_id:
                    return self._copy(result)
            return RunResult(route="transaction", status="failed", answer="Approval request was not found or has already been resolved.", steps=["approval:unknown"])
        approval, steps = pending
        if not isinstance(decision, ApprovalDecision):
            decision = ApprovalDecision.model_validate(decision)
        result = self._finish_approval(approval, decision, steps)
        self._results[approval.request_id] = result
        return self._copy(result)
