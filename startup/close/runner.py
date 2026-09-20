"""The close, month by month, over a folder of documents - as a library.

Everything starts from the documents. The runner holds no vendor, no purchase order and no rate: it only says
which month folder is being closed, what the clock reads in each pass, and when a month is done. The Evidence
worker builds every table from the PDFs in the folder.

    periods(pdf_dir)                       the month folders, sorted
    workspace(root, as_of)                 root/db, root/state, root/out, root/world
    index_documents(root, pdf_dir)         world/documents/index.json, straight from the folders
    run_close(root, pdf_dir, period, llm)  the two close passes, the cutoff and the snapshot
    run_settlement(...)                    the two settlement passes and the snapshot
    status(root, pdf_dir)                  NOT_RUN | CLOSED | SETTLED per month, and what is still unsettled
    reset(root)                            wipe db / state / out / world

A document is filed in the folder of the month it ARRIVED, not the month it is about: December's late
invoice reaches us in January, so it lives in `2027-01/` and is first seen when January is closed.
Folders decide when a document becomes known (`<next>` = the following month):

    <P>/*                      arrived during the month      (<next>-01)   known by the time P is closed
    <P>/replies/*              answers before the cutoff     (<next>-03)   a reply is named REPLY-<ticket_id>
    <P>/afterclose/*           arrives after P is closed     (<next>-12)   still supported; the month folder is enough
    <P>/afterclose/replies/*   vendor answers after close    (<next>-20)

Each month runs on a simulated clock:

    <next>-02  close pass 1   evidence, settle the earlier months, detection, invoice lookup, classification,
                              estimation, outreach (asks)
    <next>-05  close pass 2   the same again with the replies, outreach (answers / expiries), close out
    <next>-15  settle pass 1  evidence (after-close documents), settlement (true-ups, vendor questions)
    <next>-25  settle pass 2  evidence (vendor replies), outreach (answers), settlement (explanations)

Because a document about December only arrives in January, each close first settles what the months already
closed are still waiting for: the January close is where December's invoice becomes December's true-up.
"""
from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from . import case as cases_mod
from . import classifier, detection, estimation, evidence, improvements, invoice_lookup, outreach, settlement, store, tickets
from .workspace import Workspace

MONTH = re.compile(r"\d{4}-\d{2}")
DOC_SUFFIXES = (".pdf", ".txt")
RUNS = "runs"  # state/runs.json: {period: {"closed_at": ..., "settled_at": ...}}
CLOSE_PASSES = (("close pass 1", "02", False), ("close pass 2 - cutoff", "05", True))
SETTLE_PASSES = (("settle pass 1", "15"), ("settle pass 2", "25"))
CLOSED_STATUSES = ("CLOSED", "SETTLED", "LEARNED")


# --------------------------------------------------------------------------------------------------------------
# Time and place
# --------------------------------------------------------------------------------------------------------------


def next_month(period: str) -> str:
    y, m = map(int, period.split("-"))
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def available_at(period: str, rel: Path) -> str:
    """When a document filed at `rel` inside the month folder becomes known.

    A document that simply arrived during the month is known when the month ends (`<next>-01`), which is
    before that month's own close and after the close of the month before it: a January invoice for December
    can never be read back into the December close, only into December's settlement."""
    parts, nxt = rel.parts[:-1], next_month(period)
    if "afterclose" in parts:
        return f"{nxt}-20" if "replies" in parts else f"{nxt}-12"
    return f"{nxt}-03" if "replies" in parts else f"{nxt}-01"


def periods(pdf_dir: Path) -> list[str]:
    """Every month folder in the document directory, oldest first."""
    if not Path(pdf_dir).is_dir():
        return []
    return sorted(p.name for p in Path(pdf_dir).iterdir() if p.is_dir() and MONTH.fullmatch(p.name))


def documents_in(pdf_dir: Path, period: str) -> list[Path]:
    folder = Path(pdf_dir) / period
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in DOC_SUFFIXES)


def workspace(root: Path, as_of: str) -> Workspace:
    root = Path(root)
    return Workspace(world_dir=root / "world", db_dir=root / "db", state_dir=root / "state",
                     out_dir=root / "out", as_of=as_of).ensure()


