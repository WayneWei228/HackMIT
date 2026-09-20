"""Outreach worker: the questions the close has to ask, and what happens when nobody answers.

For the period's cases:
  OUTREACH_PENDING        a blocking MISSING_DATA question to the PO requester - the estimate waits for the answer
  flag DATA_MISMATCH      a non-blocking question to Procurement: two sources disagree about the rate
  flag CLASSIFICATION_MISMATCH  a non-blocking question to Procurement: the columns and the description disagree
Code decides who is asked, what is asked and when it expires; the LLM only writes the wording of a NEW ticket, and
any failure sends the plain question instead. A reply is an ordinary document (`REPLY-<ticket_id>`): when Evidence
has accepted one, the ticket is ANSWERED. Past its deadline a ticket EXPIRES, and a blocking one forces its case to
book the recorded fallback - or, when there is none, 0.00 and a human.
"""
from . import case as cases_mod
from . import estimation, events, store, tickets

PROCUREMENT = "Procurement"


def requesters(ws) -> dict[str, str]:
    """po_line_id -> who to ask about it: the PO requester, else the cost centre owner, else Procurement."""
    headers = {h["po_number"]: h for h in store.visible(store.load_table(ws, "po_headers"), ws.as_of)}
    lines = store.visible(store.load_table(ws, "po_lines"), ws.as_of)
    return {l["po_line_id"]: (headers.get(l["po_number"]) or {}).get("requester")
            or (headers.get(l["po_number"]) or {}).get("cost_center_owner") or PROCUREMENT for l in lines}


def pending(case: dict, period: str, requester: str) -> list[dict]:
    """Everything this case's state says to ask right now, as {reason, to, blocking, question}."""
    estimate = case.get("estimate") or {}
    classification = case.get("classification") or {}
    flags = case.get("flags") or []
    who = case.get("vendor_name") or case.get("vendor_id")
    out = []
    if case.get("status") == "OUTREACH_PENDING":
        out.append({"reason": "MISSING_DATA", "to": requester, "blocking": True,
                    "question": f"We are closing {period} and cannot estimate {case['case_key']} ({who}): "
                                f"missing {estimate.get('missing')}. What was the amount for the period?"})
    if "DATA_MISMATCH" in flags:
        out.append({"reason": "DATA_MISMATCH", "to": PROCUREMENT, "blocking": False,
                    "question": f"{case['case_key']}: {estimate.get('mismatch')}. "
                                f"Which value is right, and can the PO be corrected?"})
    if "CLASSIFICATION_MISMATCH" in flags:
        out.append({"reason": "CLASSIFICATION_MISMATCH", "to": PROCUREMENT, "blocking": False,
                    "question": f"{case['case_key']}: the PO columns say {classification.get('rules')} but the "
                                f"description reads as {classification.get('suggested')}. Which is right?"})
    return out


def write_message(ws, llm, case: dict, ask: dict, period: str, deadline: str, asked_of: str = "INTERNAL") -> dict:
    """The wording of a new ticket. Any failure, or an empty body, falls back to the plain question."""
    plain = {"subject": f"[{period} close] {ask['reason']} {case['case_key']}", "body": ask["question"]}
    try:
        reply = llm("outreach_message", {"TO": ask["to"], "ASKED_OF": asked_of, "REASON": ask["reason"],
                                         "QUESTION": ask["question"], "PERIOD": period, "DEADLINE": deadline})
        subject, body = str(reply.get("subject") or "").strip(), str(reply.get("body") or "").strip()
        if not body:
            raise ValueError("no body")
    except Exception as exc:  # noqa: BLE001 - the question still has to go out
        events.log(ws, "outreach", f"{case['case_key']}: {ask['reason']} wording not written ({exc}), sending the question", period)
        return plain
    return {"subject": subject or plain["subject"], "body": body}


