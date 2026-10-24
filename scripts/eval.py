"""Run every demo claim through the real LangGraph graph and score against its `expected` block.

    python -m scripts.eval              # real LLM calls (needs .env key)
    $env:LLM_MOCK="1"; python -m scripts.eval   # offline, canned answers
    python -m scripts.eval clean_swift_front    # just one
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph.types import Command  # noqa: E402

from backend import config  # noqa: E402
from backend.agents.graph import GRAPH  # noqa: E402

DEMO = config.DATA / "demo_claims"


def run(name: str) -> dict:
    c = json.loads((DEMO / name / "claim.json").read_text(encoding="utf-8"))
    photos = [{"id": f"P{i}", "path": str(DEMO / name / fn), "name": fn} for i, fn in enumerate(c["photos"], 1)]
    mock = c.get("mock", {})
    for k in ("damage", "damage_recheck"):
        if isinstance(mock.get(k), dict):
            mock[k] = {p["id"]: mock[k].get(p["name"]) for p in photos}
    cid = f"EVAL-{name}-{int(time.time())}"
    cfg = {"configurable": {"thread_id": cid}, "recursion_limit": 60}
    state = {"claim_id": cid, "story": c["story"], "accident_date": c["accident_date"], "vehicle": c["vehicle"],
             "policy": c["policy"], "photos": photos, "mock": mock, "retries": 0, "trail": [], "meta": {"demo": name}}
    t0 = time.time()
    GRAPH.invoke(state, cfg)
    snap = GRAPH.get_state(cfg)
    if snap.next and "human" in snap.next:
        GRAPH.invoke(Command(resume={"approved": True}), cfg)
    v = GRAPH.get_state(cfg).values
    secs = time.time() - t0

    exp = c.get("expected", {})
    outcome = "escalate" if v.get("escalation") else (v.get("audit") or {}).get("status")
    covered = {x["part"] for x in v.get("coverage") or [] if x["status"] in ("covered", "partial")}
    not_cov = {(x.get("item") or "").lower() for x in v.get("extra_items") or [] if x["status"] == "not_covered"}
    checks = {"outcome": outcome == exp.get("audit")}
    if exp.get("audit") != "escalate":
        checks["covered_parts"] = set(exp.get("covered", [])) <= covered
        checks["exclusions"] = all(any(e.lower().split()[0] in n for n in not_cov) for e in exp.get("not_covered", []))
    t = (v.get("estimate") or {}).get("totals") or {}
    return {"name": name, "outcome": outcome, "expected": exp.get("audit"), "checks": checks,
            "pass": all(checks.values()), "secs": round(secs, 1),
            "payout": f"{t.get('payable_low', 0):,}-{t.get('payable_high', 0):,}", "trail": " > ".join(v.get("trail", []))}


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.parent.name for p in DEMO.glob("*/claim.json"))
    rows = []
    for n in names:
        try:
            rows.append(run(n))
        except Exception as e:  # noqa: BLE001
            rows.append({"name": n, "pass": False, "outcome": f"ERROR {e}", "expected": "-", "secs": 0, "payout": "-", "checks": {}})
    print("\n" + "=" * 90)
    for r in rows:
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['name']:<24} outcome={r['outcome']:<9} expected={r['expected']:<9} "
              f"{r['secs']:>5}s  payout Rs {r['payout']}  {r['checks']}")
    ok = sum(r["pass"] for r in rows)
    print(f"\nAgreement with answer key: {ok}/{len(rows)} = {100 * ok / max(len(rows), 1):.0f}%   (mock={config.LLM_MOCK})")
