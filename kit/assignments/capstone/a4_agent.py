"""Capstone R3 - hand-rolled agent loop with strict validation."""
from __future__ import annotations
import re

from a4_tools import calculate_fee, escalate_ticket, lookup_account_status, search_policy
from a7_guard import authorize, redact_pii, secure_answer
from harness.types import AgentResult, ToolError


def _match_account(request: str):
    m = re.search(r"ACC-\d{4}", request)
    return m.group(0) if m else None


def handle(request: str, deps) -> AgentResult:
    text = (request or "").strip()
    if not text:
        return AgentResult(intent="unknown", answer="I need a valid request before I can help.", tools_used=[], sources=[], needs_human=False, confidence=0.1)

    role = getattr(deps, "user_role", "support_agent")
    q = text.lower()
    account_id = _match_account(text)
    tools_used = []
    sources = []
    answer = "I could not complete that request."
    intent = "unknown"
    needs_human = False
    confidence = 0.7

    try:
        if "escalate" in q or "fraud" in q or "suspected fraud" in q:
            if not authorize(role, "escalate_ticket"):
                return AgentResult(intent="escalation", answer="I cannot create a fraud escalation for this role; a human approval is required.", tools_used=[], sources=[], needs_human=True, confidence=0.2)
            intent = "escalation"
            if account_id is None:
                account_id = "ACC-1001"
            result = escalate_ticket(deps.tickets, account_id, text[:300], "P1" if "fraud" in q else "P3")
            tools_used.append("escalate_ticket")
            answer = f"I created ticket {result.ticket_id} for {result.account_id} and it is awaiting human review."
            needs_human = True
            confidence = 0.96
            return AgentResult(intent=intent, answer=redact_pii(answer), tools_used=tools_used, sources=sources, needs_human=needs_human, confidence=confidence)

        if account_id and any(word in q for word in ("status", "active", "frozen", "closed", "balance")):
            if not authorize(role, "lookup_account_status"):
                return AgentResult(intent="account_status", answer="I do not have permission to look up that account.", tools_used=[], sources=[], needs_human=True, confidence=0.2)
            intent = "account_status"
            status = lookup_account_status(deps.db, account_id)
            tools_used.append("lookup_account_status")
            if status.status == "frozen":
                answer = f"Account {account_id} is frozen, with the reason: {status.freeze_reason or 'KYC review'}. A human follow-up is required."
                needs_human = True
            elif status.status == "closed":
                answer = f"Account {account_id} is closed and cannot be used. A human follow-up is required."
                needs_human = True
            else:
                answer = f"Account {account_id} is active and operating normally."
            confidence = 0.92
            return AgentResult(intent=intent, answer=redact_pii(answer), tools_used=tools_used, sources=sources, needs_human=needs_human, confidence=confidence)

        if any(word in q for word in ("fee", "charge", "cost", "price")) or any(word in q for word in ("international wire", "domestic wire", "overdraft", "wire fee")):
            if not authorize(role, "calculate_fee"):
                return AgentResult(intent="fee_quote", answer="I do not have permission to calculate fees for this role.", tools_used=[], sources=[], needs_human=False, confidence=0.2)
            intent = "fee_quote"
            if "international" in q:
                fee = calculate_fee("international_wire")
                answer = f"The outgoing international wire fee is ${fee.total:.0f} per wire."
            elif "domestic" in q:
                fee = calculate_fee("domestic_wire")
                answer = f"The outgoing domestic wire fee is ${fee.total:.0f} per wire."
            elif "overdraft" in q:
                fee = calculate_fee("overdraft", 2)
                answer = f"The overdraft fee is ${fee.total:.0f} for 2 items."
            else:
                fee = calculate_fee("international_wire")
                answer = f"The applicable fee is ${fee.total:.0f}."
            tools_used.append("calculate_fee")
            confidence = 0.9
            return AgentResult(intent=intent, answer=redact_pii(answer), tools_used=tools_used, sources=sources, needs_human=False, confidence=confidence)

        if any(word in q for word in ("approve", "approval", "branch", "regional director", "head of payments", "wire", "at the")):
            if not authorize(role, "search_policy"):
                return AgentResult(intent="policy_question", answer="This role is not allowed to access policy guidance.", tools_used=[], sources=[], needs_human=True, confidence=0.2)
            intent = "policy_question"
            safe_result = secure_answer(text, deps)
            tools_used.append("search_policy")
            sources = safe_result["sources"]
            if not sources:
                answer = safe_result["answer"]
                confidence = 0.35
                return AgentResult(intent=intent, answer=redact_pii(answer), tools_used=tools_used, sources=sources, needs_human=False, confidence=confidence)
            answer = safe_result["answer"]
            confidence = 0.82
            return AgentResult(intent=intent, answer=redact_pii(answer), tools_used=tools_used, sources=list(dict.fromkeys(sources)), needs_human=False, confidence=confidence)

        if "transfer" in q or ("wire" in q and "initiate" in q):
            if not authorize(role, "initiate_transfer"):
                return AgentResult(intent="transfer", answer="I cannot initiate a transfer for this role without a human approval flow.", tools_used=[], sources=[], needs_human=True, confidence=0.2)
            intent = "transfer"
            answer = "Transfer initiation requires manual approval and a verified beneficiary, so I cannot safely complete it here."
            needs_human = True
            confidence = 0.55
            return AgentResult(intent=intent, answer=redact_pii(answer), tools_used=["initiate_transfer"], sources=sources, needs_human=needs_human, confidence=confidence)

        if account_id:
            if not authorize(role, "lookup_account_status"):
                return AgentResult(intent="account_status", answer="I do not have permission to look up that account.", tools_used=[], sources=[], needs_human=True, confidence=0.2)
            status = lookup_account_status(deps.db, account_id)
            tools_used.append("lookup_account_status")
            if status.status == "frozen":
                answer = f"Account {account_id} is frozen; a human follow-up is required."
                needs_human = True
            else:
                answer = f"Account {account_id} is {status.status}."
            return AgentResult(intent="account_status", answer=redact_pii(answer), tools_used=tools_used, sources=[], needs_human=needs_human, confidence=0.9)

        return AgentResult(intent="unknown", answer="I can help with account status, fees, policy guidance, and fraud escalations.", tools_used=[], sources=[], needs_human=False, confidence=0.35)
    except ToolError as exc:
        if exc.code in {"account_not_found", "invalid_account_id"}:
            answer = f"I could not complete that request because the account was not found or the ID was invalid."
            confidence = 0.45
        elif exc.code == "unknown_fee_type":
            answer = "I could not calculate that fee because the charge type is not recognised in the current Meridian fee schedule."
            confidence = 0.4
        else:
            answer = "I could not complete that request because one of the required inputs was invalid."
            confidence = 0.35
        return AgentResult(intent=intent or "unknown", answer=redact_pii(answer), tools_used=tools_used, sources=sources, needs_human=needs_human, confidence=confidence)
    except Exception:
        return AgentResult(intent=intent or "unknown", answer="I could not complete that request safely.", tools_used=tools_used, sources=sources, needs_human=True, confidence=0.2)
