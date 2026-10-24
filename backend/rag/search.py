"""Policy clause search: BM25 over curated clauses (+ PDF chunks if the PDF is present).

No embedding API needed. Clause IDs stay exact so every coverage call can cite them.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache

from backend import config

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set("the a an of to in and or is are be by for on with any as at it this that from shall which".split())


def _tok(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.N = len(docs)
        self.avgdl = sum(map(len, docs)) / max(self.N, 1)
        df = Counter(t for d in docs for t in set(d))
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.tf = [Counter(d) for d in docs]

    def scores(self, q: list[str]) -> list[float]:
        out = []
        for tf, d in zip(self.tf, self.docs):
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl))
            out.append(s)
        return out


def _pdf_chunks() -> list[dict]:
    pdf = config.DATA / "policy" / "standard_od_policy.pdf"
    if not pdf.exists():
        return []
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    chunks = []
    for pno, page in enumerate(PdfReader(str(pdf)).pages, 1):
        text = re.sub(r"\s+", " ", page.extract_text() or "")
        # ~120-word windows with overlap
        words = text.split()
        for i in range(0, len(words), 90):
            piece = " ".join(words[i:i + 120])
            if len(piece) > 80:
                chunks.append({"id": f"PDF.p{pno}.{i // 90}", "title": f"Policy wording p.{pno}", "text": piece, "tags": []})
    return chunks


@lru_cache(maxsize=1)
def _index():
    data = json.loads((config.DATA / "policy" / "clauses.json").read_text(encoding="utf-8"))
    clauses = data["clauses"] + _pdf_chunks()
    docs = [_tok(c["title"] + " " + c["text"] + " " + (" ".join(c.get("tags", [])) + " ") * 2) for c in clauses]
    return clauses, BM25(docs), data.get("source", "")


def search(query: str, k: int = 4) -> list[dict]:
    clauses, bm25, _ = _index()
    sc = bm25.scores(_tok(query))
    ranked = sorted(range(len(clauses)), key=lambda i: sc[i], reverse=True)
    return [dict(clauses[i], score=round(sc[i], 3)) for i in ranked[:k] if sc[i] > 0]


def get_clause(clause_id: str) -> dict | None:
    clauses, _, _ = _index()
    return next((c for c in clauses if c["id"] == clause_id), None)


def source() -> str:
    return _index()[2]