def answer(ws, ticket: dict, case: dict | None, doc_id: str) -> dict:
    ticket.update(state="ANSWERED", answered_at=ws.as_of, answered_by_doc=doc_id)
    if case is not None:
        cases_mod.log_decision(ws, case, "outreach", "RULE", f"Has {ticket['ticket_id']} been answered?", doc_id,
                               action=f"{ticket['reason']} ANSWERED")
    events.log(ws, "outreach", f"{ticket['ticket_id']}: answered by {doc_id}", ticket["period"])
    return ticket


def expire(ws, ticket: dict, case: dict | None) -> dict:
    """Nobody answered in time. A blocking ticket makes its case book what it can, or nothing at all."""
    ticket.update(state="EXPIRED", expired_at=ws.as_of)
    if case is not None:
        cases_mod.log_decision(ws, case, "outreach", "RULE", f"Has {ticket['ticket_id']} been answered by {ticket['deadline']}?",
                               False, action=f"{ticket['reason']} EXPIRED")
    events.log(ws, "outreach", f"{ticket['ticket_id']}: no answer by {ticket['deadline']}", ticket["period"])
    if not ticket.get("blocking") or case is None or case.get("status") != "OUTREACH_PENDING":
        return ticket
    if estimation.force(ws, case):
        return ticket
    estimate = case.get("estimate") or {}
    case["estimate"] = estimate
    cases_mod.transition(ws, case, "FORCED_ESTIMATE", "outreach", f"no answer to {ticket['ticket_id']} and no fallback to book")
    estimate.update(amount=0.0, forced=True)
    cases_mod.add_flag(case, "NO_ACCRUAL_BASIS")
    cases_mod.transition(ws, case, "ESTIMATED", "outreach", "0.00: nothing to base an accrual on")
    cases_mod.transition(ws, case, "REVIEW", "outreach", "no basis for an accrual: a human has to decide")
    return ticket


def run(ws, llm, period: str, deadline: str) -> list[dict]:
    """Ask the period's open questions, then read the answers and retire what has run out of time. Idempotent."""
    everything = cases_mod.load_cases(ws)
    asks = requesters(ws)
    known = {t["ticket_id"] for t in tickets.load(ws)}
    for case in [c for c in everything if c["period"] == period]:
        for ask in pending(case, period, asks.get(case.get("po_line_id")) or PROCUREMENT):
            tid = tickets.ticket_id(case, ask["reason"])
            message = None if tid in known else write_message(ws, llm, case, ask, period, deadline)
            ticket = tickets.open_ticket(ws, case, ask["reason"], to=ask["to"], asked_of="INTERNAL", question=ask["question"],
                                         deadline=deadline, blocking=ask["blocking"], message=message)
            known.add(tid)
            opened = (case.get("outreach") or {}).get("tickets") or []
            if ticket["ticket_id"] not in opened:
                case["outreach"] = {"tickets": [*opened, ticket["ticket_id"]]}

    replies = {d["doc_id"] for d in store.visible(store.load_table(ws, "documents"), ws.as_of) if d.get("quality") == "OK"}
    all_tickets, changed = tickets.load(ws), set()
    for ticket in all_tickets:  # every period: settlement's vendor tickets outlive their close
        if ticket.get("state") != "OPEN":
            continue
        case = cases_mod.find_case(everything, ticket["case_id"])
        if ticket.get("message") is None and case is not None:  # opened by another worker (settlement's vendor question): word it now
            ticket["message"] = write_message(ws, llm, case, ticket, ticket["period"], ticket["deadline"], ticket["asked_of"])
            changed.add(ticket["ticket_id"])
        reply = tickets.reply_doc_id(ticket)
        if reply in replies:  # an answer that arrives on the deadline still counts
            answer(ws, ticket, case, reply)
        elif ticket.get("deadline") and store.normalise_ts(ticket["deadline"]) <= store.normalise_ts(ws.as_of):
            expire(ws, ticket, case)
        else:
            continue
        changed.add(ticket["ticket_id"])

    tickets.save(ws, all_tickets)
    cases_mod.save_cases(ws, everything)
    return [t for t in all_tickets if t["period"] == period or t["ticket_id"] in changed]
