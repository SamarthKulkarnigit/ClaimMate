"""Shared claim state (see docs/PLAN.md section 4.1)."""
from __future__ import annotations

from typing import Any, TypedDict


class ClaimState(TypedDict, total=False):
    claim_id: str
    story: str
    accident_date: str
    vehicle: dict          # {make, model, reg_no, cc, reg_date, age_months}
    policy: dict           # {policy_no, start, end, idv, zero_dep, voluntary_deductible}
    photos: list[dict]     # {id, path, exif_datetime, phash, duplicate_of}
    damages: list[dict]    # {part, side, severity, action, material, photo_ids, confidence}
    photo_quality: list[dict]
    plate_read: str | None
    extra_items: list[dict]
    coverage: list[dict]   # {part, status, clause_id, clause_quote, reason}
    estimate: dict         # {lines, totals}
    audit: dict            # {status, findings, send_back_to, hint}
    hint: str | None       # coordinator -> agent re-check hint
    retries: int
    next: str
    trail: list[str]       # agent visit order, for the UI
    decision: str | None
    escalation: dict | None
    outputs: dict
    synthetic: bool
    mock: dict             # demo-only canned LLM answers (used when LLM_MOCK=1)
    meta: dict[str, Any]
