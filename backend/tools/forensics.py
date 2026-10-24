"""Photo forensics: EXIF capture time + perceptual hash duplicate check. No LLM."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PIL import Image

from backend import config

HASH_STORE = config.DATA / "past_claims_hashes.json"


def dhash(path: str | Path, size: int = 8) -> str:
    """Difference hash (64-bit hex). Robust to resize / recompression."""
    with Image.open(path) as im:
        g = im.convert("L").resize((size + 1, size))
        px = list(g.getdata())
    bits = 0
    for r in range(size):
        for c in range(size):
            bits = (bits << 1) | (px[r * (size + 1) + c] > px[r * (size + 1) + c + 1])
    return f"{bits:0{size * size // 4}x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def exif_datetime(path: str | Path) -> str | None:
    try:
        with Image.open(path) as im:
            ex = im.getexif()
            raw = ex.get_ifd(0x8769).get(36867) or ex.get(306)  # DateTimeOriginal, DateTime
        if raw:
            return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:  # noqa: BLE001
        pass
    return None


def _store() -> list[dict]:
    if HASH_STORE.exists():
        return json.loads(HASH_STORE.read_text(encoding="utf-8"))
    return []


def find_duplicate(phash: str, exclude_claim: str | None = None, max_distance: int = 6) -> dict | None:
    for rec in _store():
        if rec.get("claim_id") != exclude_claim and hamming(rec["phash"], phash) <= max_distance:
            return rec
    return None


def remember(claim_id: str, phash: str, photo: str) -> None:
    recs = _store()
    if not any(r["phash"] == phash and r["claim_id"] == claim_id for r in recs):
        recs.append({"claim_id": claim_id, "phash": phash, "photo": photo})
        HASH_STORE.write_text(json.dumps(recs, indent=1), encoding="utf-8")


def inspect_photo(path: str | Path, claim_id: str | None = None) -> dict:
    ph = dhash(path)
    dup = find_duplicate(ph, exclude_claim=claim_id)
    return {
        "exif_datetime": exif_datetime(path),
        "phash": ph,
        "duplicate_of": dup["claim_id"] if dup else None,
    }
