from __future__ import annotations


def make_ir_node_id(doc_id: str, rel_path: str, order_index: int) -> str:
    """결정론적 IR 노드 ID. section_path 문자열을 안 넣는 이유:
    section 추정 규칙이 나중에 바뀌어도 ID가 안정적이어야 재현성이 깨지지 않는다
    (order_index는 XML/HTML 파싱 순서라 규칙과 무관하게 항상 같음)."""
    return f"{doc_id}::{rel_path}::n{order_index}"

# make_chunk_id / make_evidence_id는 이번 Parser Pilot Phase 범위 밖(Chunk를 안 만듦) —
# Chunking Phase에서 chunk_set.py와 함께 추가한다.
