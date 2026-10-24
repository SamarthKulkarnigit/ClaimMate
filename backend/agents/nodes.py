"""All agent nodes. Each returns a partial state update.

Money is never decided by an LLM: Cost Estimator only calls backend.tools.rules.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

from langgraph.types import interrupt

try:
    from langgraph.errors import GraphInterrupt
except ImportError:  # test stubs
    class GraphInterrupt(Exception):
        pass

from backend import config
from backend.app.events import emit
from backend.llm.ollama_client import LLMError, chat_json
from backend.rag import search as rag
from backend.tools import forensics, rules
from backend.agents.state import ClaimState

PARTS = rules.parts_catalog()
PART_KEYS = list(PARTS.keys())

# Names vision models commonly use instead of our part keys.
PART_ALIASES = {
    "hood": "bonnet", "front_hood": "bonnet",
    "front_windshield": "windshield", "windscreen": "windshield", "front_windscreen": "windshield",
    "front_glass": "windshield", "wind_shield": "windshield",
    "rear_window": "rear_windshield", "rear_glass": "rear_windshield", "back_glass": "rear_windshield",
    "rear_windscreen": "rear_windshield", "back_windshield": "rear_windshield", "hatch_glass": "rear_windshield",
    "tail_light": "tail_lamp", "taillight": "tail_lamp", "taillamp": "tail_lamp", "rear_light": "tail_lamp",
    "rear_lamp": "tail_lamp", "headlight": "headlamp", "head_light": "headlamp", "head_lamp": "headlamp",
    "fog_light": "fog_lamp", "fender": "front_fender", "wing": "front_fender", "door": "front_door",
    "driver_door": "front_door", "passenger_door": "front_door", "mirror": "side_mirror",
    "wing_mirror": "side_mirror", "rear_view_mirror": "side_mirror", "wheel": "alloy_wheel", "rim": "alloy_wheel",
    "tire": "tyre", "trunk": "boot_lid", "tailgate": "boot_lid", "hatch": "boot_lid", "boot": "boot_lid",
    "quarter_panel": "rear_quarter_panel", "side_window": "side_window_glass", "door_glass": "side_window_glass",
    "window": "side_window_glass", "door_window": "side_window_glass", "quarter_glass": "side_window_glass",
    "front_grille": "grille",
}


def _part_key(raw, side: str | None = None) -> str | None:
    """Map a vision model's part name onto PART_KEYS; None if it cannot be mapped."""
    k = re.sub(r"[^a-z0-9]+", "_", str(raw or "").lower()).strip("_")
    if k in PARTS:
        return k
    for prefix in ("left_", "right_", "lh_", "rh_"):
        if k.startswith(prefix):
            k = k[len(prefix):]
            if k in PARTS:
                return k
    if k == "bumper":
        return "rear_bumper" if side == "rear" else "front_bumper"
    return PART_ALIASES.get(k)


def agent(name: str):
    """Wrap a node: emit start/end events and keep the visit trail."""
    def deco(fn):
        @wraps(fn)
        def inner(state: ClaimState):
            cid = state["claim_id"]
            emit(cid, "agent_start", name, f"{name} started")
            try:
                out = fn(state) or {}
            except GraphInterrupt:
                raise  # normal pause for human approval, not an error
            except Exception as e:  # noqa: BLE001
                emit(cid, "error", name, f"{name} failed: {e}")
                raise
            out["trail"] = list(state.get("trail") or []) + [name]
            emit(cid, "agent_end", name, out.pop("_summary", f"{name} done"))
            return out
        return inner
    return deco


