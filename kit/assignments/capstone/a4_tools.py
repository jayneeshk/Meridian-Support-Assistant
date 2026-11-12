"""Capstone R2 - typed, safe tools."""
from __future__ import annotations
import re
from typing import Optional

from pydantic import BaseModel

from harness.backends import load_fee_schedule
from harness.types import ToolError


class AccountStatus(BaseModel):
    account_id: str
    product: str
    status: str
    masked_account_number: str
    freeze_reason: Optional[str] = None


class FeeQuote(BaseModel):
    fee_type: str
    unit_fee: float
    quantity: int
    free_quantity: int
    total: float
    schedule_id: str


class Ticket(BaseModel):
    ticket_id: str
    account_id: str
    reason: str
    priority: str
    created_new: bool


_ACCOUNT_RE = re.compile(r"^ACC-\d{4}$")


def _normalise_fee_type(fee_type: str) -> str:
    if not isinstance(fee_type, str):
        raise ToolError("unknown_fee_type", "Unknown fee type")
    key = fee_type.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "domestic_wire": "domestic_wire",
        "domestic": "domestic_wire",
        "international_wire": "international_wire",
        "international": "international_wire",
        "incoming_wire": "incoming_wire",
        "wire_recall": "wire_recall",
        "stop_payment": "stop_payment",
        "overdraft": "overdraft",
        "paper_statement": "paper_statement",
        "card_replacement": "card_replacement",
        "excess_withdrawal": "excess_withdrawal",
    }
    if key not in aliases:
        raise ToolError("unknown_fee_type", f"Unknown fee type: {fee_type}")
    return aliases[key]


def lookup_account_status(db, account_id: str) -> AccountStatus:
    if not isinstance(account_id, str) or not _ACCOUNT_RE.fullmatch(account_id):
        raise ToolError("invalid_account_id", "Account ID must match ACC-####")
    record = db.get(account_id)
    if record is None:
        raise ToolError("account_not_found", f"Account {account_id} was not found")
    masked = "************" + str(record.get("account_number", "")[-4:])
    status = AccountStatus(
        account_id=account_id,
        product=record.get("product", ""),
        status=record.get("status", ""),
        masked_account_number=masked,
        freeze_reason=record.get("freeze_reason"),
    )
    return status


def calculate_fee(fee_type: str, quantity: int = 1, plan: Optional[str] = None) -> FeeQuote:
    if not isinstance(quantity, int) or quantity < 1 or quantity > 1000:
        raise ToolError("invalid_quantity", "Quantity must be between 1 and 1000")
    fee_key = _normalise_fee_type(fee_type)
    schedule = load_fee_schedule()
    fees = schedule.get("fees", {})
    if fee_key not in fees:
        raise ToolError("unknown_fee_type", f"Unknown fee type: {fee_type}")
    if plan is not None and plan not in ("business_current", "premier_saver"):
        raise ToolError("unknown_plan", "Plan must be None, business_current or premier_saver")
    free_quantity = 0
    if fee_key == "domestic_wire":
        free_allowance = schedule.get("free_allowance", {}).get("domestic_wire", {})
        if plan in free_allowance:
            free_quantity = int(free_allowance.get(plan, 0))
    unit_fee = float(fees[fee_key])
    total = max(0.0, unit_fee * max(0, quantity - free_quantity))
    return FeeQuote(
        fee_type=fee_key,
        unit_fee=unit_fee,
        quantity=quantity,
        free_quantity=free_quantity,
        total=total,
        schedule_id=schedule.get("schedule_id", "FEES-001"),
    )


def escalate_ticket(store, account_id: str, reason: str, priority: str) -> Ticket:
    if not isinstance(account_id, str) or not _ACCOUNT_RE.fullmatch(account_id):
        raise ToolError("invalid_account_id", "Account ID must match ACC-####")
    if not isinstance(priority, str) or priority not in {"P1", "P2", "P3"}:
        raise ToolError("invalid_priority", "Priority must be P1, P2 or P3")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 300:
        raise ToolError("invalid_reason", "Reason must be non-empty and <= 300 chars")
    norm_reason = " ".join(reason.strip().split()).lower()
    for existing in store.all():
        if existing.get("account_id") == account_id and existing.get("reason") == norm_reason and existing.get("priority") == priority:
            return Ticket(
                ticket_id=existing["ticket_id"],
                account_id=account_id,
                reason=existing["reason"],
                priority=priority,
                created_new=False,
            )
    counter = len(store.all()) + 1
    ticket_id = f"TCK-{counter:04d}"
    ticket = {"ticket_id": ticket_id, "account_id": account_id, "reason": norm_reason, "priority": priority}
    store.add(ticket)
    return Ticket(ticket_id=ticket_id, account_id=account_id, reason=norm_reason, priority=priority, created_new=True)


def search_policy(retriever, query: str, k: int = 4) -> list:
    if retriever is None:
        return []
    hits = retriever(query, k=k)
    return [{"doc_id": h.get("doc_id"), "chunk_id": h.get("chunk_id"), "text": h.get("text")} for h in hits if h.get("doc_id")]
