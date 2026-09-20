"""Outreach tickets: one open question to one person about one case. Stored in state/outreach.json.

A reply is an ordinary document whose doc_id is `REPLY-<ticket_id>`; the Evidence worker reads it like any other
document, so what the person said lands in the tables. Outreach only has to notice that it arrived.
"""
from . import events, store

STATES = ("OPEN", "ANSWERED", "EXPIRED")


def ticket_id(case: dict, reason: str) -> str:
    return f"T-{case['period']}-{case['case_key'].replace('/', '-')}-{reason}"


def reply_doc_id(ticket: dict) -> str:
    return f"REPLY-{ticket['ticket_id']}"


def load(ws) -> list[dict]:
    return store.load_state(ws, "outreach", [])


def save(ws, tickets: list[dict]) -> list[dict]:
    return store.save_state(ws, "outreach", tickets)


def for_case(ws, case_id: str) -> list[dict]:
    return [t for t in load(ws) if t["case_id"] == case_id]


def open_ticket(ws, case: dict, reason: str, *, to: str, asked_of: str, question: str, deadline: str, blocking: bool, message: dict | None = None) -> dict:
    """Open a ticket, or return the one that already exists for this case and reason (a re-run never asks twice).
    asked_of is INTERNAL or VENDOR. A blocking ticket holds the case's estimate until it is answered or expires."""
    all_tickets = load(ws)
    tid = ticket_id(case, reason)
    existing = next((t for t in all_tickets if t["ticket_id"] == tid), None)
    if existing:
        return existing
    ticket = {"ticket_id": tid, "case_id": case["case_id"], "period": case["period"], "reason": reason, "asked_of": asked_of, "to": to,
              "question": question, "message": message, "blocking": blocking, "deadline": deadline, "state": "OPEN",
              "opened_at": ws.as_of, "answered_at": None, "answered_by_doc": None, "expired_at": None}
    all_tickets.append(ticket)
    save(ws, all_tickets)
    events.log(ws, "outreach", f"{tid}: asked {to} ({asked_of}) - {question}", case["period"])
    return ticket
