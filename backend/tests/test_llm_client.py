import httpx
import pytest

from backend import config
from backend.llm import ollama_client as oc


class Resp:
    def __init__(self, status, content='{"ok": true}'):
        self.status_code, self.text, self._content = status, content, content

    def json(self):
        return {"message": {"content": self._content}}


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LLM_MOCK", False)
    monkeypatch.setattr(config, "OLLAMA_API_KEY", "test-key")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(oc.time, "sleep", lambda s: None)
    calls = []

    def install(replies):
        def post(url, json, **kw):
            calls.append(json["model"])
            reply = replies[json["model"]]
            r = reply.pop(0) if isinstance(reply, list) else reply
            if isinstance(r, Exception):
                raise r
            return r
        monkeypatch.setattr(oc.httpx, "post", post)
        return calls
    return install


def test_bad_key_stops_immediately(live):
    calls = live({"a": Resp(401), "b": Resp(200)})
    with pytest.raises(oc.LLMError, match="OLLAMA_API_KEY"):
        oc.chat_json("s", "u", models=["a", "b"], use_cache=False)
    assert calls == ["a"]


def test_unknown_model_falls_through_without_retries(live):
    calls = live({"missing": Resp(404), "good": Resp(200, '{"parts": []}')})
    assert oc.chat_json("s", "u", models=["missing", "good"], use_cache=False) == {"parts": []}
    assert calls == ["missing", "good"]


def test_errors_are_named_in_final_message(live):
    live({"a": Resp(404), "b": [httpx.ReadTimeout("slow")] * 3})
    with pytest.raises(oc.LLMError, match="ReadTimeout"):
        oc.chat_json("s", "u", models=["a", "b"], use_cache=False)


def test_non_object_reply_is_retried(live):
    calls = live({"a": [Resp(200, "[1, 2]"), Resp(200, '{"x": 1}')]})
    assert oc.chat_json("s", "u", models=["a"], use_cache=False) == {"x": 1}
    assert calls == ["a", "a"]
