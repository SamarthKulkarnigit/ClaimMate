"""Single entry point for every LLM call.

- JSON mode + tolerant parsing
- retries, then falls back to the next model in the list
- on-disk cache keyed by (model, messages, images) -> instant demo replays
- LLM_MOCK=1 returns the provided `mock` value without any network call
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

from backend import config


class LLMError(RuntimeError):
    pass


def _encode_image(path: str | Path, max_side: int = 1024) -> str:
    """Downscale + JPEG-encode an image to keep vision calls fast."""
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _parse_json(text: str) -> Any:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if m:
            return json.loads(m.group(1))
        raise


def _cache_key(model: str, messages: list, images: list[str]) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(json.dumps(messages, sort_keys=True).encode())
    for img in images:
        h.update(hashlib.sha256(img.encode()).digest())
    return h.hexdigest()


def chat_json(
    system: str,
    user: str,
    *,
    models: list[str] | None = None,
    images: list[str | Path] | None = None,
    mock: Any = None,
    retries: int = 2,
    use_cache: bool = True,
) -> Any:
    """Ask a model for JSON. Returns the parsed object."""
    if config.LLM_MOCK:
        if mock is None:
            raise LLMError("LLM_MOCK=1 but no mock value supplied")
        return mock

    if not config.OLLAMA_API_KEY:
        raise LLMError("OLLAMA_API_KEY missing in .env")

    models = models or config.TEXT_MODELS
    imgs_b64 = [_encode_image(p) for p in (images or [])]
    messages = [
        {"role": "system", "content": system + "\nRespond with ONE valid JSON object only. No prose, no markdown."},
        {"role": "user", "content": user},
    ]

    last_err: Exception | None = None
    for model in models:
        key = _cache_key(model, messages, imgs_b64)
        cache_file = config.CACHE_DIR / f"{key}.json"
        if use_cache and cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))

        msgs = [dict(m) for m in messages]
        if imgs_b64:
            msgs[-1]["images"] = imgs_b64
        payload = {"model": model, "messages": msgs, "stream": False, "format": "json",
                   "options": {"temperature": 0.1}}

        for attempt in range(retries + 1):
            try:
                r = httpx.post(
                    f"{config.OLLAMA_HOST}/api/chat",
                    headers={"Authorization": f"Bearer {config.OLLAMA_API_KEY}"},
                    json=payload,
                    timeout=config.LLM_TIMEOUT,
                )
                if r.status_code == 429:
                    time.sleep(2 * (attempt + 1))
                    raise LLMError(f"{model}: rate limited")
                r.raise_for_status()
                content = r.json().get("message", {}).get("content", "")
                data = _parse_json(content)
                if use_cache:
                    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            except Exception as e:  # noqa: BLE001 - we want to try the next model
                last_err = e
        # try next model
    raise LLMError(f"All models failed: {last_err}")
