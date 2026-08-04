"""Canonical hash — 재현성 검증용. DocumentIR을 실행 환경/시각과 무관하게 항상 같은
해시로 만든다(SHA-256, JSON key sort, whitespace 제거, UTF-8). Python 내장 hash()는
프로세스마다 시드가 달라질 수 있어(PYTHONHASHSEED) persistent ID/hash에 쓰면 안 된다 —
여기서는 hashlib.sha256만 쓴다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CANONICALIZATION_VERSION = "v1"
HASH_ALGORITHM = "sha256"


def canonical_json_bytes(obj) -> bytes:
    """key sort + 구분자 공백 제거 + UTF-8. 같은 내용이면 dict key 삽입 순서와 무관하게
    항상 같은 바이트를 낸다."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def document_ir_hash_from_dict(d: dict) -> str:
    """이미 dict로 로드된 DocumentIR(예: jsonl에서 읽은 한 줄을 json.loads한 것)의
    canonical hash. 8.61GB 전체를 다시 파싱/재구성하지 않고 스트리밍으로 계산할 때 쓴다."""
    return sha256_hex(canonical_json_bytes(d))


def document_ir_hash(ir) -> str:
    """DocumentIR 객체를 직접 받는 편의 함수(document_ir_to_dict를 내부에서 호출)."""
    from dart_corpus.parsing.serialization import document_ir_to_dict

    return document_ir_hash_from_dict(document_ir_to_dict(ir))


def aggregate_hash(doc_id_hash_pairs: list[tuple[str, str]]) -> str:
    """(doc_id, document_ir_hash) 목록을 doc_id로 정렬한 뒤 canonical hash. 입력 리스트
    순서와 무관(내부에서 정렬) — doc_group별 group_artifact_hash, 전체 corpus_document_ir_hash
    양쪽 다 이 함수로 계산한다."""
    sorted_pairs = sorted(doc_id_hash_pairs, key=lambda p: p[0])
    return sha256_hex(canonical_json_bytes(sorted_pairs))


def compute_parser_config_hash(module_paths: list[Path]) -> str:
    """파싱 로직 소스 파일들의 바이트를 정렬된 경로 순으로 이어붙여 해시. parser_version을
    수동으로 안 올려도 로직이 바뀌면 이 값이 자동으로 바뀌는 안전망(§document_ir_contract.md
    parser_version 관리 방식 gap 대응)."""
    concatenated = b"".join(p.read_bytes() for p in sorted(module_paths, key=str))
    return sha256_hex(concatenated)
