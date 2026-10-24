"""Check that the API key and every configured Ollama model actually answer.

    python -m scripts.check_models

Vision models get one demo photo; text models get a tiny JSON prompt. No cache is used.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config  # noqa: E402
from backend.llm.ollama_client import LLMError, chat_json  # noqa: E402

PHOTO = config.DATA / "demo_claims" / "clean_swift_front" / "photos" / "evidence.jpg"


def probe(model: str, vision: bool) -> tuple[bool, str]:
    t0 = time.time()
    try:
        res = chat_json("Answer in JSON.",
                        'Describe the image in at most five words as {"sees": "..."}' if vision else 'Reply {"ok": true}',
                        models=[model], images=[PHOTO] if vision else None, use_cache=False, retries=0)
        return True, f"{time.time() - t0:.1f}s  {res}"
    except LLMError as e:
        return False, str(e)


if __name__ == "__main__":
    if config.LLM_MOCK:
        print("LLM_MOCK=1: the app never calls models in this mode. Set LLM_MOCK=0 to test them.")
    if not config.OLLAMA_API_KEY or config.OLLAMA_API_KEY == "put_your_key_here":
        sys.exit("OLLAMA_API_KEY is missing in .env")
    config.LLM_MOCK = False
    ok_any = {}
    for group, models, vision in (("VISION_MODELS", config.VISION_MODELS, True),
                                  ("TEXT_MODELS", config.TEXT_MODELS, False),
                                  ("FAST_MODELS", config.FAST_MODELS, False)):
        print(f"\n{group}")
        for m in models:
            ok, detail = probe(m, vision)
            ok_any[group] = ok_any.get(group, False) or ok
            print(f"  {'OK  ' if ok else 'FAIL'} {m:<28} {detail}")
    bad = [g for g in ("VISION_MODELS", "TEXT_MODELS") if not ok_any.get(g)]
    print("\n" + ("All required model groups have a working model." if not bad else
                  f"No working model in {', '.join(bad)}: edit those lists in .env with model names that passed or that your account offers."))
    sys.exit(1 if bad else 0)