def index_documents(root: Path, pdf_dir: Path) -> list[dict]:
    """The document index the Evidence worker reads, built from the folder tree alone."""
    index = [{"doc_id": f.stem, "file": str(f.resolve()), "period": period,
              "available_at": available_at(period, f.relative_to(Path(pdf_dir) / period))}
             for period in periods(pdf_dir) for f in documents_in(pdf_dir, period)]
    path = Path(root) / "world" / "documents" / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=1))
    return index


def reset(root: Path) -> None:
    """Forget every run: the tables, the cases, the packages and the index all go."""
    for sub in ("db", "state", "out", "world"):
        shutil.rmtree(Path(root) / sub, ignore_errors=True)


# --------------------------------------------------------------------------------------------------------------
# The cutoff and what a pass leaves behind
# --------------------------------------------------------------------------------------------------------------


def close_out(ws, period: str) -> list[dict]:
    """The cutoff: every estimate becomes the month's accrual and the case is closed. Invoiced cases close with
    nothing to accrue. Re-running a closed month re-reports the same accruals and changes nothing."""
    everything = cases_mod.load_cases(ws)
    mine = [c for c in everything if c["period"] == period]
    for c in mine:
        if c["status"] == "ESTIMATED":
            cases_mod.transition(ws, c, "JOURNALED", "runner", "cutoff: estimate booked as the accrual")
            cases_mod.transition(ws, c, "CLOSED", "runner", "period closed")
        elif c["status"] == "INVOICED":
            cases_mod.transition(ws, c, "CLOSED", "runner", "period closed, invoice on hand")
    cases_mod.save_cases(ws, everything)
    return [{"case_key": c["case_key"], "vendor": c["vendor_id"], "category": c["estimate"]["category"],
             "amount": c["estimate"]["amount"], "calculation": c["estimate"]["calculation"],
             "estimator": c["estimate"]["estimator"], "complete": c["estimate"]["complete"], "flags": c["flags"]}
            for c in mine if c["status"] in CLOSED_STATUSES and (c.get("estimate") or {}).get("amount") is not None]