def _norm_plate(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _mock(state: ClaimState, key: str, default=None):
    return (state.get("mock") or {}).get(key, default)


# --------------------------------------------------------------------------- intake
@agent("intake")
def intake(state: ClaimState):
    cid = state["claim_id"]
    photos = []
    for p in state.get("photos", []):
        info = forensics.inspect_photo(p["path"], claim_id=cid)
        photos.append({**p, **info})
        emit(cid, "message", "intake",
             f"{p['id']}: EXIF {info['exif_datetime'] or 'missing'}"
             + (f", DUPLICATE of {info['duplicate_of']}" if info["duplicate_of"] else ""),
             {"photo": p["id"], **info})
    v = dict(state.get("vehicle") or {})
    if v.get("reg_date") and "age_months" not in v:
        v["age_months"] = rules.age_months(v["reg_date"], state.get("accident_date"))
    return {"photos": photos, "vehicle": v, "retries": state.get("retries", 0),
            "_summary": f"Checked {len(photos)} photos (EXIF + duplicate hash)"}


# --------------------------------------------------------------------------- coordinator
def coordinator(state: ClaimState):
    cid = state["claim_id"]
    audit = state.get("audit")
    retries = state.get("retries", 0)
    upd: dict = {}

    if audit:
        if audit["status"] == "pass":
            nxt, why = "human", "Auditor passed the claim. Asking the owner to approve."
        elif audit["status"] == "escalate":
            nxt, why = "escalate", f"Auditor escalated: {audit.get('hint') or 'see findings'}"
        elif retries >= config.MAX_SEND_BACKS:
            nxt, why = "escalate", f"Mismatch persists after {retries} re-check(s). Handing to a human surveyor."
        else:
            nxt = audit.get("send_back_to") or "damage"
            why = f"Auditor objected. Sending work back to {nxt} (re-check {retries + 1}/{config.MAX_SEND_BACKS})."
            upd = {"retries": retries + 1, "hint": audit.get("hint"), "audit": None, "estimate": None}
            if nxt == "damage":
                upd.update({"damages": None, "coverage": None})
            elif nxt == "policy":
                upd.update({"coverage": None})
            emit(cid, "send_back", "coordinator", why, {"to": nxt, "send_back_to": nxt, "retry": retries + 1, "retries": retries + 1})
    elif state.get("damages") is None:
        nxt, why = "damage", "Need damage assessment from photos."
    elif not state.get("damages"):
        # assessed but nothing visible: don't loop back to the vision agent - let the Auditor decide (A6)
        nxt, why = "auditor", "No damage detected in any photo. Auditor must decide whether clearer evidence is needed."
        upd = {"coverage": [], "estimate": {"lines": [], "totals": {}}}
    elif state.get("coverage") is None:
        nxt, why = "policy", "Damage known. Need policy coverage per part."
    elif state.get("estimate") is None:
        nxt, why = "cost", "Coverage known. Need cost estimate."
    else:
        nxt, why = "auditor", "Estimate ready. Auditor must cross-check before the owner sees it."

    emit(cid, "message", "coordinator", why, {"next": nxt})
    trail = list(state.get("trail") or []) + ["coordinator"]
    return {**upd, "next": nxt, "trail": trail}


def route(state: ClaimState) -> str:
    return state["next"]


# --------------------------------------------------------------------------- damage assessor
DAMAGE_SYSTEM = f"""You are an experienced Indian motor insurance damage assessor looking at ONE accident photo of a car.
List every visibly damaged exterior part. Use ONLY these part keys: {", ".join(PART_KEYS)}.
For each part give: part, side (front|rear|left|right), severity (minor|moderate|severe),
action (repair|replace) - plastic lamps/glass that are cracked are 'replace'; small dents/scratches are 'repair',
confidence (0-1), evidence (max 12 words).
Also give: plate (registration number text if readable else null), quality (ok|blurry|not_a_car),
structural: true ONLY if you can clearly SEE deformed A/B pillars, bent chassis rails, deployed airbags or a crushed engine bay / radiator support.
A dented or crumpled bonnet, broken bumper, lamps or glass alone is NOT structural - set false if unsure.
JSON: {{"parts":[...], "plate": null, "quality": "ok", "structural": false}}"""


@agent("damage")
def damage(state: ClaimState):
    cid = state["claim_id"]
    hint = state.get("hint")
    merged: dict[tuple, dict] = {}
    plate, quality, structural = None, [], False

    def assess(ph: dict) -> tuple[dict, str | None]:
        user = "Assess this photo."
        if hint:
            user += f" A re-check was requested by the auditor: {hint} Look carefully at which END of the car (front or rear) is damaged."
        mock_list = _mock(state, "damage", {})
        mock_val = mock_list.get(ph["id"]) if isinstance(mock_list, dict) else None
        if state.get("retries") and _mock(state, "damage_recheck"):
            mock_val = _mock(state, "damage_recheck").get(ph["id"], mock_val)
        try:
            return chat_json(DAMAGE_SYSTEM, user, models=config.VISION_MODELS, images=[ph["path"]],
                             mock=mock_val or {"parts": [], "plate": None, "quality": "ok"}), None
        except LLMError as e:
            return {"parts": [], "plate": None, "quality": "error"}, str(e)

    photos = state.get("photos", [])
    # Photos are independent; assess them concurrently (results stay in photo order).
    with ThreadPoolExecutor(max_workers=max(1, min(4, len(photos)))) as pool:
        results = list(pool.map(assess, photos))

    for ph, (res, err) in zip(photos, results):
        if err:
            emit(cid, "error", "damage", f"Vision failed on {ph['id']}: {err}", {"photo": ph["id"]})
        quality.append({"photo": ph["id"], "quality": res.get("quality", "ok"), **({"error": err} if err else {})})
        plate = plate or res.get("plate")
        structural = structural or bool(res.get("structural"))
        unmapped = []
        for d in res.get("parts") or []:
            if not isinstance(d, dict):
                continue
            part = _part_key(d.get("part"), d.get("side"))
            if not part:
                unmapped.append(str(d.get("part")))
                continue
            key = (part, d.get("side") or PARTS[part]["zone"])
            cur = merged.get(key)
            try:
                conf = float(d.get("confidence", 0.5))
            except (TypeError, ValueError):
                conf = 0.5
            if not cur:
                merged[key] = {"part": part, "side": key[1], "severity": d.get("severity", "moderate"),
                               "action": d.get("action", "replace"), "material": PARTS[part]["material"],
                               "photo_ids": [ph["id"]], "confidence": conf, "evidence": d.get("evidence", "")}
            else:
                cur["photo_ids"].append(ph["id"])
                cur["confidence"] = max(cur["confidence"], conf)
        if err:
            continue
        text = ", ".join(f"{d.get('part')} ({d.get('side')}, {d.get('severity')})" for d in res.get("parts") or [] if isinstance(d, dict))
        if unmapped:
            text += f" [not in parts list, ignored: {', '.join(unmapped)}]"
        emit(cid, "message", "damage", f"{ph['id']}: " + (text or "no damage found"),
             {"photo": ph["id"], "parts": res.get("parts", []), "quality": res.get("quality"), "unmapped": unmapped})

    damages = list(merged.values())
    return {"damages": damages, "plate_read": plate, "photo_quality": quality,
            "meta": {**(state.get("meta") or {}), "structural": structural},
            "hint": None,
            "_summary": f"Found {len(damages)} damaged part(s)" + (f", plate read {plate}" if plate else "")}


# --------------------------------------------------------------------------- policy analyst
POLICY_SYSTEM = """You are a motor insurance policy analyst. Decide coverage for each damaged part using ONLY the clauses given.
status: covered | not_covered | partial. Cite exactly one clause_id from the list. Reason: one plain-English sentence for a car owner.
Also scan the owner's story for any OTHER claimed item that is not a body part (e.g. engine noise, AC not working, personal items)
and decide those too under extra_items.
JSON: {"coverage":[{"part":"...","status":"covered","clause_id":"...","reason":"..."}],
       "extra_items":[{"item":"...","status":"not_covered","clause_id":"...","reason":"..."}]}"""


@agent("policy")
def policy(state: ClaimState):
    cid = state["claim_id"]
    damages = state.get("damages") or []
    story = state.get("story", "")
    pol = state.get("policy") or {}

    retrieved: dict[str, dict] = {}
    for d in damages:
        for c in rag.search(f"{PARTS[d['part']]['name']} {d['material']} accident damage", k=3):
            retrieved[c["id"]] = c
    for c in rag.search(story, k=4):
        retrieved[c["id"]] = c
    if pol.get("zero_dep"):
        c = rag.get_clause("ADDON.ZERO_DEP")
        if c:
            retrieved[c["id"]] = c
    emit(cid, "message", "policy", f"Retrieved {len(retrieved)} clauses: {', '.join(retrieved)}",
         {"clauses": list(retrieved)})

    user = json.dumps({
        "owner_story": story,
        "accident_date": state.get("accident_date"),
        "policy": {k: pol.get(k) for k in ("start", "end", "zero_dep")},
        "damaged_parts": [{"part": d["part"], "name": PARTS[d["part"]]["name"], "severity": d["severity"]} for d in damages],
        "clauses": [{"id": c["id"], "title": c["title"], "text": c["text"]} for c in retrieved.values()],
    }, ensure_ascii=False)

    default_mock = {"coverage": [{"part": d["part"], "status": "covered", "clause_id": "S1.PERIL.vi",
                                  "reason": "Accidental external damage is covered."} for d in damages],
                    "extra_items": []}
    res = chat_json(POLICY_SYSTEM, user, models=config.TEXT_MODELS, mock=_mock(state, "policy", default_mock))

    def _fix(item: dict) -> dict:
        cl = rag.get_clause(item.get("clause_id", "")) or (rag.search(item.get("part") or item.get("item", ""), k=1) or [{}])[0]
        item["clause_id"] = cl.get("id")
        item["clause_title"] = cl.get("title")
        item["clause_quote"] = (cl.get("text") or "")[:240]
        if item.get("status") not in ("covered", "not_covered", "partial"):
            item["status"] = "not_covered"
        return item

    by_part = {c.get("part"): _fix(c) for c in res.get("coverage", [])}
    coverage = []
    for d in damages:
        c = by_part.get(d["part"]) or _fix({"part": d["part"], "status": "covered", "clause_id": "S1.PERIL.vi",
                                            "reason": "Accidental external damage (default)."})
        # tyre rule is deterministic
        if d["part"] == "tyre":
            c.update(_fix({"part": "tyre", "status": "partial", "clause_id": "S1.EXCL.b",
                           "reason": "Tyres are paid at 50% when the car is damaged in the same accident."}))
        coverage.append(c)
    extras = [_fix(x) for x in res.get("extra_items", [])]
    for c in coverage + extras:
        emit(cid, "message", "policy", f"{c.get('part') or c.get('item')}: {c['status']} [{c['clause_id']}]", c)
    n_cov = sum(c["status"] == "covered" for c in coverage)
    return {"coverage": coverage, "extra_items": extras,
            "_summary": f"{n_cov}/{len(coverage)} parts covered, {len(extras)} other item(s) checked"}


# --------------------------------------------------------------------------- cost estimator (tools only)
@agent("cost")
def cost(state: ClaimState):
    cid = state["claim_id"]
    v, pol = state.get("vehicle") or {}, state.get("policy") or {}
    cov = {c["part"]: c for c in state.get("coverage") or []}
    lines = []
    for d in state.get("damages") or []:
        c = cov.get(d["part"], {"status": "not_covered"})
        line = rules.estimate_line(model=v.get("model", ""), part=d["part"], action=d["action"],
                                   material=d["material"], vehicle_age_months=int(v.get("age_months", 0)),
                                   zero_dep=bool(pol.get("zero_dep")), coverage_status=c["status"])
        line.update({"clause_id": c.get("clause_id"), "photo_ids": d["photo_ids"], "side": d["side"],
                     "severity": d["severity"], "confidence": d["confidence"]})
        lines.append(line)
        emit(cid, "message", "cost",
             f"{line['part_name']}: {d['action']}, dep {int(line['dep_pct'] * 100)}%, payable ₹{line['payable_low']:,}–₹{line['payable_high']:,}",
             line)
    t = rules.totals(lines, int(v.get("cc", 1200)), int(pol.get("voluntary_deductible", 0)))
    return {"estimate": {"lines": lines, "totals": t},
            "_summary": f"Estimated payout ₹{t['payable_low']:,}–₹{t['payable_high']:,} (after ₹{t['compulsory_deductible']:,} deductible)"}


# --------------------------------------------------------------------------- auditor
STORY_SYSTEM = """You audit insurance claims. Compare the owner's story with where the photos show damage.
story_zone: which part of THEIR car the story implies was hit (front|rear|left|right|unknown).
damage_zones: zones present in the damage list. consistent: false only if the story clearly implies a different zone.
JSON: {"story_zone":"rear","damage_zones":["front"],"consistent":false,"detail":"one sentence"}"""


def _d(s: str | None):
    if not s:
        return None
    return datetime.fromisoformat(s).date() if "T" in s else date.fromisoformat(s)


@agent("auditor")
def auditor(state: ClaimState):
    cid = state["claim_id"]
    f: list[dict] = []
    pol, v = state.get("policy") or {}, state.get("vehicle") or {}
    acc = _d(state.get("accident_date"))
    start, end = _d(pol.get("start")), _d(pol.get("end"))
    damages = state.get("damages") or []
    est = state.get("estimate") or {}

    def add(check, ok, detail, severity="info", send_back_to=None):
        f.append({"check": check, "ok": ok, "detail": detail, "severity": severity, "send_back_to": send_back_to})
        emit(cid, "message", "auditor", f"{'✔' if ok else '✘'} {check}: {detail}", f[-1])

    # A1 dates
    if acc and start and end and not (start <= acc <= end):
        add("A1 policy period", False, f"Accident {acc} is outside policy period {start}–{end}.", "escalate")
    else:
        add("A1 policy period", True, "Accident date within policy period.")
    no_exif = []
    for ph in state.get("photos", []):
        pd = _d(ph.get("exif_datetime"))
        if not pd:
            no_exif.append(ph["id"])
        elif start and end and not (start <= pd <= end):
            add(f"A1 photo date {ph['id']}", False, f"Photo taken {pd}, outside policy period.", "escalate")
        elif acc and abs((pd - acc).days) > 3:
            add(f"A1 photo date {ph['id']}", False, f"Photo taken {pd}, {abs((pd - acc).days)} days from accident.", "escalate")

    if no_exif:
        add("A1 photo date", True, f"No EXIF capture date on {_ids(no_exif)} (screenshot/forwarded image?) - noted.", "warn")

    # A2 duplicates
    dups = [p for p in state.get("photos", []) if p.get("duplicate_of")]
    if dups:
        add("A2 reused photo", False, f"{len(dups)} photo(s) match earlier claim {dups[0]['duplicate_of']}.", "escalate")
    else:
        add("A2 reused photo", True, "No photo matches earlier claims.")

    # A3 plate
    plate, reg = _norm_plate(state.get("plate_read")), _norm_plate(v.get("reg_no"))
    if plate and reg and plate != reg:
        add("A3 number plate", False, f"Plate in photo '{state.get('plate_read')}' ≠ RC '{v.get('reg_no')}'.", "send_back", "damage")
    else:
        add("A3 number plate", True, "Plate matches RC." if plate else "Plate not readable - skipped.")

    # A4 story vs damage zone
    zones = sorted({d["side"] for d in damages})
    mock_list = _mock(state, "story_check") or []
    mock_val = mock_list[min(state.get("retries", 0), len(mock_list) - 1)] if mock_list else {
        "story_zone": "unknown", "damage_zones": zones, "consistent": True, "detail": "No conflict."}
    try:
        sc = chat_json(STORY_SYSTEM, json.dumps({"story": state.get("story"), "damage": [
            {"part": d["part"], "side": d["side"]} for d in damages]}), models=config.TEXT_MODELS, mock=mock_val)
    except LLMError as e:
        sc = {"consistent": True, "detail": f"Story check unavailable ({e})", "unavailable": True}
    if not sc.get("consistent", True):
        add("A4 story vs photos", False, sc.get("detail", "Story contradicts damage location."), "send_back", "damage")
    elif sc.get("unavailable"):
        add("A4 story vs photos", True, sc["detail"] + " - not verified.", "warn")
    else:
        add("A4 story vs photos", True, sc.get("detail", "Story matches damage."))

    # A5 evidence for every line
    bad = [l["part_name"] for l in est.get("lines", []) if not l.get("photo_ids") or not l.get("clause_id")]
    missing = [l["part_name"] for l in est.get("lines", []) if l.get("price_missing")]
    add("A5 evidence trail", not bad, "Every amount has a photo and a clause." if not bad else f"No evidence for: {', '.join(bad)}",
        "send_back" if bad else "info", "cost" if bad else None)
    proxy = [l["part_name"] for l in est.get("lines", []) if l.get("action") == "replace" and l.get("part_price") and not l.get("price_verified")]
    if missing or proxy:
        add("A5 price source", True, f"No verified catalogue price for {', '.join(missing + proxy)} - proxy/reference price used; garage quote recommended.", "warn")

    # A6 confidence / severity / CTL
    low = [d for d in damages if d["confidence"] < config.LOW_CONFIDENCE]
    pq = state.get("photo_quality") or []
    failed = [q for q in pq if q.get("error")]
    blurry = [q["photo"] for q in pq if q["quality"] != "ok" and not q.get("error")]
    if failed:
        # a vision outage is not evidence about the photos - say what actually happened
        add("A6 assessment", False, f"Damage assessment failed for {_ids([q['photo'] for q in failed])} "
            f"(vision model error: {failed[0]['error'][:160]}). A surveyor must inspect, or fix the model setup and resubmit.", "escalate")
    if not damages and not failed:
        add("A6 confidence", False, "No damage detected in any photo - need clearer photos.", "escalate")
    elif low or blurry:
        add("A6 confidence", False, f"Low confidence on {', '.join(d['part'] for d in low) or 'photos ' + ', '.join(blurry)}. Clearer photo needed.", "escalate")
    elif not failed:
        add("A6 confidence", True, "All detections above confidence threshold.")
    idv = float(pol.get("idv") or 0)
    gross_hi = (est.get("totals") or {}).get("gross_high", 0)
    if (state.get("meta") or {}).get("structural"):
        add("A6 structural damage", False, "Vision flagged possible structural damage (pillars / chassis / airbags / engine bay) - a surveyor must inspect.", "escalate")
    if idv and gross_hi > 0.75 * idv:
        add("A6 total-loss threshold", False, f"Repair estimate up to Rs {gross_hi:,.0f} exceeds 75% of IDV (Rs {idv:,.0f}) - possible constructive total loss (IDV.CTL).", "escalate")

    # verdict (raw findings)
    esc = [x for x in f if not x["ok"] and x["severity"] == "escalate"]
    sb = [x for x in f if not x["ok"] and x["severity"] == "send_back"]
    if esc:
        audit = {"status": "escalate", "findings": f, "hint": esc[0]["detail"]}
    elif sb:
        audit = {"status": "fail", "findings": f, "send_back_to": sb[0]["send_back_to"],
                 "hint": f"{sb[0]['detail']} Owner's story: \"{state.get('story')}\""}
    else:
        audit = {"status": "pass", "findings": f}
    audit["findings"] = _collapse(f)
    audit["raw_findings"] = f
    return {"audit": audit, "_summary": f"Audit {audit['status'].upper()} ({sum(not x['ok'] for x in f)} issue(s))"}


def _ids(ids: list[str]) -> str:
    return ids[0] if len(ids) == 1 else ", ".join(ids[:-1]) + " and " + ids[-1]


def _collapse(f: list[dict]) -> list[dict]:
    """One row per check code (A1..A6): failing details win, warnings shown as ok=None."""
    out = []
    for code in ("A1", "A2", "A3", "A4", "A5", "A6"):
        rows = [x for x in f if x["check"].startswith(code)]
        if not rows:
            continue
        bad = [x for x in rows if not x["ok"]]
        warn = [x for x in rows if x["ok"] and x["severity"] == "warn"]
        pick = bad or warn or rows
        out.append({"check": code, "name": rows[0]["check"][3:],
                    "ok": False if bad else (None if warn else True),
                    "detail": " ".join(dict.fromkeys(x["detail"] for x in pick)),
                    "severity": pick[0]["severity"], "send_back_to": pick[0].get("send_back_to")})
    return out


# --------------------------------------------------------------------------- human-in-the-loop
_ASKED: set[str] = set()

@agent("human")
def human(state: ClaimState):
    cid = state["claim_id"]
    t = (state.get("estimate") or {}).get("totals", {})
    if cid not in _ASKED:
        _ASKED.add(cid)
        emit(cid, "interrupt", "human", "Waiting for owner approval", {"totals": t})
    answer = interrupt({"question": "Approve this claim for filing?", "totals": t})
    approved = bool((answer or {}).get("approved"))
    emit(cid, "message", "human", "Owner approved" if approved else "Owner rejected", answer or {})
    return {"decision": "approved" if approved else "rejected",
            "_summary": "Approved by owner" if approved else "Rejected by owner"}


def after_human(state: ClaimState) -> str:
    return "finalize" if state.get("decision") == "approved" else "end"


# --------------------------------------------------------------------------- finalize / escalate
@agent("finalize")
def finalize(state: ClaimState):
    from backend.tools import claim_file
    cid = state["claim_id"]
    pdf = claim_file.build_pdf(state, status="READY TO FILE")
    email = claim_file.build_email(state)
    ref = f"MOCK-INS-{cid[-6:].upper()}"
    if not (state.get("meta") or {}).get("demo"):  # demo photos are re-used on purpose
        for p in state.get("photos", []):
            forensics.remember(cid, p["phash"], p["id"])
    emit(cid, "message", "finalize", f"Claim file generated, submitted to mock insurer: {ref}", {"ref": ref})
    return {"outputs": {"pdf_path": str(pdf), "email_text": email, "insurer_ref": ref},
            "_summary": f"Filed with mock insurer ({ref})"}


@agent("escalate")
def escalate(state: ClaimState):
    from backend.tools import claim_file
    audit = state.get("audit") or {}
    reasons = [x["detail"] for x in audit.get("findings", []) if x["ok"] is False]
    reasons = reasons or [audit.get("hint") or "Auditor escalation"]
    pdf = claim_file.build_pdf({**state, "escalation": {"reasons": reasons}}, status="ESCALATED TO HUMAN SURVEYOR")
    email = claim_file.build_email(state, escalation_reasons=reasons)
    emit(state["claim_id"], "message", "auditor", "Surveyor hand-off file and email prepared.", {"reasons": reasons})
    return {"escalation": {"reasons": reasons},
            "outputs": {"pdf_path": str(pdf), "email_text": email, "handoff": True},
            "_summary": "Handed to human surveyor: " + "; ".join(reasons[:2])}
