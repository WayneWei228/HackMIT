"""Formatting helpers and deterministic legal filler shared by the file builders."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from trueup.simulator.files.doc import Block, Heading, Para

_CENT = Decimal("0.01")


def usd(value: Decimal) -> str:
    """$1,400 for whole dollars, $1,234.50 for cents, $0.016 for finer rates."""
    if value == value.to_integral_value():
        return f"${int(value):,}"
    if value == value.quantize(_CENT):
        return f"${value:,.2f}"
    return "$" + format(value.normalize(), "f")


def usd2(value: Decimal) -> str:
    return f"${value.quantize(_CENT):,.2f}"


def long_date(day: date) -> str:
    return f"{day:%B} {day.day}, {day.year}"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def split_units(total: int, parts: int) -> list[int]:
    """Split an integer into `parts` near-equal integers that sum exactly."""
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


_SECTIONS = (
    (
        "1. Definitions",
        "In this Agreement, Customer means {customer} and Vendor means {vendor}. "
        "Services means the products and services described in the applicable order. "
        "Effective Date means the date on which both parties have signed the Agreement.",
    ),
    (
        "2. Services",
        "Vendor will provide the Services in accordance with the applicable order and this "
        "Agreement. Customer may use the Services for its internal business purposes and "
        "may permit its employees and contractors to use them on its behalf.",
    ),
    (
        "3. Term and Renewal",
        "This Agreement begins on the Effective Date and continues for the initial term stated "
        "in the order. Unless either party gives written notice at least thirty days before the "
        "end of the term, the Agreement renews for successive periods of equal length.",
    ),
    (
        "5. Confidentiality",
        "Each party will protect the other party's confidential information using the same "
        "care it uses for its own, and no less than reasonable care. Confidential information "
        "may be disclosed only to personnel who need to know it and are bound by similar duties.",
    ),
    (
        "6. Warranties",
        "Vendor warrants that the Services will be performed in a professional manner and will "
        "materially conform to the documentation. Except as stated, the Services are provided "
        "as is, and each party disclaims all other warranties to the extent permitted by law.",
    ),
    (
        "7. Limitation of Liability",
        "Neither party is liable for indirect, incidental or consequential damages. Each "
        "party's total liability arising out of this Agreement is limited to the amounts paid "
        "or payable by Customer in the twelve months before the event giving rise to the claim.",
    ),
    (
        "8. Termination",
        "Either party may terminate this Agreement for material breach that remains uncured "
        "thirty days after written notice. On termination Customer will pay all fees for "
        "Services delivered through the termination date.",
    ),
    (
        "9. General",
        "This Agreement is governed by the laws of the State of Delaware. It is the entire "
        "agreement between the parties on its subject and may be amended only in a writing "
        "signed by both parties. Notices must be sent to the addresses in the order.",
    ),
)


def boilerplate(vendor: str, customer: str) -> tuple[Block, ...]:
    """Sections 1-3 come before the fee section and 5-9 after it, so callers slice this."""
    blocks: list[Block] = []
    for heading, text in _SECTIONS:
        blocks += [Heading(heading), Para(text.format(vendor=vendor, customer=customer))]
    return tuple(blocks)


def before_fees(blocks: tuple[Block, ...]) -> tuple[Block, ...]:
    return blocks[:6]


def after_fees(blocks: tuple[Block, ...]) -> tuple[Block, ...]:
    return blocks[6:]
