"""FastAPI app. Run from repo root:  uvicorn backend.app.main:app --reload --port 8000"""
from __future__ import annotations

import asyncio
import json
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from backend import config
from backend.agents.graph import GRAPH
from backend.app import events
from backend.app.demo_loader import list_demos, load_demo

app = FastAPI(title="ClaimMate API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STATUS: dict[str, str] = {}
DEMO_DIR = config.DATA / "demo_claims"


def _cfg(cid: str) -> dict:
    return {"configurable": {"thread_id": cid}, "recursion_limit": 60}


def _values(cid: str) -> dict:
    snap = GRAPH.get_state(_cfg(cid))
    return dict(snap.values or {}) if snap else {}


def _settle_status(cid: str) -> None:
    snap = GRAPH.get_state(_cfg(cid))
    v = snap.values or {}
    if snap.next and "human" in snap.next:
        STATUS[cid] = "awaiting_approval"
    elif v.get("escalation"):
        STATUS[cid] = "escalated"
    elif v.get("decision") == "approved":
        STATUS[cid] = "filed"
    elif v.get("decision") == "rejected":
        STATUS[cid] = "rejected"
    else:
        STATUS[cid] = "done"
    if STATUS[cid] == "escalated":
        reasons = (v.get("escalation") or {}).get("reasons", [])
        events.emit(cid, "escalate", "auditor", "Handed to a human surveyor: " + "; ".join(reasons[:2]),
                    {"status": "escalated", "reasons": reasons})
    if STATUS[cid] in ("filed", "rejected", "done"):
        events.emit(cid, "done", "finalize" if STATUS[cid] == "filed" else "coordinator",
                    {"filed": "Claim file ready and filed with the mock insurer.",
                     "rejected": "Owner rejected the estimate. Nothing was filed."}.get(STATUS[cid], "Run complete."),
                    {"status": STATUS[cid]})


def _run(cid: str, payload) -> None:
    STATUS[cid] = "running"
    try:
        GRAPH.invoke(payload, _cfg(cid))
        _settle_status(cid)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        STATUS[cid] = "error"
        events.emit(cid, "error", "coordinator", f"Run failed: {e}", {"status": "error"})


def _start(state: dict) -> str:
    cid = state["claim_id"]
    events.emit(cid, "message", "coordinator", "Claim received. Starting agent team.", {"status": "running"})
    threading.Thread(target=_run, args=(cid, state), daemon=True).start()
    return cid


def _new_id() -> str:
    return "CLM-" + uuid.uuid4().hex[:8].upper()


# ------------------------------------------------------------------ routes
@app.get("/api/health")
def health():
    return {"ok": True, "mock": config.LLM_MOCK, "vision_models": config.VISION_MODELS, "text_models": config.TEXT_MODELS}


@app.get("/api/demo")
def list_demo():
    return list_demos()


@app.post("/api/demo/{name}")
def run_demo(name: str):
    if not (DEMO_DIR / name / "claim.json").exists():
        raise HTTPException(404, "demo not found")
    cid = _new_id()
    return {"claim_id": _start(load_demo(name, cid))}


@app.post("/api/claims")
async def create_claim(request: Request):
    form = await request.form()
    files = [f for f in form.getlist("photos[]") + form.getlist("photos") if hasattr(f, "read")]
    if not files:
        raise HTTPException(422, "at least one photo is required")
    cid = _new_id()
    up = config.UPLOADS / cid
    up.mkdir(parents=True, exist_ok=True)
    plist = []
    for i, f in enumerate(files, 1):
        dst = up / f"P{i}{Path(f.filename or 'x.jpg').suffix.lower() or '.jpg'}"
        dst.write_bytes(await f.read())
        plist.append({"id": f"P{i}", "path": str(dst), "name": f.filename})
    vehicle = json.loads(form.get("vehicle") or "{}")
    vehicle.pop("age_months", None)  # recomputed from reg_date at accident date
    state = {"claim_id": cid, "story": form.get("story", ""), "accident_date": form.get("accident_date"),
             "vehicle": vehicle, "policy": json.loads(form.get("policy") or "{}"), "photos": plist,
             "retries": 0, "trail": [], "meta": {}, "synthetic": False}
    return {"claim_id": _start(state)}


@app.get("/api/claims/{cid}")
def get_claim(cid: str):
    v = _values(cid)
    if not v:
        raise HTTPException(404, "unknown claim")
    v.pop("mock", None)
    v["photos"] = [{**p, "url": f"/api/claims/{cid}/photos/{p['id']}"} for p in v.get("photos", [])]
    # UI lists non-covered items from `coverage`; include story items (e.g. engine noise) there too
    v["coverage"] = list(v.get("coverage") or []) + [
        {**x, "part": x.get("item", "other")} for x in (v.get("extra_items") or [])]
    v["status"] = STATUS.get(cid, "unknown")
    return v


@app.get("/api/claims/{cid}/events")
async def stream(cid: str, request: Request):
    try:
        start_at = int(request.headers.get("last-event-id", "-1")) + 1
    except ValueError:
        start_at = 0

    async def gen():
        i, idle = start_at, 0
        yield "retry: 3000\n\n"
        while not await request.is_disconnected():
            new = events.since(cid, i)
            for ev in new:
                i += 1
                yield f"id: {ev['seq']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            idle = 0 if new else idle + 1
            if idle and idle % 60 == 0:
                yield ": ping\n\n"
            await asyncio.sleep(0.25)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class Approval(BaseModel):
    approved: bool
    note: str = ""


@app.post("/api/claims/{cid}/approve")
def approve(cid: str, body: Approval):
    snap = GRAPH.get_state(_cfg(cid))
    if not (snap and snap.next and "human" in snap.next):
        raise HTTPException(409, f"claim is {STATUS.get(cid)}, not awaiting approval")
    STATUS[cid] = "running"
    threading.Thread(target=_run, args=(cid, Command(resume=body.model_dump())), daemon=True).start()
    return {"ok": True}


@app.get("/api/claims/{cid}/photos/{pid}")
def photo(cid: str, pid: str):
    for p in _values(cid).get("photos", []):
        if p["id"] == pid:
            return FileResponse(p["path"])
    raise HTTPException(404)


@app.get("/api/claims/{cid}/pdf")
def pdf(cid: str):
    path = (_values(cid).get("outputs") or {}).get("pdf_path")
    if not path or not Path(path).exists():
        raise HTTPException(404, "no claim file yet")
    return FileResponse(path, media_type="application/pdf", filename=f"{cid}.pdf")


@app.post("/api/mock-insurer/claims")
def mock_insurer(body: dict):
    return {"reference": "MOCK-INS-" + uuid.uuid4().hex[:6].upper(), "received": True}
