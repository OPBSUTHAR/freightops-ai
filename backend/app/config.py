"""Runtime configuration for the FreightOps AI control tower."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "FreightOps AI"
    version: str = "1.0.0"
    developer: str = "Omprakash Suthar"
    developer_role: str = "AI / Platform Engineer - freight operations"

    # Storage: memory (default, zero-setup) or mongo.
    storage: str = field(default_factory=lambda: os.getenv("STORAGE", "memory").lower())
    mongodb_uri: str = field(default_factory=lambda: os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    mongodb_db: str = field(default_factory=lambda: os.getenv("MONGODB_DB", "freightops"))

    # Model routing. "rules" is a deterministic baseline that needs no API key.
    llm_mode: str = field(default_factory=lambda: os.getenv("LLM_MODE", "rules").lower())
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_small_model: str = field(default_factory=lambda: os.getenv("LLM_SMALL_MODEL", "gpt-4o-mini"))

    # Guardrails / operating policy.
    min_margin_pct: float = field(default_factory=lambda: _float("MIN_MARGIN_PCT", 12.0))
    max_auto_book_usd: float = field(default_factory=lambda: _float("MAX_AUTO_BOOK_USD", 5000.0))
    doc_confidence_floor: float = field(default_factory=lambda: _float("DOC_CONFIDENCE_FLOOR", 0.85))
    carrier_reliability_floor: float = field(default_factory=lambda: _float("CARRIER_RELIABILITY_FLOOR", 0.85))
    run_budget_usd: float = field(default_factory=lambda: _float("RUN_BUDGET_USD", 0.25))

    @property
    def llm_enabled(self) -> bool:
        return self.llm_mode != "rules" and bool(self.llm_api_key)


settings = Settings()

CAPABILITIES = [
    "Multi-agent orchestration: planner, executor, reviewer, domain agents",
    "Quote, book, track-and-trace and exception handling for live freight ops",
    "Document ingestion with OCR-ready extraction for BOLs, invoices and packing lists",
    "RAG over tariffs and SOPs with vector search",
    "Evals, traces, cost telemetry and guardrails",
    "Clean REST APIs on MongoDB, React operator console",
]

MODEL_ROUTING = [
    {"task": "planning", "model": settings.llm_model if settings.llm_enabled else "deterministic-planner", "why": "low volume, needs reasoning"},
    {"task": "extraction", "model": settings.llm_small_model if settings.llm_enabled else "regex+heuristics", "why": "high volume, cost sensitive"},
    {"task": "review", "model": settings.llm_model if settings.llm_enabled else "policy-engine", "why": "must be auditable"},
]
