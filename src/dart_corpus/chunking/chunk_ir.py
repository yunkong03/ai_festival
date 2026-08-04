"""ChunkSet — Chunking 전략의 유일한 산출물. DocumentIR을 소비하지만 Parser 코드는
건드리지 않는다(별도 레이어). 모든 chunking 전략(Fixed Token, 이후 Section-aware 등)이
이 타입을 공유한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    strategy_name: str
    chunk_index: int
    text: str
    token_count: int
    source_node_ids: list[str] = field(default_factory=list)
    source_section_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    # 추적용 metadata만 — Fixed baseline은 검색/청킹 로직에서 이 값을 참조하지 않는다.
    section_path: list[str] = field(default_factory=list)


@dataclass
class ChunkSet:
    doc_id: str
    strategy_name: str
    chunks: list[Chunk] = field(default_factory=list)
