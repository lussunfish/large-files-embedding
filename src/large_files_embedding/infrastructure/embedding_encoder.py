"""Ollama dense encoder plus hashed sparse tokens for BM25-style search."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

import httpx

from large_files_embedding.domain.document import (
    EncodedEmbedding,
    FailureReason,
    NarrativeIngestError,
    require_nonzero_embedding,
)


class DenseSparseEncoder:
    def __init__(
        self,
        host: str,
        model: str,
        dim: int,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._dim = dim
        self._client = client or httpx.Client(timeout=120.0)

    @classmethod
    def from_env(cls) -> DenseSparseEncoder:
        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        model = os.environ.get("EMBEDDING_MODEL", "qwen3-embedding:4b")
        dim = int(os.environ.get("EMBEDDING_DIM", "2560"))
        return cls(host=host, model=model, dim=dim)

    def encode(self, texts: Sequence[str]) -> list[EncodedEmbedding]:
        if not texts:
            return []
        vectors = self._embed(list(texts))
        encoded: list[EncodedEmbedding] = []
        for text, vector in zip(texts, vectors, strict=True):
            item = EncodedEmbedding(
                dense=tuple(float(value) for value in vector),
                sparse=_sparse_tokens(text),
                model=self._model,
            )
            require_nonzero_embedding(item)
            encoded.append(item)
        return encoded

    def _embed(self, texts: list[str]) -> list[list[float]]:
        payload = {
            "model": self._model,
            "input": texts,
            "dimensions": self._dim,
        }
        try:
            response = self._client.post(f"{self._host}/api/embed", json=payload)
            if response.status_code == 404:
                response = self._client.post(
                    f"{self._host}/api/embeddings",
                    json={"model": self._model, "prompt": texts[0]},
                )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise NarrativeIngestError(FailureReason.PARSE_FAILED) from exc
        embeddings = body.get("embeddings")
        if embeddings is None and "embedding" in body:
            embeddings = [body["embedding"]]
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise NarrativeIngestError(FailureReason.DUMMY_VECTOR)
        return embeddings


_TOKEN = re.compile(r"[0-9A-Za-z]+|[가-힣]+")


def _sparse_tokens(text: str) -> tuple[tuple[int, float], ...]:
    counts: dict[int, float] = {}
    for token in _TOKEN.findall(text):
        key = abs(hash(token)) % 2_147_483_647
        if key == 0:
            key = 1
        counts[key] = counts.get(key, 0.0) + 1.0
    if not counts:
        raise NarrativeIngestError(FailureReason.DUMMY_VECTOR)
    return tuple(counts.items())
