"""EXIF and 64-bit pHash evidence signals; neither proves fraud or authenticity.

Merged: Samarth's imagehash/EXIF implementation + the wrappers the agent graph calls
(inspect_photo(path, claim_id) -> duplicate_of, remember()).
"""
import json
import re
from datetime import datetime, date
from pathlib import Path

import imagehash
from PIL import Image, ImageOps

HASH_INDEX = Path(__file__).resolve().parents[2] / "data/past_claims_hashes.json"
# Completed live claims go to a gitignored runtime index, never into the committed fixture.
RUNTIME_INDEX = Path(__file__).resolve().parents[2] / "outputs/claim_hashes.json"


def _read_photo(path: str) -> dict:
    with Image.open(path) as image:
        exif = image.getexif()
        # DateTimeOriginal normally lives in the nested EXIF IFD.
        nested = exif.get_ifd(34665) if 34665 in exif else {}
        raw = nested.get(36867) or exif.get(36867) or exif.get(306)
        timestamp = None
        if raw:
            try:
                timestamp = datetime.strptime(str(raw).strip("\x00"), "%Y:%m:%d %H:%M:%S").isoformat()
            except ValueError:
                pass
        return {"exif_datetime": timestamp, "has_exif": bool(exif),
                "phash": str(imagehash.phash(ImageOps.exif_transpose(image).convert("RGB")))}


def _hash(value: str):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{16}", value):
        raise ValueError("Expected a 16-character 64-bit perceptual hash")
    return imagehash.hex_to_hash(value)


def find_duplicate(phash: str, max_distance: int = 6) -> str | None:
    """Return nearest prior claim ID; index is a list of {claim_id, phash}.

    Caller indexes completed prior claims, never the current claim's photos.
    Missing/corrupt index raises instead of silently returning a clean result.
    """
    query = _hash(phash)
    if type(max_distance) is not int or not 0 <= max_distance <= 64:
        raise ValueError("max_distance must be an integer from 0 to 64")
    records = json.loads(HASH_INDEX.read_text())
    if RUNTIME_INDEX.exists():
        records += json.loads(RUNTIME_INDEX.read_text())
    nearest = sorted((query - _hash(row["phash"]), row["claim_id"]) for row in records)
    return nearest[0][1] if nearest and nearest[0][0] <= max_distance else None


def inspect_photo(path: str, claim_id: str | None = None) -> dict:
    """EXIF capture time, pHash, and nearest earlier claim (if any) for one photo."""
    info = _read_photo(str(path))
    dup = find_duplicate(info["phash"])
    info["duplicate_of"] = dup if dup and dup != claim_id else None
    return info


def remember(claim_id: str, phash: str, photo: str | None = None) -> None:
    """Index a COMPLETED claim's photo so future claims can be checked against it."""
    records = json.loads(RUNTIME_INDEX.read_text()) if RUNTIME_INDEX.exists() else []
    if not any(r["phash"] == phash and r["claim_id"] == claim_id for r in records):
        records.append({"claim_id": claim_id, "phash": phash})
        RUNTIME_INDEX.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_INDEX.write_text(json.dumps(records, indent=2))


def check_photo_date(exif_datetime: str | None, accident_date: str, policy_start: str, policy_end: str) -> dict:
    """Date-only comparison: EXIF clocks are untrusted and usually lack timezone."""
    accident, start, end = (date.fromisoformat(v) for v in (accident_date, policy_start, policy_end))
    if end < start:
        raise ValueError("Policy end precedes start")
    if not start <= accident <= end:
        return {"ok": False, "action": "escalate", "detail": "Accident date is outside the policy period."}
    if not exif_datetime:
        return {"ok": None, "action": "request_evidence", "detail": "Capture date unavailable; ask for supporting evidence."}
    captured = datetime.fromisoformat(exif_datetime).date()
    if not start <= captured <= end:
        return {"ok": False, "action": "escalate", "detail": "Photo date is outside the policy period."}
    if captured != accident:
        return {"ok": False, "action": "request_evidence", "detail": "Photo and accident dates differ; confirm when the photo was taken."}
    return {"ok": True, "action": "continue", "detail": "Photo date matches accident date and policy period."}
