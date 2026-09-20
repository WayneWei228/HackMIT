"""Format-neutral document description that every renderer turns into a real file."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Heading:
    text: str


@dataclass(frozen=True)
class Para:
    text: str


@dataclass(frozen=True)
class KeyValues:
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Table:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


Block = Heading | Para | KeyValues | Table


@dataclass(frozen=True)
class Doc:
    title: str
    subtitle: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Sheet:
    """One spreadsheet. Cells are str, int or Decimal; Decimal cells are formatted as dollars."""

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class Mail:
    sender: str
    to: str
    sent: datetime
    subject: str
    body: str
    cc: str = ""


@dataclass(frozen=True)
class Thread:
    """An email thread. The newest message is last and becomes the .eml's own headers."""

    messages: tuple[Mail, ...]


@dataclass(frozen=True)
class ChatLine:
    sender: str
    sent: datetime
    text: str


@dataclass(frozen=True)
class Chat:
    channel: str
    lines: tuple[ChatLine, ...] = field(default_factory=tuple)