def snapshot(ws, period: str, documents: list[dict], accruals: list[dict] | None = None) -> None:
    out = ws.out_dir / period
    for sub in ("documents", "cases", "tables"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    for d in documents:
        rows = store.load_table(ws, d["applied_to"]) if d["applied_to"] else []
        key = {"invoices": "invoice_id", "activity": "activity_id", "goods_receipts": "gr_id"}.get(d["applied_to"], "source_doc")
        one = {"file": d["file"], "doc_id": d["doc_id"], "known_from": d.get("available_at"), "doc_type": d["doc_type"], "extracted": d["record"],
               "matched_vendor_id": d["vendor_id"], "matched_po_line_id": d["po_line_id"], "quality": d["quality"], "reasons": d["reasons"],
               "written_to_table": d["applied_to"], "written_row": next((r for r in rows if r.get(key) == d["doc_id"] or r.get("source_doc") == d["doc_id"]), None)}
        (out / "documents" / f"{d['doc_id']}.json").write_text(json.dumps(one, indent=2))
    all_tickets = tickets.load(ws)
    for c in cases_mod.cases_for(ws, period):
        dossier = {k: c[k] for k in ("case_id", "status", "vendor_id", "po_line_id", "flags", "obligation", "invoice_match", "classification", "estimate", "settlement")}
        dossier["tickets"] = [t for t in all_tickets if t["case_id"] == c["case_id"]]
        dossier["decision_log"] = c["decision_log"]
        (out / "cases" / f"{c['case_key'].replace('/', '-')}.json").write_text(json.dumps(dossier, indent=2))
    for tbl in sorted(ws.db_dir.glob("*.json")):
        shutil.copy(tbl, out / "tables" / tbl.name)
    (out / "tickets.json").write_text(json.dumps([t for t in all_tickets if t["period"] == period], indent=2))
    if accruals is not None:
        (out / "accruals.json").write_text(json.dumps(accruals, indent=2))
    settled = [{"case_key": c["case_key"], **c["settlement"]} for c in cases_mod.cases_for(ws, period) if c.get("settlement")]
    (out / "trueups.json").write_text(json.dumps(settled, indent=2))


def show_documents(say, documents: list[dict]) -> None:
    for d in documents:
        say(f"    {d['doc_id']:<52} {d['doc_type']:<16} {d['quality']:<12} -> {d['applied_to'] or '-'}"
            + (f"   ! {'; '.join(d['reasons'])}" if d["reasons"] else ""))


def show_cases(say, ws, period: str) -> None:
    for c in cases_mod.cases_for(ws, period):
        e, s = c.get("estimate"), c.get("settlement")
        amount = f"{e['amount']:>10,.2f} = {e['calculation']}  [{e['estimator']}]" if e and e["amount"] is not None else ("       n/a" if e else "         -")
        tail = f"   actual {s['actual']:,.2f}, true-up {s['true_up']:+,.2f}, {s['cause']}" + ("" if s["explained"] else " (asked the vendor)") if s else ""
        say(f"    {c['case_key']:<18} {c['status']:<17} {amount}{tail}  {c['flags'] or ''}")


def _sayer(out: Callable[[str], None] | None) -> Callable[[str], None]:
    return out or (lambda _msg: None)


def runs(ws) -> dict:
    return store.load_state(ws, RUNS, {}) or {}


def mark(ws, period: str, key: str) -> dict:
    book = runs(ws)
    book[period] = {**book.get(period, {}), key: ws.as_of}
    store.save_state(ws, RUNS, book)
    return book


# --------------------------------------------------------------------------------------------------------------
# What the months already closed are still waiting for
# --------------------------------------------------------------------------------------------------------------


def awaiting_actual(ws, period: str) -> list[dict]:
    """Closed cases of `period` that carry an accrual and have not met their actual yet."""
    return [c for c in cases_mod.cases_for(ws, period)
            if c["status"] == "CLOSED" and (c.get("estimate") or {}).get("amount") is not None]


def unexplained(ws, period: str) -> list[dict]:
    """Settled cases of `period` whose variance nobody has explained yet: a vendor was asked."""
    return [c for c in cases_mod.cases_for(ws, period)
            if c["status"] == "SETTLED" and (c.get("settlement") or {}).get("explained") is False]


def settle_sweep(ws, period: str, llm, say) -> list[dict]:
    """One settlement sweep over a period at the current clock: read the answers, book the true-ups, and
    word the questions settlement just opened. The same sequence a settlement pass runs."""
    deadline = f"{next_month(period)}-05T00:00:00Z"
    outreach.run(ws, llm, period, deadline=deadline)                # replies that arrived -> ANSWERED
    touched = settlement.run(ws, period)
    outreach.run(ws, llm, period, deadline=deadline)                # word the new vendor questions
    if touched:
        mark(ws, period, "settled_at")
        say(f"\n  -- settling {period} with what {period} could not see, clock {ws.as_of}")
        for t in tickets.load(ws):
            if t["period"] == period and t["asked_of"] == "VENDOR":
                say(f"    ticket {t['ticket_id']:<52} {t['state']:<9} to {t['to']} ({t['asked_of']})")
        show_cases(say, ws, period)
        snapshot(ws, period, [])                                    # the month's package keeps up
    return touched


def catch_up(ws, period: str, llm, say) -> list[str]:
    """Before this month's own cases: settle every earlier month that is still waiting for something.

    A close is the first moment the documents that arrived this month are on the table, and some of them
    are about a month that is already closed."""
    book, done = runs(ws), []
    for earlier in sorted(p for p in book if p < period and (book[p] or {}).get("closed_at")):
        if not (awaiting_actual(ws, earlier) or unexplained(ws, earlier)):
            continue
        if settle_sweep(ws, earlier, llm, say):
            done.append(earlier)
    return done


# --------------------------------------------------------------------------------------------------------------
# The passes
# --------------------------------------------------------------------------------------------------------------


def run_close(root: Path, pdf_dir: Path, period: str, llm, *, out: Callable[[str], None] | None = None) -> dict:
    """Close one month: two passes on the simulated clock, the cutoff, and the month's package.

    Refuses while an earlier month folder is unclosed - earlier months feed the tables. Safe to re-run: the
    documents are hash-cached, Detection keeps CLOSED cases, and the cutoff re-reports the same accruals."""
    say = _sayer(out)
    ws = workspace(root, f"{period}-01T00:00:00Z")
    book = runs(ws)
    behind = [p for p in periods(pdf_dir) if p < period and not (book.get(p) or {}).get("closed_at")]
    if behind:
        raise ValueError(f"cannot close {period}: {', '.join(behind)} not closed yet - "
                         "earlier months build the purchase tables, so close them in order")
    index_documents(root, pdf_dir)
    nxt, accruals, deadline = next_month(period), None, f"{next_month(period)}-05T00:00:00Z"
    shutil.rmtree(ws.out_dir / period, ignore_errors=True)
    active = [l["id"] for l in improvements.load(ws) if l["status"] == "ACTIVE"]
    say(f"\n================ {period}   (active lessons: {active or 'none'}) ================")
    for label, day, cutoff in CLOSE_PASSES:
        ws = ws.at(f"{nxt}-{day}T12:00:00Z")
        say(f"\n  -- {label}, clock {ws.as_of}")
        documents = evidence.run(ws, llm, period)
        show_documents(say, documents)
        catch_up(ws, period, llm, say)      # what arrived this month about the months already closed
        detection.run(ws, period)
        invoice_lookup.run(ws, period)
        classifier.run(ws, llm, period)
        estimation.run(ws, llm, period)
        for t in outreach.run(ws, llm, period, deadline=deadline):
            say(f"    ticket {t['ticket_id']:<52} {t['state']:<9} to {t['to']} ({t['asked_of']})")
        if cutoff:
            accruals = close_out(ws, period)
        show_cases(say, ws, period)
        snapshot(ws, period, documents, accruals)
    mark(ws, period, "closed_at")
    total = round(sum(a["amount"] for a in accruals or []), 2)
    return {"period": period, "accrued_total": total, "cases": len(cases_mod.cases_for(ws, period)),
            "tickets": len([t for t in tickets.load(ws) if t["period"] == period])}


def run_settlement(root: Path, pdf_dir: Path, period: str, llm, *, out: Callable[[str], None] | None = None) -> dict:
    """Settle one closed month on its own clock: the documents the close could not see, the true-ups and the
    vendor questions. A later month's close does the same sweep for this month when its documents arrive there."""
    say = _sayer(out)
    ws = workspace(root, f"{period}-01T00:00:00Z")
    if not (runs(ws).get(period) or {}).get("closed_at"):
        raise ValueError(f"cannot settle {period}: it has not been closed yet")
    index_documents(root, pdf_dir)
    nxt = next_month(period)
    for label, day in SETTLE_PASSES:
        ws = ws.at(f"{nxt}-{day}T12:00:00Z")
        documents = evidence.run(ws, llm, period)
        if documents:
            say(f"\n  -- {label}, clock {ws.as_of}")
            show_documents(say, documents)
        settle_sweep(ws, period, llm, say)
        snapshot(ws, period, documents)
    mark(ws, period, "settled_at")
    mine = [c for c in cases_mod.cases_for(ws, period) if c.get("settlement")]
    return {"period": period, "settled": len(mine),
            "true_up_total": round(sum(c["settlement"]["true_up"] for c in mine), 2)}


def status(root: Path, pdf_dir: Path) -> list[dict]:
    """Where every month folder stands: whether it ran, what it accrued, what it trued up, and how many of
    its accruals are still waiting for an actual (a closed month can be settled and still have one open)."""
    ws = workspace(root, "1970-01-01T00:00:00Z")
    book, cases = runs(ws), cases_mod.load_cases(ws)
    out = []
    for period in periods(pdf_dir):
        mine = [c for c in cases if c.get("period") == period]
        done = book.get(period) or {}
        settled = [c for c in mine if c.get("settlement")]
        waiting = [c for c in mine if c["status"] == "CLOSED" and (c.get("estimate") or {}).get("amount") is not None]
        if not done.get("closed_at"):
            state = "NOT_RUN"
        elif done.get("settled_at") and (settled or not waiting):
            state = "SETTLED"      # settlement has run and either trued something up or has nothing left to do
        else:
            state = "CLOSED"
        accruals = read_json(ws.out_dir / period / "accruals.json")
        trueups = read_json(ws.out_dir / period / "trueups.json")
        out.append({"period": period, "state": state, "cases": len(mine),
                    "accrued_total": round(sum(a.get("amount") or 0 for a in accruals), 2),
                    "true_up_total": round(sum(t.get("true_up") or 0 for t in trueups), 2),
                    "unsettled": len(waiting),
                    "documents": len(documents_in(pdf_dir, period))})
    return out


def read_json(path: Path) -> list[dict]:
    return json.loads(path.read_text()) if path.exists() else []
