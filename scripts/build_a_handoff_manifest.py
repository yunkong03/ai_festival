"""a_handoff_manifest.json 생성 — Workstream A가 B/C에 넘기는 handoff의 단일 색인.
corpus_snapshot.json / parse_summary.json / document_ir_hash_manifest.json이 먼저
생성되어 있어야 한다(scripts/run_full_corpus.py, scripts/compute_document_ir_hashes.py).

실행: python3 scripts/build_a_handoff_manifest.py [--out-dir data/artifacts]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.contract.snapshot import sha256_of_file  # noqa: E402
from dart_corpus.parsing.document_ir import DOCUMENTIR_SCHEMA_VERSION, PARSER_VERSION  # noqa: E402

HANDOFF_VERSION = "1.0"

KNOWN_GAPS = [
    "section_path/table_group_id/row_id/xml_xpath/page_number/file_role enum 필드가 파서에 없음 — "
    "docs/document_ir_contract.md 유도 규칙 및 gap 표 참고",
    "ParserWarning에 recoverable/recovery_used/details/parser_version/source_locator 필드 없음",
    "parse_quality.tier에 'failed' 값 없음(별도 개념 — failed_documents.jsonl로 분리)",
    "router_fallback_parser warning code는 정의만 되어 있고 실제로 발생하지 않는 예약 코드",
    "periodic 문서 100%(1054/1054)가 structured가 아님(partial 975 + fallback 79) — 원인 분해: "
    "sanitizer로 인한 partial 972건(text_preservation_ratio 평균 1.02, 실질 손실 없음), "
    "pdf+html 강제 partial 3건(ratio 평균 0.30, 실손실), fallback 79건(ratio 평균 0.14, 실손실 — "
    "20000자 절단 포함). 상세: docs/document_ir_contract.md §periodic parse quality",
    "dependency 버전이 pyproject.toml에 범위(>=)로만 고정됨 — requirements-lock.txt로 현재 환경 스냅샷만 "
    "제공(패키지 관리자 lock file 아님), 완전한 byte reproducibility는 이 lock file을 그대로 쓸 때만 보장",
    "byte reproducibility(동일 JSONL 바이트 스트림)는 아직 두 개의 서로 다른 환경에서 실제로 재실행해 "
    "검증한 적 없음(단일 실행만 존재) — semantic reproducibility(canonical hash 일치)만 설계/구현됨",
    "code_revision은 최초 git commit 이후에 채워야 함(이 manifest 생성 시점엔 git 저장소가 없었음)",
]


def _git_revision() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data" / "artifacts")
    args = ap.parse_args()
    out_dir = args.out_dir
    repo_root = Path(__file__).resolve().parent.parent

    with open(out_dir / "corpus_snapshot.json", encoding="utf-8") as f:
        snapshot = json.load(f)
    with open(out_dir / "parse_summary.json", encoding="utf-8") as f:
        summary = json.load(f)
    with open(out_dir / "handoff" / "document_ir_hash_manifest.json", encoding="utf-8") as f:
        hash_manifest = json.load(f)

    corpus_root = repo_root / "data" / "3.공시" / "corpus"
    manifest_sha256 = sha256_of_file(corpus_root / "manifest.jsonl")
    universe_sha256 = sha256_of_file(corpus_root / "universe.csv")

    manifest = {
        "handoff_version": HANDOFF_VERSION,
        "corpus_snapshot_id": snapshot["corpus_snapshot_id"],
        "manifest_sha256": manifest_sha256,
        "universe_sha256": universe_sha256,
        "parser_version": PARSER_VERSION,
        "document_ir_schema_version": DOCUMENTIR_SCHEMA_VERSION,
        "parser_config_hash": hash_manifest["parser_config_hash"],
        "code_revision": _git_revision(),
        "total_documents": summary["total_documents"],
        "doc_group_counts": snapshot["report"]["doc_group_histogram"],
        "schema_path": "schemas/document_ir_schema_v0.json",
        "contract_path": "docs/document_ir_contract.md",
        "representative_sample_path": "data/artifacts/handoff/representative_documents.jsonl",
        "parse_summary_path": "data/artifacts/parse_summary.json",
        "full_document_ir_in_git": False,
        "full_document_ir_local_path": "data/artifacts/document_ir/{periodic,major,exchange,holding}.jsonl",
        "regenerate_command": "PYTHONIOENCODING=utf-8 python3 scripts/run_full_corpus.py --out-dir data/artifacts",
        "validation_status": {
            "unit_integration_tests": "102 passed, 3 deselected(@integration) — pytest -m 'not integration'",
            "schema_validation": "11/11 representative_documents.jsonl entries valid against document_ir_schema_v0.json",
            "parse_run": f"{summary['n_success']}/{summary['total_documents']} success, "
                          f"{summary['n_failed']} failed(failed_documents.jsonl)",
            "semantic_reproducibility": "설계/구현 완료(document_ir_hash_manifest.json) — canonical hash로 두 실행 비교 가능",
            "byte_reproducibility": "미검증(단일 실행만 존재, 두 환경 교차검증 안 함)",
        },
        "known_gaps": KNOWN_GAPS,
        "schema_stability_note": (
            "schema_version=1.0 / parser_version=1.0.0은 이번 단계 확정 입력 계약으로 써도 됨 — "
            "현재 변경 예정 없음. 향후 필드 추가/의미 변경이 생기면 버전을 올리고 변경 내용·시점을 "
            "이 필드와 docs/document_ir_contract.md §parser_version 관리 방식에 반영해 공지한다."
        ),
    }

    out_path = out_dir / "handoff" / "a_handoff_manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"저장: {out_path}")
    print(f"code_revision = {manifest['code_revision']!r} (git 저장소 없으면 null — commit 후 재생성 권장)")


if __name__ == "__main__":
    main()
