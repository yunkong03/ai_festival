"""Chunk ID — 모든 chunking 전략이 공유하는 deterministic ID 규칙. 입력(doc_id,
strategy_name, chunk_index)이 같으면 항상 같은 chunk_id가 나온다(랜덤 요소 없음)."""
from __future__ import annotations


def make_chunk_id(doc_id: str, strategy_name: str, chunk_index: int) -> str:
    return f"{doc_id}::{strategy_name}::c{chunk_index}"
