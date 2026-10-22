"""A dependency-free vector index.

Uses signed hashing embeddings so the demo runs offline. Swap `embed()` for a
real embedding model (OpenAI, Cohere, local sentence-transformers) and the rest
of the retrieval contract stays identical.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from .corpus import DOCS

DIM = 384
_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-']+")
STOP = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has",
    "have", "not", "but", "any", "all", "per", "into", "must", "may", "can", "will",
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP and len(t) > 2]


def embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    tokens = tokenize(text)
    for i, token in enumerate(tokens):
        digest = int(hashlib.blake2b(token.encode(), digest_size=8).hexdigest(), 16)
        vec[digest % DIM] += 1.0 if (digest >> 17) & 1 else -1.0
        if i + 1 < len(tokens):
            bigram = f"{token}_{tokens[i + 1]}"
            d2 = int(hashlib.blake2b(bigram.encode(), digest_size=8).hexdigest(), 16)
            vec[d2 % DIM] += 0.5 if (d2 >> 19) & 1 else -0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    title: str
    tags: tuple[str, ...]
    text: str
    vector: list[float]


def _chunks() -> list[Chunk]:
    out: list[Chunk] = []
    for doc in DOCS:
        sentences = re.split(r"(?<=[.!?])\s+", doc["text"].strip())
        buf: list[str] = []
        size = 0
        for sentence in sentences:
            if size + len(sentence) > 320 and buf:
                text = " ".join(buf)
                out.append(Chunk(f"{doc['id']}#{len(out)}", doc["id"], doc["title"], tuple(doc["tags"]), text, embed(text)))
                buf, size = [], 0
            buf.append(sentence)
            size += len(sentence)
        if buf:
            text = " ".join(buf)
            out.append(Chunk(f"{doc['id']}#{len(out)}", doc["id"], doc["title"], tuple(doc["tags"]), text, embed(text)))
    return out


class VectorIndex:
    def __init__(self) -> None:
        self.chunks = _chunks()

    def search(self, query: str, k: int = 4, tag: str | None = None) -> list[dict]:
        if not query.strip():
            return []
        q = embed(query)
        pool = [c for c in self.chunks if not tag or tag in c.tags]
        scored = sorted(((cosine(q, c.vector), c) for c in pool), key=lambda pair: pair[0], reverse=True)
        results = []
        for score, chunk in scored[:k]:
            results.append(
                {
                    "id": chunk.id,
                    "doc_id": chunk.doc_id,
                    "title": chunk.title,
                    "tags": list(chunk.tags),
                    "text": chunk.text,
                    "score": round(max(score, 0.0), 4),
                }
            )
        return results

    def stats(self) -> dict:
        return {
            "documents": len(DOCS),
            "chunks": len(self.chunks),
            "dimensions": DIM,
            "embedding": "signed-hashing (offline baseline)",
        }


index = VectorIndex()
