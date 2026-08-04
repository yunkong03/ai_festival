"""대표 파싱 문서 샘플 생성 — B/C handoff 공통 자료(representative_documents.jsonl).

전체 corpus를 다시 돌리지 않고, 카테고리별로 미리 확인된 11건만 개별 파싱한다
(doc_id별 선정 이유는 docs/document_ir_contract.md의 대표 샘플 표 참고).

실행: python3 scripts/generate_handoff_samples.py [--out data/artifacts/handoff/representative_documents.jsonl]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.config import default_corpus_root  # noqa: E402
from dart_corpus.contract.manifest import DocumentRecord, ManifestLoader  # noqa: E402
from dart_corpus.contract.snapshot import derive_corpus_snapshot_id, sha256_of_file  # noqa: E402
from dart_corpus.parsing.canonical_parser import parse_document  # noqa: E402
from dart_corpus.parsing.serialization import document_ir_to_json_line  # noqa: E402

# doc_id -> 선정 이유(카테고리). docs/document_ir_contract.md §대표 샘플 표와 동기화할 것.
SAMPLE_DOC_IDS: dict[str, str] = {
    "periodic_20231114001884": "periodic dart3 + sanitizer 사용 + merged cell + shape mismatch + unknown_section_depth",
    "periodic_20241114001965": "periodic dart4 + TE 셀 태그 우세 + sanitizer 사용",
    "major_20230601000234": "major dart3",
    "major_20251219000396": "major dart4",
    "holding_20230103000123": "holding dart3",
    "holding_20240717000432": "holding dart4",
    "exchange_20230406800008": "exchange HTML-in-.xml + 인코딩 선언 불일치(euc-kr 선언, 실제 utf-8)",
    "periodic_20260513000860": "pdf+viewer HTML(원문 PDF는 파싱 안 하고 보존만, viewer.html이 primary)",
    "periodic_20240312000736": "첨부 포함 문서(n_files=3) + sanitizer 사용(삼성전자 사업보고서)",
    "periodic_20240516000601": "TABLE-GROUP 내부 TITLE 승격 + 다중 header 표 + rowspan/colspan + sanitizer 사용",
    "periodic_20260515002418": "fallback tier(ENG 속성값 내부 미이스케이프 큰따옴표로 XML 파싱 자체 실패)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                     default=Path(__file__).resolve().parent.parent / "data" / "artifacts" / "handoff" / "representative_documents.jsonl")
    args = ap.parse_args()

    root = default_corpus_root()
    # 전체 게이트 체크(build_snapshot_report, 4204건 순회)는 여기서 필요 없다 —
    # corpus_snapshot_id는 manifest/universe 파일 두 개의 해시만으로 결정되므로 가볍게 계산한다.
    manifest_sha256 = sha256_of_file(root / "manifest.jsonl")
    universe_sha256 = sha256_of_file(root / "universe.csv")
    snapshot_id = derive_corpus_snapshot_id(manifest_sha256, universe_sha256)
    print(f"corpus_snapshot_id = {snapshot_id}")

    records_by_id: dict[str, DocumentRecord] = {r.doc_id: r for r in ManifestLoader(root).load()}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for doc_id, reason in SAMPLE_DOC_IDS.items():
            rec = records_by_id.get(doc_id)
            if rec is None:
                print(f"[경고] manifest에 없음: {doc_id} — 건너뜀")
                continue
            ir = parse_document(rec, root)
            ir.corpus_snapshot_id = snapshot_id
            f.write(document_ir_to_json_line(ir) + "\n")
            n_written += 1
            print(f"  {doc_id}: tier={ir.parse_quality.tier} nodes={len(ir.nodes)} — {reason}")

    print(f"\n{n_written}/{len(SAMPLE_DOC_IDS)}건 저장 -> {args.out}")


if __name__ == "__main__":
    main()
