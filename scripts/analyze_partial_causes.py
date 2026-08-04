"""Partial-tier 원인 분석 — 기존 run_parser_pilot.py와 동일한 층화표본(seed=0, 60/group)에
대해 parse_document를 실행하고, tier=partial이 된 문서별 원인을 warning code/조건별로
분류한다. Chunk는 만들지 않는다 — 순수 진단 스크립트.

실행: python3 scripts/analyze_partial_causes.py [--n-per-group 60] [--seed 0] [--json PATH]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.config import default_corpus_root  # noqa: E402
from dart_corpus.contract.manifest import ManifestLoader  # noqa: E402
from dart_corpus.parsing.canonical_parser import parse_document  # noqa: E402
from dart_corpus.parsing.document_ir import ParagraphIR, SectionIR, TableIR, WarningCode  # noqa: E402
from dart_corpus.parsing.sniff import CONTENT_DART_XML  # noqa: E402

import re

_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
_TITLE_OPEN_RE = re.compile(r"<TITLE[\s>]")
_P_OPEN_RE = re.compile(r"<P[\s>]")
_TABLE_GROUP_OPEN_RE = re.compile(r"<TABLE-GROUP[\s>]")


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _raw_text_len_for_doc(doc, root) -> int:
    """부속서류 포함 모든 XML 파일의 태그 제거+공백 정규화 후 문자 수(원문 규모 추정치).
    node 쪽도 동일하게 공백 정규화해서 비교해야 공정하다(단순 길이비교면 whitespace
    처리 차이 때문에 ratio>1이 나올 수 있음 — 실측으로 확인됨)."""
    from dart_corpus.contract.paths import resolve_corpus_path

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


def _primary_tag_counts(doc, root) -> dict:
    """부속서류 포함 모든 XML 파일 합산 원문 TITLE/P/TABLE-GROUP open-tag 개수(구조 손실
    점검용). node 쪽(ir.nodes)도 primary+첨부 전체를 합산하므로 동일 기준으로 비교해야
    공정하다 — 최초 버전은 primary 파일만 세서 첨부파일 표가 많은 문서에서 허위로
    'node_tables >> raw_table_group'처럼 보이는 착시가 있었음(실측으로 확인 후 수정)."""
    from dart_corpus.contract.paths import resolve_corpus_path

    doc_dir = resolve_corpus_path(root, doc.file_path)
    total = {"title": 0, "p": 0, "table_group": 0}
    for p in doc_dir.iterdir():
        if p.suffix.lower() != ".xml":
            continue
        raw = p.read_bytes().decode("utf-8", errors="replace")
        total["title"] += len(_TITLE_OPEN_RE.findall(raw))
        total["p"] += len(_P_OPEN_RE.findall(raw))
        total["table_group"] += len(_TABLE_GROUP_OPEN_RE.findall(raw))
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-group", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    root = default_corpus_root()
    loader = ManifestLoader(root)
    docs = loader.load()

    by_group: dict[str, list] = {}
    for d in docs:
        by_group.setdefault(d.doc_group, []).append(d)

    random.seed(args.seed)
    sample = []
    for group, group_docs in by_group.items():
        k = min(args.n_per_group, len(group_docs))
        sample.extend(random.sample(group_docs, k))

    # [실측 확인] ManifestLoader.load()는 file_format="xml"만 반환 — pdf+html 3건은
    # SUPPORTED_FORMATS 밖이라 기존 240건 층화표본에 한 번도 포함된 적이 없었다.
    # partial 원인 분석에서 pdf+html 경로를 실제로 보려면 unsupported() 결과를 별도로 붙여야 함.
    pdf_html_docs = loader.unsupported(loader.load())
    sample.extend(pdf_html_docs)

    print(f"샘플 크기: {len(sample) - len(pdf_html_docs)}건(층화표본) + {len(pdf_html_docs)}건(pdf+html, 기존 표본엔 미포함이었음)")

    partial_cause_hist = Counter()
    partial_docs = []
    encoding_replace_docs = []
    text_ratios = []
    n_partial = 0

    t0 = time.perf_counter()
    for doc in sample:
        try:
            ir = parse_document(doc, root)
        except Exception as exc:
            print(f"CRASH {doc.doc_id}: {type(exc).__name__}: {exc}")
            continue

        if any(sf.actual_encoding_used.endswith("(replace)") for sf in ir.source_files):
            encoding_replace_docs.append(doc.doc_id)

        if ir.parse_quality.tier != "partial":
            continue
        n_partial += 1

        is_pdf_html = doc.file_format == "pdf+html"
        has_sanitized = any(w.code == WarningCode.SANITIZED_ENTITY for w in ir.warnings)
        has_content_mismatch = any(w.code == WarningCode.CONTENT_TYPE_MISMATCH for w in ir.warnings)
        has_merged_cell = any(w.code == WarningCode.TABLE_MERGED_CELL_IGNORED for w in ir.warnings)

        if is_pdf_html:
            cause = "pdf+html_forced_partial"
        elif has_sanitized:
            cause = "sanitized_entity_downgrade"
        else:
            cause = "other_unclassified"
        partial_cause_hist[cause] += 1

        raw_len = _raw_text_len_for_doc(doc, root)
        node_len = _node_text_len(ir.nodes)
        ratio = (node_len / raw_len) if raw_len else None
        text_ratios.append(ratio)

        tag_counts = _primary_tag_counts(doc, root) if not is_pdf_html else {}
        n_sections = sum(1 for n in ir.nodes if isinstance(n, SectionIR))
        n_tables = sum(1 for n in ir.nodes if isinstance(n, TableIR))

        partial_docs.append({
            "doc_id": doc.doc_id, "doc_group": doc.doc_group, "cause": cause,
            "is_pdf_html": is_pdf_html, "has_sanitized_entity": has_sanitized,
            "has_content_type_mismatch": has_content_mismatch, "has_merged_cell": has_merged_cell,
            "n_nodes": len(ir.nodes),
            "n_sections": n_sections,
            "n_tables": n_tables,
            "n_paragraphs": sum(1 for n in ir.nodes if isinstance(n, ParagraphIR)),
            "raw_text_len_no_tags": raw_len, "node_text_len": node_len,
            "text_preservation_ratio": ratio,
            "raw_title_tag_count": tag_counts.get("title"),
            "raw_table_group_tag_count": tag_counts.get("table_group"),
            "section_count_matches_title_tags": (tag_counts.get("title") == n_sections) if tag_counts else None,
            "table_count_matches_table_group_tags": (tag_counts.get("table_group") == n_tables) if tag_counts else None,
        })

    elapsed = time.perf_counter() - t0

    print(f"\n소요시간: {elapsed:.2f}s")
    print(f"partial 총 {n_partial}건")
    print(f"partial 원인별: {dict(partial_cause_hist)}")
    print(f"encoding replace(최후수단) 발생 문서 수: {len(encoding_replace_docs)}")
    print(f"  -> {encoding_replace_docs[:10]}")
    valid_ratios = [r for r in text_ratios if r is not None]
    if valid_ratios:
        print(f"partial 문서 text_preservation_ratio: min={min(valid_ratios):.3f} "
              f"max={max(valid_ratios):.3f} avg={sum(valid_ratios)/len(valid_ratios):.3f}")
        low_ratio_docs = [d for d in partial_docs if d["text_preservation_ratio"] is not None and d["text_preservation_ratio"] < 0.9]
        print(f"text_preservation_ratio < 0.9인 partial 문서: {len(low_ratio_docs)}건")
        for d in low_ratio_docs[:10]:
            print(f"  - {d['doc_id']} ratio={d['text_preservation_ratio']:.3f} cause={d['cause']}")

    section_mismatch = [d for d in partial_docs if d["section_count_matches_title_tags"] is False]
    table_mismatch = [d for d in partial_docs if d["table_count_matches_table_group_tags"] is False]
    print(f"\nSectionIR 개수 != 원문 TITLE 태그 수: {len(section_mismatch)}건")
    for d in section_mismatch[:10]:
        print(f"  - {d['doc_id']} raw_title={d['raw_title_tag_count']} node_sections={d['n_sections']}")
    print(f"TableIR 개수 != 원문 TABLE-GROUP 태그 수: {len(table_mismatch)}건")
    for d in table_mismatch[:10]:
        print(f"  - {d['doc_id']} raw_table_group={d['raw_table_group_tag_count']} node_tables={d['n_tables']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({
                "sample_size": len(sample), "n_partial": n_partial,
                "partial_cause_histogram": dict(partial_cause_hist),
                "encoding_replace_docs": encoding_replace_docs,
                "partial_docs": partial_docs,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n저장: {args.json}")


if __name__ == "__main__":
    main()
