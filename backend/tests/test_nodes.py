"""Damage Assessor and Auditor behaviour with real (non-mock) vision replies, using a fake LLM."""
import pytest

from backend import config
from backend.agents import nodes
from backend.llm.ollama_client import LLMError


def base_state(n_photos=3, **extra):
    return {"claim_id": "TEST-NODES", "story": "Hit a pole.", "accident_date": "2026-10-23",
            "vehicle": {"model": "Swift", "reg_no": "KA01AB1234", "cc": 1197, "age_months": 30},
            "policy": {"start": "2026-01-01", "end": "2026-12-31", "idv": 500000},
            "photos": [{"id": f"P{i}", "path": f"/nonexistent/P{i}.jpg", "exif_datetime": None} for i in range(1, n_photos + 1)],
            "retries": 0, "trail": [], "meta": {}, **extra}


@pytest.fixture(autouse=True)
def real_mode(monkeypatch):
    monkeypatch.setattr(config, "LLM_MOCK", False)


def test_part_aliases_map_onto_catalogue_keys():
    assert nodes._part_key("Hood") == "bonnet"
    assert nodes._part_key("rear window") == "rear_windshield"
    assert nodes._part_key("Left Tail Light") == "tail_lamp"
    assert nodes._part_key("bumper", "rear") == "rear_bumper"
    assert nodes._part_key("door glass") == "side_window_glass"
    assert nodes._part_key("flux capacitor") is None


def test_vision_failure_is_reported_not_called_no_damage(monkeypatch):
    def fail(*a, **k):
        raise LLMError("All models failed. Last error: gemma4:31b: model not found (HTTP 404)")
    monkeypatch.setattr(nodes, "chat_json", fail)
    state = base_state()
    state.update(nodes.damage(state))
    assert state["damages"] == [] and all(q.get("error") for q in state["photo_quality"])
    state.update({"coverage": [], "estimate": {"lines": [], "totals": {}}})
    monkeypatch.setattr(nodes, "chat_json", lambda *a, mock=None, **k: mock)  # story check
    audit = nodes.auditor(state)["audit"]
    a6 = next(f for f in audit["findings"] if f["check"] == "A6")
    assert audit["status"] == "escalate" and a6["ok"] is False
    assert "Damage assessment failed for P1, P2 and P3" in a6["detail"] and "HTTP 404" in a6["detail"]
    assert "No damage detected" not in a6["detail"]


def test_missing_exif_is_one_line_for_all_photos(monkeypatch):
    replies = {"P1": {"parts": [{"part": "hood", "side": "front", "severity": "moderate", "action": "repair", "confidence": 0.9}],
                      "quality": "ok"},
               "P2": {"parts": [{"part": "Rear Window", "side": "rear", "severity": "severe", "action": "replace",
                                 "confidence": 0.8}, {"part": "spoiler", "side": "rear"}], "quality": "ok"}}
    monkeypatch.setattr(nodes, "chat_json", lambda system, user, images=None, mock=None, **k:
                        replies[images[0].split("/")[-1][:2]] if images else mock)
    state = base_state(2)
    state.update(nodes.damage(state))
    assert {d["part"] for d in state["damages"]} == {"bonnet", "rear_windshield"}
    state.update(nodes.cost({**state, "coverage": [{"part": d["part"], "status": "covered", "clause_id": "S1.PERIL.vi"}
                                                   for d in state["damages"]]}))
    state["coverage"] = []
    a1 = next(f for f in nodes.auditor(state)["audit"]["findings"] if f["check"] == "A1")
    assert a1["detail"].count("No EXIF") == 1 and "P1 and P2" in a1["detail"]
