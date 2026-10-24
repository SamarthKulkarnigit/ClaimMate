"""FastAPI app. Run from repo root:  uvicorn backend.app.main:app --reload --port 8000"""
from __future__ import annotations

import asyncio
import json
import shutil
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from backend import config
from backend.agents.graph import GRAPH
from backend.app import events

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
    events.emit(cid, "done" if STATUS[cid] != "awaiting_approval" else "status", "coordinator",
                f"Status: {STATUS[cid]}", {"status": STATUS[cid]})


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
    out = []
    for d in sorted(DEMO_DIR.glob("*/claim.json")):
        c = json.loads(d.read_text(encoding="utf-8"))
        out.append({"name": d.parent.name, "title": c.get("title", d.parent.name), "story": c.get("story"),
                    "expected": c.get("expected")})
    return out


@app.post("/api/demo/{name}")
def run_demo(name: str):
    f = DEMO_DIR / name / "claim.json"
    if not f.exists():
        raise HTTPException(404, "demo not found")
    c = json.loads(f.read_text(encoding="utf-8"))
    cid = _new_id()
    up = config.UPLOADS / cid
    up.mkdir(parents=True, exist_ok=True)
    photos = []
    for i, fn in enumerate(c.get("photos", []), 1):
        src = DEMO_DIR / name / fn
        dst = up / f"P{i}{src.suffix.lower()}"
        shutil.copy(src, dst)
        photos.append({"id": f"P{i}", "path": str(dst), "name": fn})
    mock = c.get("mock", {})
    # remap mock keys from file names to photo ids
    for key in ("damage", "damage_recheck"):
        if isinstance(mock.get(key), dict):
            mock[key] = {p["id"]: mock[key].get(p["name"], mock[key].get(p["id"])) for p in photos}
    state = {"claim_id": cid, "story": c["story"], "accident_date": c["accident_date"], "vehicle": c["vehicle"],
             "policy": c["policy"], "photos": photos, "mock": mock, "retries": 0, "trail": [],
             "meta": {"demo": name, "expected": c.get("expected")}}
    return {"claim_id": _start(state)}


@app.post("/api/claims")
async def create_claim(photos: list[UploadFile] = File(...), story: str = Form(...), accident_date: str = Form(...),
                       vehicle: str = Form(...), policy: str = Form(...)):
    cid = _new_id()
    up = config.UPLOADS / cid
    up.mkdir(parents=True, exist_ok=True)
    plist = []
    for i, f in enumerate(photos, 1):
        dst = up / f"P{i}{Path(f.filename or 'x.jpg').suffix.lower() or '.jpg'}"
        dst.write_bytes(await f.read())
        plist.append({"id": f"P{i}", "path": str(dst), "name": f.filename})
    state = {"claim_id": cid, "story": story, "accident_date": accident_date, "vehicle": json.loads(vehicle),
             "policy": json.loads(policy), "photos": plist, "retries": 0, "trail": [], "meta": {}}
    return {"claim_id": _start(state)}


@app.get("/api/claims/{cid}")
def get_claim(cid: str):
    v = _values(cid)
    if not v:
        raise HTTPException(404, "unknown claim")
    v.pop("mock", None)
    for p in v.get("photos", []):
        p["url"] = f"/api/claims/{cid}/photos/{p['id']}"
    return {"status": STATUS.get(cid, "unknown"), "state": v}


@app.get("/api/claims/{cid}/events")
async def stream(cid: str):
    async def gen():
        i = 0
        while True:
            for ev in events.since(cid, i):
                i += 1
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if STATUS.get(cid) in ("done", "filed", "rejected", "escalated", "error") and not events.since(cid, i):
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(0.25)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class Approval(BaseModel):
    approved: bool
    note: str = ""


@app.post("/api/claims/{cid}/approve")
def approve(cid: str, body: Approval):
    if STATUS.get(cid) != "awaiting_approval":
        raise HTTPException(409, f"claim is {STATUS.get(cid)}")
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
