"""In-memory event log per claim. Graph nodes call emit(); the SSE endpoint replays + tails it."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_events: dict[str, list[dict]] = {}


def emit(claim_id: str, type_: str, agent: str, text: str = "", data: dict | None = None) -> None:
    ev = {
        "type": type_,
        "agent": agent,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "text": text,
        "data": data or {},
    }
    with _lock:
        lst = _events.setdefault(claim_id, [])
        ev["seq"] = len(lst)
        lst.append(ev)
    print(f"[{claim_id}] {type_:<11} {agent:<11} {text}")


def since(claim_id: str, idx: int) -> list[dict]:
    with _lock:
        return list(_events.get(claim_id, [])[idx:])


def all_events(claim_id: str) -> list[dict]:
    return since(claim_id, 0)
