"""Load demo/test claims from data/demo_claims/<name>/ into an initial ClaimState.

Supports Samarth's fixture format (photos = [{id, path}], path relative to repo root)
and the simple format (photos = ["file.jpg"] relative to the claim folder).
Offline LLM answers come from mock.json; the answer key from data/answer_key.json.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from backend import config

DEMO_DIR = config.DATA / "demo_claims"
MANIFEST = config.ROOT / "frontend" / "public" / "demo" / "manifest.json"

TITLES = {
    "clean_swift_front": ("A straightforward claim", "Swift · front damage · review & approve"),
    "partial_baleno_rear": ("A closer look at coverage", "Baleno · partial coverage · mechanical exclusion"),
    "mismatch_front_rear": ("When the story does not match", "Swift · story mismatch · re-check & escalation"),
    "duplicate_photo": ("A reused photo", "Photo matches an earlier claim · escalation"),
    "exif_before_policy": ("Outside the policy period", "Photo taken before the policy started"),
    "plate_mismatch": ("A different number plate", "Plate in photo ≠ RC · re-check & escalation"),
    "blurry_photo": ("More evidence needed", "Low-confidence photo · ask for clearer evidence"),
    "zero_dep": ("With zero depreciation", "Zero-dep add-on · no depreciation"),
    "six_year_old": ("A six-year-old vehicle", "40% metal depreciation"),
    "windshield_only": ("Windshield damage only", "Glass · 0% depreciation"),
}


def _answer_key() -> dict:
    f = config.DATA / "answer_key.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def expected_for(name: str, claim: dict) -> dict:
    if claim.get("expected"):
        return claim["expected"]
    k = _answer_key().get(name, {})
    return {"audit": k.get("expected_audit_outcome"), "covered": k.get("covered_parts", []),
            "not_covered": k.get("not_covered_parts", []), "dep_pct": k.get("expected_dep_pct", {})}


def list_demos() -> list[dict]:
    order = list(TITLES)
    names = sorted((p.parent.name for p in DEMO_DIR.glob("*/claim.json")),
                   key=lambda n: order.index(n) if n in order else 99)
    out = []
    for n in names:
        c = json.loads((DEMO_DIR / n / "claim.json").read_text(encoding="utf-8"))
        t, d = TITLES.get(n, (c.get("title", n.replace("_", " ")), c.get("story", "")))
        out.append({"name": n, "title": t, "description": d, "story": c.get("story"),
                    "expected": expected_for(n, c)})
    return out


def _resolve(name: str, p) -> tuple[str, Path]:
    if isinstance(p, str):
        return Path(p).stem, DEMO_DIR / name / p
    path = Path(p["path"])
    if not path.is_absolute():
        path = (config.ROOT / path) if (config.ROOT / path).exists() else (DEMO_DIR / name / path)
    return p.get("id") or path.stem, path


def load_demo(name: str, claim_id: str, copy_photos: bool = True) -> dict:
    folder = DEMO_DIR / name
    c = json.loads((folder / "claim.json").read_text(encoding="utf-8"))
    mock = json.loads((folder / "mock.json").read_text(encoding="utf-8")) if (folder / "mock.json").exists() else c.get("mock", {})

    photos = []
    up = config.UPLOADS / claim_id
    for i, raw in enumerate(c.get("photos", []), 1):
        orig_id, src = _resolve(name, raw)
        pid = f"P{i}"
        dst = src
        if copy_photos:
            up.mkdir(parents=True, exist_ok=True)
            dst = up / f"{pid}{src.suffix.lower() or '.jpg'}"
            shutil.copy(src, dst)
        photos.append({"id": pid, "path": str(dst), "name": src.name, "orig_id": orig_id})

    for key in ("damage", "damage_recheck"):
        m = mock.get(key)
        if isinstance(m, dict):
            mock[key] = {p["id"]: m.get(p["name"], m.get(p["orig_id"], m.get(p["id"], m.get("*")))) for p in photos}

    return {"claim_id": claim_id, "story": c["story"], "accident_date": c["accident_date"],
            "vehicle": {k: v for k, v in c["vehicle"].items() if k != "age_months"},
            "policy": c["policy"], "photos": photos, "mock": mock, "retries": 0, "trail": [],
            "synthetic": bool(c.get("synthetic")),
            "meta": {"demo": name, "expected": expected_for(name, c)}}
