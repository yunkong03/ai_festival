"""document_ir_hash_manifest.json 생성 — 8.61GB document_ir/*.jsonl을 스트리밍으로
한 줄씩 읽어 canonical hash만 계산한다(전체 파일을 메모리에 올리지 않음). 이 작은
manifest만 있으면 두 환경에서 만든 DocumentIR이 바이트 단위까지는 아니어도
의미(semantic) 단위로 동일한지 8.61GB를 다시 읽지 않고 비교할 수 있다.

실행: python3 scripts/compute_document_ir_hashes.py [--out-dir data/artifacts]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.parsing.canonical_hash import (  # noqa: E402
    CANONICALIZATION_VERSION, HASH_ALGORITHM, aggregate_hash, compute_parser_config_hash,
    document_ir_hash_from_dict,
)
from dart_corpus.parsing.document_ir import DOCUMENTIR_SCHEMA_VERSION, PARSER_VERSION  # noqa: E402

_DOC_GROUPS = ["periodic", "major", "exchange", "holding"]

# 파싱 "의미"를 결정하는 소스 파일들 — 여기 바이트가 하나라도 바뀌면 parser_config_hash가
# 바뀐다(parser_version을 수동으로 안 올려도 잡아내는 안전망).
_PARSER_MODULE_NAMES = [
    "document_ir.py", "canonical_parser.py", "section_builder.py", "table_serializer.py",
    "encoding.py", "sniff.py", "ids.py", "serialization.py",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data" / "artifacts")
    ap.add_argument("--document-ir-dir", type=Path, default=None, help="기본값: <out-dir>/document_ir")
    ap.add_argument("--corpus-snapshot-path", type=Path, default=None, help="기본값: <out-dir>/corpus_snapshot.json")
    args = ap.parse_args()

    document_ir_dir = args.document_ir_dir or (args.out_dir / "document_ir")
    snapshot_path = args.corpus_snapshot_path or (args.out_dir / "corpus_snapshot.json")

    with open(snapshot_path, encoding="utf-8") as f:
        corpus_snapshot_id = json.load(f)["corpus_snapshot_id"]

    parsing_dir = Path(__file__).resolve().parent.parent / "src" / "dart_corpus" / "parsing"
    parser_config_hash = compute_parser_config_hash([parsing_dir / name for name in _PARSER_MODULE_NAMES])

    group_counts: dict[str, int] = {}
    group_hashes: dict[str, str] = {}
    all_pairs: list[tuple[str, str]] = []

    for group in _DOC_GROUPS:
        path = document_ir_dir / f"{group}.jsonl"
        if not path.exists():
            print(f"[경고] 없음: {path} — 건너뜀")
            continue
        pairs: list[tuple[str, str]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                pairs.append((d["doc_id"], document_ir_hash_from_dict(d)))
        group_counts[group] = len(pairs)
        group_hashes[group] = aggregate_hash(pairs)
        all_pairs.extend(pairs)
        print(f"{group}: {len(pairs)}건 해시 완료")

    corpus_document_ir_hash = aggregate_hash(all_pairs)

    manifest = {
        "corpus_snapshot_id": corpus_snapshot_id,
        "parser_version": PARSER_VERSION,
        "parser_config_hash": parser_config_hash,
        "document_ir_schema_version": DOCUMENTIR_SCHEMA_VERSION,
        "total_documents": len(all_pairs),
        "group_counts": group_counts,
        "group_hashes": group_hashes,
        "corpus_document_ir_hash": corpus_document_ir_hash,
        "hash_algorithm": HASH_ALGORITHM,
        "canonicalization_version": CANONICALIZATION_VERSION,
    }

    out_path = args.out_dir / "handoff" / "document_ir_hash_manifest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\ntotal_documents={len(all_pairs)}")
    print(f"corpus_document_ir_hash={corpus_document_ir_hash}")
    print(f"저장: {out_path}")


if __name__ == "__main__":
    main()
