"""Corpus Snapshot pilot 실행 — 파싱 게이트. Parser는 아직 안 부름(스키마버전만 peek).

실행: python3 scripts/run_corpus_snapshot.py [--json OUT_PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.config import default_corpus_root  # noqa: E402
from dart_corpus.contract.snapshot import build_snapshot_report, validate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None, help="리포트를 json으로 저장할 경로")
    args = ap.parse_args()

    root = default_corpus_root()
    print(f"corpus root: {root}")
    report = build_snapshot_report(root)

    print(f"\nmanifest_row_count = {report.manifest_row_count} (기대 4204, ok={report.manifest_row_count_ok})")
    print(f"universe_row_count = {report.universe_row_count} (기대 70, ok={report.universe_row_count_ok})")
    print(f"file_format_histogram = {report.file_format_histogram}")
    print(f"doc_group_histogram = {report.doc_group_histogram}")
    print(f"schema_version_histogram = {report.schema_version_histogram}")
    print(f"n_files_mismatch = {len(report.n_files_mismatch)}건 {report.n_files_mismatch[:10]}")
    print(f"path_resolution_failures = {len(report.path_resolution_failures)}건 {report.path_resolution_failures[:10]}")
    print(f"major_doc_subtype_all_blank = {report.major_doc_subtype_all_blank}")
    print(f"corp_code_leading_zero_ok = {report.corp_code_leading_zero_ok}")

    problems = validate(report)
    print(f"\n=== 게이트 판정: {'통과' if not problems else '실패'} ===")
    for p in problems:
        print(f"  - {p}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, ensure_ascii=False, indent=2)
        print(f"\n저장: {args.json}")

    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
