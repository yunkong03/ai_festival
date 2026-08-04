"""Parser Pilot — 실제 corpus 샘플(층화표본, doc_group당 N건)에 parse_document를 실제로 돌려서
tier/warning 분포와 크래시 여부를 확인한다. 전체 4204건은 다음 단계(승인 후).

Section Builder/Table Serializer Phase에서 추가된 지표: 문서당 node/section/table 수,
text 보존율(공백 정규화 후 원문 대비 node 텍스트 길이 비), table 제목 확정 비율,
table shape 정상 비율.

실행: python3 scripts/run_parser_pilot.py [--n-per-group 60] [--seed 0]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.config import default_corpus_root  # noqa: E402
from dart_corpus.contract.manifest import ManifestLoader  # noqa: E402
from dart_corpus.contract.paths import resolve_corpus_path  # noqa: E402
from dart_corpus.parsing.canonical_parser import parse_document  # noqa: E402
from dart_corpus.parsing.document_ir import ParagraphIR, SectionIR, TableIR  # noqa: E402

_STRIP_TAGS_RE = re.compile(r"<[^>]+>")


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _raw_text_len_for_doc(doc, root) -> int:
    doc_dir = resolve_corpus_path(root, doc.file_path)
    total = 0
    if doc.file_format == "pdf+html":
        viewer_path = doc_dir / f"{doc.rcept_no}_viewer.html"
        raw = viewer_path.read_bytes().decode("utf-8", errors="replace")
        total += len(_normalize_ws(_STRIP_TAGS_RE.sub("", raw)))
    else:
        for p in doc_dir.iterdir():
            if p.suffix.lower() == ".xml":
                raw = p.read_bytes().decode("utf-8", errors="replace")
                total += len(_normalize_ws(_STRIP_TAGS_RE.sub("", raw)))
    return total


def _node_text_len(nodes) -> int:
    total = 0
    for n in nodes:
        if isinstance(n, ParagraphIR):
            total += len(_normalize_ws(n.text))
        elif isinstance(n, SectionIR):
            total += len(_normalize_ws(n.title_text))
        elif isinstance(n, TableIR):
            total += sum(len(_normalize_ws(c.text)) for c in n.raw_cells)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-group", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    root = default_corpus_root()
    docs = ManifestLoader(root).load()

    by_group: dict[str, list] = {}
    for d in docs:
        by_group.setdefault(d.doc_group, []).append(d)

    random.seed(args.seed)
    sample = []
    for group, group_docs in by_group.items():
        k = min(args.n_per_group, len(group_docs))
        sample.extend(random.sample(group_docs, k))

    print(f"샘플 크기: {len(sample)}건 ({ {g: min(args.n_per_group, len(v)) for g, v in by_group.items()} })")

    tier_hist = Counter()
    warning_code_hist = Counter()
    content_format_hist = Counter()
    schema_version_hist = Counter()
    crashes = []

    n_nodes_list, n_sections_list, n_tables_list, text_ratio_list = [], [], [], []
    n_tables_total = 0
    n_tables_title_confirmed = 0
    n_tables_shape_ok = 0

    t0 = time.perf_counter()
    for doc in sample:
        try:
            ir = parse_document(doc, root)
        except Exception as exc:  # 파일럿 단계 — 크래시 자체를 데이터로 수집(숨기지 않음)
            crashes.append({"doc_id": doc.doc_id, "error": f"{type(exc).__name__}: {exc}",
                             "traceback": traceback.format_exc(limit=3)})
            continue
        tier_hist[ir.parse_quality.tier] += 1
        schema_version_hist[str(ir.parse_quality.schema_version)] += 1
        for w in ir.warnings:
            warning_code_hist[w.code.value] += 1
        for sf in ir.source_files:
            content_format_hist[sf.content_format] += 1

        sections = [n for n in ir.nodes if isinstance(n, SectionIR)]
        tables = [n for n in ir.nodes if isinstance(n, TableIR)]
        n_nodes_list.append(len(ir.nodes))
        n_sections_list.append(len(sections))
        n_tables_list.append(len(tables))

        raw_len = _raw_text_len_for_doc(doc, root)
        if raw_len:
            text_ratio_list.append(_node_text_len(ir.nodes) / raw_len)

        shape_mismatched_tables = {
            m.group(1) for w in ir.warnings if w.code.value == "table_shape_mismatch"
            for m in [re.match(r"^table (\S+):", w.message)] if m
        }
        for t in tables:
            n_tables_total += 1
            if t.title_confirmed:
                n_tables_title_confirmed += 1
            if t.node_id not in shape_mismatched_tables:
                n_tables_shape_ok += 1

    elapsed = time.perf_counter() - t0

    def _avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    print(f"\n소요시간: {elapsed:.2f}s ({len(sample)/elapsed:.1f}건/s)")
    print(f"tier 분포: {dict(tier_hist)}")
    print(f"schema_version 분포: {dict(schema_version_hist)}")
    print(f"content_format 분포: {dict(content_format_hist)}")
    print(f"warning code 분포: {dict(warning_code_hist)}")
    print(f"\n문서당 node 수: avg={_avg(n_nodes_list):.1f} min={min(n_nodes_list, default=0)} max={max(n_nodes_list, default=0)}")
    print(f"문서당 section 수: avg={_avg(n_sections_list):.1f}")
    print(f"문서당 table 수: avg={_avg(n_tables_list):.1f}")
    print(f"text 보존율(공백정규화, node/원문): avg={_avg(text_ratio_list):.3f} "
          f"min={min(text_ratio_list, default=0):.3f} max={max(text_ratio_list, default=0):.3f}")
    print(f"table 제목 확정 비율: {n_tables_title_confirmed}/{n_tables_total} "
          f"({(n_tables_title_confirmed/n_tables_total*100) if n_tables_total else 0:.1f}%)")
    print(f"table shape 정상 비율: {n_tables_shape_ok}/{n_tables_total} "
          f"({(n_tables_shape_ok/n_tables_total*100) if n_tables_total else 0:.1f}%)")
    print(f"\n크래시: {len(crashes)}건")
    for c in crashes[:10]:
        print(f"  - {c['doc_id']}: {c['error']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({
                "sample_size": len(sample), "elapsed_s": elapsed,
                "tier_histogram": dict(tier_hist), "schema_version_histogram": dict(schema_version_hist),
                "content_format_histogram": dict(content_format_hist),
                "warning_code_histogram": dict(warning_code_hist), "crashes": crashes,
                "avg_nodes_per_doc": _avg(n_nodes_list), "avg_sections_per_doc": _avg(n_sections_list),
                "avg_tables_per_doc": _avg(n_tables_list), "avg_text_preservation_ratio": _avg(text_ratio_list),
                "n_tables_total": n_tables_total, "n_tables_title_confirmed": n_tables_title_confirmed,
                "n_tables_shape_ok": n_tables_shape_ok,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n저장: {args.json}")


if __name__ == "__main__":
    main()
