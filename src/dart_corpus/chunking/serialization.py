"""ChunkSet 직렬화 — data/chunks/{strategy_name}/{doc_id}.jsonl (workstream_a_documentir_contract.md
§직렬화 형식과 동일한 레이아웃을 chunk 레벨에 적용)."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from dart_corpus.chunking.chunk_ir import Chunk, ChunkSet


def chunk_to_dict(chunk: Chunk) -> dict:
    return asdict(chunk)


def chunk_from_dict(d: dict) -> Chunk:
    return Chunk(
        chunk_id=d["chunk_id"], doc_id=d["doc_id"], strategy_name=d["strategy_name"],
        chunk_index=d["chunk_index"], text=d["text"], token_count=d["token_count"],
        source_node_ids=list(d.get("source_node_ids", [])),
        source_section_ids=list(d.get("source_section_ids", [])),
        evidence_ids=list(d.get("evidence_ids", [])),
        section_path=list(d.get("section_path", [])),
    )


def write_chunk_set_jsonl(chunk_set: ChunkSet, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for c in chunk_set.chunks:
            f.write(json.dumps(chunk_to_dict(c), ensure_ascii=False) + "\n")


def read_chunk_set_jsonl(path: Path, doc_id: str, strategy_name: str) -> ChunkSet:
    chunks = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunks.append(chunk_from_dict(json.loads(line)))
    return ChunkSet(doc_id=doc_id, strategy_name=strategy_name, chunks=chunks)
