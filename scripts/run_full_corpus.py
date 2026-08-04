"""전체 corpus(4,204건) 파싱 실행 — Corpus Snapshot 검증 + DocumentIR/Parse Audit 산출.

산출물(기본 --out-dir data/artifacts/):
  corpus_snapshot.json       Corpus Snapshot(해시+게이트 리포트)
  document_ir/{doc_group}.jsonl   문서별 DocumentIR(JSONL, doc_group당 1파일)
  parse_audit.jsonl          문서별 Parse Audit(성공한 문서만)
  parse_summary.json         tier/doc_group/warning code 분포 집계
  failed_documents.jsonl     파싱 자체가 예외로 실패한 문서 목록(원인 포함)

실행: python3 scripts/run_full_corpus.py [--out-dir data/artifacts] [--limit N] [--no-hash-source-files]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.config import default_corpus_root  # noqa: E402
from dart_corpus.contract.manifest import ManifestLoader  # noqa: E402
from dart_corpus.contract.snapshot import compute_corpus_snapshot  # noqa: E402
from dart_corpus.parsing.audit import build_parse_audit  # noqa: E402
from dart_corpus.parsing.canonical_parser import parse_document  # noqa: E402
from dart_corpus.parsing.serialization import document_ir_to_json_line  # noqa: E402

_DOC_GROUPS = ["periodic", "major", "exchange", "holding"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data" / "artifacts")
    ap.add_argument("--limit", type=int, default=None, help="디버깅용 — 앞에서 N건만 처리")
    ap.add_argument("--no-hash-source-files", action="store_true",
                     help="corpus snapshot에서 source file별 SHA-256 계산을 건너뛴다(빠른 재실행용)")
    ap.add_argument("--skip-snapshot", action="store_true",
                     help="[디버그 전용] corpus snapshot 단계 자체를 건너뛴다(--limit 스모크 테스트용 — "
                          "--limit은 파싱 루프만 줄이고 snapshot은 항상 전체 코퍼스를 스캔하므로 별도 스위치가 필요)")
    ap.add_argument("--progress-every", type=int, default=200)
    args = ap.parse_args()

    root = default_corpus_root()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_ir_dir = out_dir / "document_ir"
    doc_ir_dir.mkdir(parents=True, exist_ok=True)

    print(f"corpus root: {root}", flush=True)
    print(f"output dir: {out_dir}", flush=True)

    if args.skip_snapshot:
        print("\n[1/2] --skip-snapshot: corpus snapshot 계산 생략(디버그 실행)", flush=True)
        snapshot_id = "snap_debug_skip"
        snapshot = None
    else:
        print("\n[1/2] corpus snapshot 계산 중(manifest/universe/source-file SHA-256, 게이트 검증)...", flush=True)
        t0 = time.perf_counter()
        snapshot = compute_corpus_snapshot(root, hash_source_files=not args.no_hash_source_files)
        snapshot_elapsed = time.perf_counter() - t0
        snapshot_path = out_dir / "corpus_snapshot.json"
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)
        snapshot_id = snapshot.corpus_snapshot_id
        print(f"  corpus_snapshot_id = {snapshot.corpus_snapshot_id}", flush=True)
        print(f"  manifest_row_count = {snapshot.report.manifest_row_count} (ok={snapshot.report.manifest_row_count_ok})", flush=True)
        print(f"  n_documents_verified = {snapshot.n_documents_verified}, n_source_files_hashed = {snapshot.n_source_files_hashed}", flush=True)
        print(f"  소요시간: {snapshot_elapsed:.1f}s -> {snapshot_path}", flush=True)

    docs = ManifestLoader(root).load()
    if args.limit:
        docs = docs[: args.limit]
    print(f"\n[2/2] {len(docs)}건 파싱 시작...")

    group_files = {g: open(doc_ir_dir / f"{g}.jsonl", "w", encoding="utf-8") for g in _DOC_GROUPS}
    audit_f = open(out_dir / "parse_audit.jsonl", "w", encoding="utf-8")
    failed_f = open(out_dir / "failed_documents.jsonl", "w", encoding="utf-8")

    tier_hist = Counter()
    tier_by_group = defaultdict(Counter)
    warning_code_hist = Counter()
    warning_code_by_group = defaultdict(Counter)
    text_ratios = []
    n_success = 0
    n_failed = 0
    failed_doc_ids = []

    t0 = time.perf_counter()
    try:
        for i, doc in enumerate(docs, start=1):
            try:
                ir = parse_document(doc, root)
            except Exception as exc:
                n_failed += 1
                failed_doc_ids.append(doc.doc_id)
                failed_f.write(json.dumps({
                    "doc_id": doc.doc_id, "doc_group": doc.doc_group, "file_path": doc.file_path,
                    "reason": type(exc).__name__, "error": str(exc),
                    "traceback": traceback.format_exc(limit=5),
                }, ensure_ascii=False) + "\n")
                continue

            ir.corpus_snapshot_id = snapshot_id
            group_files[doc.doc_group].write(document_ir_to_json_line(ir) + "\n")

            tier = ir.parse_quality.tier if ir.parse_quality else "unknown"
            tier_hist[tier] += 1
            tier_by_group[doc.doc_group][tier] += 1
            n_success += 1

            try:
                audit = build_parse_audit(doc, ir, root)
            except Exception as exc:
                audit = None
                print(f"  [경고] {doc.doc_id}: parse_audit 계산 실패({type(exc).__name__}: {exc})")

            if audit is not None:
                audit_f.write(json.dumps(audit.to_dict(), ensure_ascii=False) + "\n")
                for code in audit.warning_codes:
                    warning_code_hist[code] += 1
                    warning_code_by_group[doc.doc_group][code] += 1
                if audit.text_preservation_ratio is not None:
                    text_ratios.append(audit.text_preservation_ratio)

            if i % args.progress_every == 0:
                elapsed = time.perf_counter() - t0
                print(f"  {i}/{len(docs)}건 처리({elapsed:.1f}s, {i/elapsed:.1f}건/s) — "
                      f"tier={dict(tier_hist)} failed={n_failed}")
    finally:
        for f in group_files.values():
            f.close()
        audit_f.close()
        failed_f.close()

    elapsed = time.perf_counter() - t0
    avg_ratio = sum(text_ratios) / len(text_ratios) if text_ratios else None

    summary = {
        "corpus_snapshot_id": snapshot_id,
        "total_documents": len(docs),
        "n_success": n_success,
        "n_failed": n_failed,
        "elapsed_s": elapsed,
        "docs_per_s": (len(docs) / elapsed) if elapsed else None,
        "tier_distribution": dict(tier_hist),
        "tier_distribution_by_doc_group": {g: dict(c) for g, c in tier_by_group.items()},
        "warning_code_distribution": dict(warning_code_hist),
        "warning_code_distribution_by_doc_group": {g: dict(c) for g, c in warning_code_by_group.items()},
        "avg_text_preservation_ratio": avg_ratio,
        "failed_doc_ids": failed_doc_ids,
    }
    with open(out_dir / "parse_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n완료: {n_success}/{len(docs)}건 성공, {n_failed}건 실패, {elapsed:.1f}s ({len(docs)/elapsed:.1f}건/s)")
    print(f"tier 분포: {dict(tier_hist)}")
    print(f"경고코드 분포: {dict(warning_code_hist)}")
    if avg_ratio is not None:
        print(f"평균 text_preservation_ratio: {avg_ratio:.3f}")
    print(f"\n저장 위치: {out_dir}")


if __name__ == "__main__":
    main()
