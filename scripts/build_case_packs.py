#!/usr/bin/env python3
"""실제 DART 공시 DocumentIR -> 금융 탐정게임 데모 Case Pack 생성.

원칙:
  - 사건/숫자/문장은 전부 실제 공시에서 온다. 게임용 가상 수치를 만들지 않는다.
  - simulation_date 이후 문서는 available_documents에 절대 들어가지 않고 future_events에만 존재한다.
  - evidence.source_text는 available_document.original_text의 부분 문자열로 강제된다
    (빌드 시 실패하면 즉시 예외).

전제:
    scripts/extract_case_source_docs.py를 먼저 실행해
    data/artifacts/case_packs/_source_docs.jsonl이 있어야 한다.

사용법:
    PYTHONIOENCODING=utf-8 python scripts/extract_case_source_docs.py
    PYTHONIOENCODING=utf-8 python scripts/build_case_packs.py
    PYTHONIOENCODING=utf-8 python scripts/validate_case_pack.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from case_definitions import CASES  # noqa: E402
from case_pack_render import find_line, render_document  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
PACK_DIR = REPO / "data" / "artifacts" / "case_packs"
SOURCE_DOCS = PACK_DIR / "_source_docs.jsonl"
MANIFEST_PATH = REPO / "data" / "3.공시" / "corpus" / "manifest.jsonl"
SCHEMA_VERSION = "case_pack_v0"


def load_source_docs() -> dict[str, dict]:
    if not SOURCE_DOCS.exists():
        raise SystemExit(
            f"{SOURCE_DOCS} 없음. 먼저 scripts/extract_case_source_docs.py를 실행하라."
        )
    out = {}
    with SOURCE_DOCS.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            out[d["doc_id"]] = d
    return out


def load_manifest() -> dict[str, dict]:
    out = {}
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["doc_id"]] = r
    return out


def iso(rcept_dt: str) -> str:
    return f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}"


def block(lines: list[str], patterns: list[str], span: int, where: str) -> str:
    i = find_line(lines, patterns)
    if i < 0:
        raise KeyError(f"{where}: 패턴 {patterns}에 맞는 줄 없음")
    return "\n".join(lines[i:i + span])


def build_case(case: dict, docs: dict[str, dict], manifest: dict[str, dict]) -> dict:
    sim = case["simulation_date"]

    rendered: dict[str, tuple[str, list[str]]] = {}
    available_documents = []
    for d in case["documents"]:
        src = docs.get(d["doc_id"])
        if src is None:
            raise SystemExit(f"{case['case_id']}: DocumentIR {d['doc_id']} 캐시에 없음")
        meta = manifest[d["doc_id"]]
        text, lines = render_document(
            src,
            section_keywords=d.get("sections"),
            max_chars=d.get("max_chars", 20000),
        )
        if not text.strip():
            raise SystemExit(f"{case['case_id']}/{d['document_id']}: 렌더 결과가 비어 있다 "
                             f"(sections={d.get('sections')})")
        rendered[d["document_id"]] = (text, lines)

        doc_date = iso(meta["rcept_dt"])
        if doc_date > sim:
            raise SystemExit(f"{case['case_id']}/{d['document_id']}: document_date={doc_date} > "
                             f"simulation_date={sim} (future leakage)")

        excerpt = block(lines, d["excerpt"]["match"], d["excerpt"].get("span", 6),
                        f"{case['case_id']}/{d['document_id']}.excerpt")
        available_documents.append({
            "document_id": d["document_id"],
            "doc_id": d["doc_id"],
            "rcept_no": meta["rcept_no"],
            "title": d["title"],
            "document_date": doc_date,
            "source_type": meta["doc_group"],
            "doc_subtype": meta.get("doc_subtype"),
            "report_nm": meta["report_nm"],
            "is_correction": meta["is_correction"],
            "role": d["role"],
            "original_text": text,
            "display_excerpt": excerpt,
            "source_locator": {
                "corpus_file_path": meta["file_path"],
                "sections": d.get("sections"),
                "n_lines": len(lines),
            },
        })

    evidence = []
    for e in case["evidence"]:
        text, lines = rendered[e["document_id"]]
        src_text = block(lines, e["match"], e.get("span", 1),
                         f"{case['case_id']}/{e['evidence_id']}")
        if src_text not in text:
            raise SystemExit(f"{case['case_id']}/{e['evidence_id']}: source_text가 "
                             f"original_text의 부분 문자열이 아니다")
        evidence.append({
            "evidence_id": e["evidence_id"],
            "document_id": e["document_id"],
            "text": e["text"],
            "source_text": src_text,
            "category": e["category"],
            "importance": e["importance"],
            "educational_reason": e["educational_reason"],
            "source_locator": {"match": e["match"], "span": e.get("span", 1)},
        })

    future_events = []
    for fe in case["future_events"]:
        src = docs.get(fe["doc_id"])
        meta = manifest[fe["doc_id"]]
        fdate = iso(meta["rcept_dt"])
        if fdate <= sim:
            raise SystemExit(f"{case['case_id']}: future_event {fe['doc_id']} date={fdate} "
                             f"<= simulation_date={sim}")
        item = {
            "date": fdate,
            "event": fe["event"],
            "source_document_id": fe["doc_id"],
            "report_nm": meta["report_nm"],
        }
        if src is not None and fe.get("match"):
            _, flines = render_document(src, section_keywords=fe.get("sections"),
                                        max_chars=fe.get("max_chars", 20000))
            item["source_text"] = block(flines, fe["match"], fe.get("span", 1),
                                        f"{case['case_id']}/future/{fe['doc_id']}")
        if fe.get("changed_fields"):
            item["changed_fields"] = fe["changed_fields"]
        future_events.append(item)
    future_events.sort(key=lambda x: x["date"])

    company_meta = manifest[case["documents"][0]["doc_id"]]
    pack = {
        "schema_version": SCHEMA_VERSION,
        "generator": {
            "script": "scripts/build_case_packs.py",
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "corpus_snapshot_id": docs[case["documents"][0]["doc_id"]].get("corpus_snapshot_id"),
            "parser_version": docs[case["documents"][0]["doc_id"]].get("parser_version"),
        },
        "case_id": case["case_id"],
        "company": {
            "corp_name": company_meta["corp_name"],
            "listed_name": company_meta["listed_name"],
            "corp_code": company_meta["corp_code"],
            "stock_code": company_meta["stock_code"],
            "industry": company_meta["industry"],
            "sector": company_meta["sector"],
        },
        "case_title": case["case_title"],
        "simulation_date": sim,
        "difficulty": case.get("difficulty", "normal"),
        "mission": case["mission"],
        "intro": case["intro"],
        "available_documents": available_documents,
        "evidence": evidence,
        "finance_terms": case["finance_terms"],
        "decision_options": case["decision_options"],
        "future_events": future_events,
        "validation": {
            "future_leakage": False,
            "all_evidence_grounded": True,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "checks": {
                "n_available_documents": len(available_documents),
                "n_evidence": len(evidence),
                "n_critical_evidence": sum(1 for e in evidence if e["importance"] == "critical"),
                "n_future_events": len(future_events),
                "max_document_date": max(d["document_date"] for d in available_documents),
                "min_future_event_date": min(f["date"] for f in future_events),
            },
        },
    }
    return pack


def write_evidence_map(packs: list[dict], path: Path) -> None:
    """Case에 쓰인 실제 공시 목록 + Evidence 출처 매핑을 마크다운으로 뽑는다."""
    out = [
        "# 데모 Case Pack — 사용 공시 목록 / Evidence 출처 매핑",
        "",
        "> 이 파일은 `scripts/build_case_packs.py`가 생성한다. 직접 수정하지 마라.",
        "",
    ]
    for p in packs:
        out += [
            f"## {p['case_id']} — {p['company']['listed_name']} / {p['case_title']}",
            "",
            f"- simulation_date: **{p['simulation_date']}**",
            f"- corpus_snapshot_id: `{p['generator']['corpus_snapshot_id']}` / "
            f"parser_version: `{p['generator']['parser_version']}`",
            "",
            "### 조사 가능한 실제 공시 (simulation_date 이전)",
            "",
            "| document_id | 공시일 | doc_id (DART rcept_no) | report_nm | 역할 | 원문 위치 |",
            "|---|---|---|---|---|---|",
        ]
        for d in p["available_documents"]:
            sec = d["source_locator"].get("sections")
            sec_txt = " / ".join(sec) if sec else "(문서 전체)"
            out.append(
                f"| {d['document_id']} | {d['document_date']} | `{d['doc_id']}` | "
                f"{d['report_nm']} | {d['role']} | {d['source_locator']['corpus_file_path']}"
                f"<br>섹션: {sec_txt} |"
            )
        out += [
            "",
            "### Evidence 출처 매핑",
            "",
            "| evidence_id | 문서 | 분류 | 중요도 | 원문(source_text) 첫 줄 |",
            "|---|---|---|---|---|",
        ]
        for e in p["evidence"]:
            first = e["source_text"].split("\n")[0].replace("|", "\\|")
            if len(first) > 90:
                first = first[:90] + "…"
            out.append(
                f"| {e['evidence_id']} | {e['document_id']} | {e['category']} | "
                f"{e['importance']} | `{first}` |"
            )
        out += [
            "",
            "### Reality Replay (simulation_date 이후 — 플레이 전 비노출)",
            "",
            "| 공시일 | doc_id | 사건 |",
            "|---|---|---|",
        ]
        for f in p["future_events"]:
            out.append(f"| {f['date']} | `{f['source_document_id']}` | "
                       f"{f['event'].replace('|', chr(92) + '|')} |")
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", action="append", help="빌드할 case_id (반복 가능)")
    ap.add_argument("--out-dir", default=str(PACK_DIR))
    ap.add_argument("--evidence-map", default=str(REPO / "docs" / "demo_case_evidence_map.md"))
    args = ap.parse_args()

    docs = load_source_docs()
    manifest = load_manifest()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [c for c in CASES if not args.case or c["case_id"] in args.case]
    index = []
    built = []
    for case in targets:
        pack = build_case(case, docs, manifest)
        built.append(pack)
        path = out_dir / f"{pack['case_id']}.json"
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] {pack['case_id']} {pack['company']['listed_name']} "
              f"sim={pack['simulation_date']} docs={len(pack['available_documents'])} "
              f"evidence={len(pack['evidence'])} future={len(pack['future_events'])} -> {path.name}")
        index.append({
            "case_id": pack["case_id"],
            "file": path.name,
            "company": pack["company"]["listed_name"],
            "case_title": pack["case_title"],
            "simulation_date": pack["simulation_date"],
            "difficulty": pack["difficulty"],
            "n_available_documents": len(pack["available_documents"]),
            "n_evidence": len(pack["evidence"]),
            "n_future_events": len(pack["future_events"]),
        })

    (out_dir / "index.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "cases": index},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"[ok] index.json ({len(index)} cases)")

    ev_map = Path(args.evidence_map)
    ev_map.parent.mkdir(parents=True, exist_ok=True)
    write_evidence_map(built, ev_map)
    print(f"[ok] {ev_map.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
