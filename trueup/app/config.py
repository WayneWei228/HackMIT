"""Runtime configuration. Secrets come from the environment only — never from a file in the repo."""
from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent

DATABASE_URL = os.environ.get("TRUEUP_DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'trueup.db'}")

# LLM. Absent key => StubLLM => the whole deterministic simulation still runs.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
LLM_ENABLED = bool(GEMINI_API_KEY) and os.environ.get("TRUEUP_DISABLE_LLM", "") != "1"

# Where the synthetic source PDFs live (the HackMIT fixture set).
PDF_DIR = Path(os.environ.get("TRUEUP_PDF_DIR", PROJECT_ROOT / "seed" / "pdf"))

# Close calendar for the demo company (Orbit Labs, Inc.).
HISTORICAL_PERIODS = [f"2026-{m:02d}" for m in range(1, 12)]   # 2026-01 .. 2026-11
LIVE_PERIOD = "2026-12"

OUT_DIR = Path(os.environ.get("TRUEUP_OUT_DIR", PROJECT_ROOT / "out"))
