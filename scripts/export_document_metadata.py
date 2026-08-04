"""document_metadata.jsonl 생성 — DocumentIR과 doc_id로 join할 문서 메타데이터.
manifest.jsonl을 그대로 재배포하는 대신, C가 요청한 필드만 골라 작은 JSONL로 만든다
(원본 manifest.jsonl 전체를 다시 안 올려도 되게).

실행: python3 scripts/export_document_metadata.py [--out data/artifacts/handoff/document_metadata.jsonl]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.config import default_corpus_root  # noqa: E402
from dart_corpus.contract.manifest import ManifestLoader  # noqa: E402

_FIELDS = [
    "doc_id", "corp_code", "corp_name", "listed_name", "stock_code", "doc_group",
    "doc_subtype", "derived_subtype", "report_nm", "rcept_no", "rcept_dt",
    "is_correction", "file_format",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                     default=Path(__file__).resolve().parent.parent / "data" / "artifacts" / "handoff" / "document_metadata.jsonl")
    args = ap.parse_args()

    root = default_corpus_root()
    records = ManifestLoader(root).load()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for rec in records:
            row = {k: getattr(rec, k) for k in _FIELDS}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"{len(records)}건 저장 -> {args.out}")


if __name__ == "__main__":
    main()
