"""Render every case's files to disk and produce the agent-visible manifest and hidden truth."""

from __future__ import annotations

import random
from pathlib import Path

from trueup.simulator.files import render
from trueup.simulator.files.cases import BUILDERS, late_specs
from trueup.simulator.files.common import CLOSE, Cast, Ctx, Spec
from trueup.simulator.files.doc import Chat, Doc, Sheet, Thread
from trueup.simulator.files.models import (
    CaseEntry,
    FileEntry,
    FileUniverse,
    RelevanceEntry,
    RelevanceTruth,
)
from trueup.simulator.files.text import slug
from trueup.simulator.files.world_view import WorldView
from trueup.simulator.scenario_models import GeneratedWorld

RELEVANT = ("SUPPORTS_AMOUNT", "SUPPORTS_DISCREPANCY", "LATE_ARRIVAL")
PERIOD = "2026-12"


def _plural(count: int, unit: str) -> str:
    return f"{count} {unit}" if count == 1 else f"{count} {unit}s"


def _render(spec: Spec, path: Path, message_id: str) -> str:
    if spec.fmt == "PDF":
        assert isinstance(spec.content, Doc)
        return _plural(render.render_pdf(spec.content, path), "page")
    if spec.fmt == "DOCX":
        assert isinstance(spec.content, Doc)
        return _plural(render.render_docx(spec.content, path), "page")
    if spec.fmt == "XLSX":
        assert isinstance(spec.content, Sheet)
        return _plural(render.render_xlsx(spec.content, path), "row")
    if spec.fmt == "EML":
        assert isinstance(spec.content, Thread)
        return _plural(render.render_eml(spec.content, path, message_id), "message")
    assert isinstance(spec.content, Chat)
    return _plural(render.render_txt(spec.content, path), "message")


def build_universe(
    world: GeneratedWorld, seed: int, out_dir: Path
) -> tuple[FileUniverse, RelevanceTruth]:
    """Write files under out_dir/files/<vendor>/ and return the manifest plus the answer key."""
    view = WorldView(world, CLOSE)
    cast = Cast(view)
    cases: list[CaseEntry] = []
    files: list[FileEntry] = []
    truth: dict[str, RelevanceEntry] = {}
    for name, builder in BUILDERS.items():
        vendor = view.vendor(name)
        ctx = Ctx(world, view, cast, random.Random(f"{seed}:{name}"), vendor)
        case_id = f"CASE-{name.upper()}-{PERIOD}"
        cases.append(
            CaseEntry(
                case_id=case_id,
                vendor_id=vendor.vendor_id,
                vendor_name=name,
                title=f"{name} December accrual",
                period=PERIOD,
            )
        )
        universe = builder(ctx)
        ctx.rng.shuffle(universe)
        late = late_specs(ctx)
        numbered = [(f"FILE-{name.upper()}-{i:02d}", s) for i, s in enumerate(universe, 1)]
        numbered += [(f"FILE-{name.upper()}-L{i}", s) for i, s in enumerate(late, 1)]
        for file_id, spec in numbered:
            relative = f"files/{slug(name)}/{spec.filename}"
            size = _render(spec, out_dir / relative, file_id)
            files.append(
                FileEntry(
                    file_id=file_id,
                    case_id=case_id,
                    vendor_id=vendor.vendor_id,
                    name=spec.filename,
                    kind=spec.kind,  # type: ignore[arg-type]
                    format=spec.fmt,  # type: ignore[arg-type]
                    path=relative,
                    size_label=size,
                    available_at=spec.available_at,
                    preview=spec.preview,
                )
            )
            truth[file_id] = RelevanceEntry(
                file_id=file_id,
                case_id=case_id,
                relevant=spec.role in RELEVANT,
                role=spec.role,  # type: ignore[arg-type]
                in_universe=spec.universe,
                reason=spec.reason,
            )
    files.sort(key=lambda f: f.file_id)
    return FileUniverse(as_of=CLOSE, cases=cases, files=files), RelevanceTruth(
        entries=dict(sorted(truth.items()))
    )


def write_manifests(universe: FileUniverse, truth: RelevanceTruth, out_dir: Path) -> None:
    (out_dir / "file_universe.json").write_text(universe.model_dump_json(indent=2) + "\n")
    (out_dir / "relevance_truth.json").write_text(truth.model_dump_json(indent=2) + "\n")
