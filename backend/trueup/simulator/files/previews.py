"""Small JSON blobs the frontend renders on each source card.

Shapes follow the comp: clause, table, memo, record, email, chat and skeleton cards.
"""

from __future__ import annotations

from trueup.simulator.files.doc import ChatLine, Mail

Preview = dict[str, object]


def clause(title: str, subtitle: str, heading: str, clause_no: str, text: str) -> Preview:
    return {
        "card": "clause",
        "title": title,
        "subtitle": subtitle,
        "heading": heading,
        "clause_no": clause_no,
        "text": text,
    }


def table(
    title: str, subtitle: str, columns: list[str], rows: list[list[str]], limit: int = 4
) -> Preview:
    return {
        "card": "table",
        "title": title,
        "subtitle": subtitle,
        "columns": columns,
        "rows": rows[:limit],
    }


def memo(title: str, subtitle: str, fields: dict[str, str], body: str) -> Preview:
    return {"card": "memo", "title": title, "subtitle": subtitle, "fields": fields, "body": body}


def record(title: str, subtitle: str, rows: list[tuple[str, str]]) -> Preview:
    return {
        "card": "record",
        "title": title,
        "subtitle": subtitle,
        "fields": [[k, v] for k, v in rows],
    }


def skeleton(
    title: str, subtitle: str, rows: list[tuple[str, str]], total: tuple[str, str] | None = None
) -> Preview:
    return {
        "card": "skeleton",
        "title": title,
        "subtitle": subtitle,
        "fields": [[k, v] for k, v in rows],
        "total": list(total) if total else None,
    }


def email(title: str, subtitle: str, mail: Mail) -> Preview:
    return {
        "card": "email",
        "title": title,
        "subtitle": subtitle,
        "fields": {"From": mail.sender, "To": mail.to, "Date": f"{mail.sent:%b %d, %Y}"},
        "body": mail.body,
    }


def chat(title: str, subtitle: str, lines: tuple[ChatLine, ...], limit: int = 4) -> Preview:
    return {
        "card": "chat",
        "title": title,
        "subtitle": subtitle,
        "messages": [
            {"sender": m.sender, "time": f"{m.sent:%H:%M}", "text": m.text} for m in lines[:limit]
        ],
    }
