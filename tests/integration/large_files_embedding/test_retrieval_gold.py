"""Retrieval gold eval against ingested PDFs. Skip if infra or corpus is down."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path

import pytest

from large_files_embedding.application.serve_mcp import ServeMcp
from large_files_embedding.domain.document import NO_EVIDENCE
from large_files_embedding.infrastructure.embedding_encoder import DenseSparseEncoder
from large_files_embedding.infrastructure.mariadb_table_store import MariaDbTableStore
from large_files_embedding.infrastructure.milvus_chunk_store import MilvusChunkStore

_GOLD_PATH = Path(__file__).resolve().parents[2] / "eval" / "pdf_gold.json"


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _ollama_has_model() -> bool:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:11434/api/tags", timeout=2
        ) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return False
    names = [str(item.get("name", "")) for item in payload.get("models", [])]
    return any(
        name == "qwen3-embedding:4b" or name.startswith("qwen3-embedding:4b")
        for name in names
    )


def _infra_skip_reason() -> str | None:
    missing: list[str] = []
    if not _http_ok("http://127.0.0.1:9091/healthz"):
        missing.append("milvus")
    if not _port_open("127.0.0.1", 19530):
        missing.append("milvus-grpc")
    if not _port_open("127.0.0.1", 3306):
        missing.append("mariadb")
    if not _ollama_has_model():
        missing.append("ollama:qwen3-embedding:4b")
    if missing:
        return "01-stable/ollama down: " + ", ".join(missing)
    return None


def _load_gold() -> dict[str, object]:
    return json.loads(_GOLD_PATH.read_text(encoding="utf-8"))


def _search_cases() -> list[dict[str, object]]:
    gold = _load_gold()
    cases = gold.get("cases", [])
    assert isinstance(cases, list)
    return [case for case in cases if isinstance(case, dict)]


@pytest.fixture(scope="module")
def retrieval() -> ServeMcp:
    reason = _infra_skip_reason()
    if reason is not None:
        pytest.skip(reason)
    uc = ServeMcp(
        MilvusChunkStore.from_env(),
        MariaDbTableStore.from_env(),
        DenseSparseEncoder.from_env(),
    )
    listing = uc.list_documents()
    gold = _load_gold()
    documents = gold.get("documents", [])
    assert isinstance(documents, list)
    names = [
        str(item.get("filename_substr", ""))
        for item in documents
        if isinstance(item, Mapping)
    ]
    if not any(name and name in listing for name in names):
        pytest.skip("sample pdf corpus not ingested")
    return uc


def test_list_documents_includes_gold_pdfs(retrieval: ServeMcp) -> None:
    listing = retrieval.list_documents()
    gold = _load_gold()
    documents = gold.get("documents", [])
    assert isinstance(documents, list)
    names = [
        str(item.get("filename_substr", ""))
        for item in documents
        if isinstance(item, Mapping) and item.get("filename_substr")
    ]
    queries = {
        str(case.get("expect", {}).get("filename_substr") or ""): str(
            case.get("query") or ""
        )
        for case in _search_cases()
        if isinstance(case.get("expect"), Mapping)
    }
    still_missing: list[str] = []
    for name in names:
        if name in listing:
            continue
        if name in retrieval.search_passages(name):
            continue
        extra = queries.get(name, "")
        if extra and name in retrieval.search_passages(extra):
            continue
        still_missing.append(name)
    assert still_missing == [], (
        f"gold pdfs missing from list_documents and search_passages: {still_missing}"
    )


@pytest.mark.parametrize(
    "case",
    _search_cases(),
    ids=lambda case: str(case.get("id", "case")),
)
def test_search_passages_gold_case(
    retrieval: ServeMcp, case: Mapping[str, object]
) -> None:
    assert case.get("tool") == "search_passages"
    query = str(case.get("query") or "")
    expect = case.get("expect")
    assert isinstance(expect, Mapping)
    result = retrieval.search_passages(query)
    if expect.get("no_evidence"):
        assert result == NO_EVIDENCE
        return
    needle = str(expect.get("filename_substr") or "")
    assert needle
    assert needle in result, result[:500]
    assert "page=" in result or "slide=" in result, result[:300]
    haystack = result.lower()
    for token in expect.get("must_contain") or []:
        assert str(token).lower() in haystack, f"{token!r} not in hits"
