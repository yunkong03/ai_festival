#!/usr/bin/env python3
"""Case Pack -> Point-in-Time 검색 인덱스(JSONL) 생성.

**인덱스에는 미래 문서도 일부러 함께 넣는다.**
날짜 필터가 실제로 일하는지 증명하려면, 필터를 껐을 때 미래 문서가 검색되어야 한다.
필터가 켜진 운영 경로에서는 PointInTimeRetriever가 후보 풀 단계에서 잘라낸다.

입력:
    data/artifacts/case_packs/CASE-*.json          (필수)
    data/artifacts/case_packs/_source_docs.jsonl   (선택 — 있으면 미래 문서 본문까지 색인)

출력:
    data/artifacts/case_packs/search_index.jsonl

사용법:
    PYTHONIOENCODING=utf-8 python scripts/build_case_search_index.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

from case_pack_render import render_document  # noqa: E402

PACK_DIR = REPO / "data" / "artifacts" / "case_packs"
SOURCE_DOCS = PACK_DIR / "_source_docs.jsonl"
OUT_PATH = PACK_DIR / "search_index.jsonl"

WINDOW = 12   # 청크 하나에 담는 줄 수
STRIDE = 8    # 창 이동 폭(겹침 4줄) — 표 행이 창 경계에서 잘려도 옆 창이 받는다


def chunk_lines(text: str, window: int = WINDOW, stride: int = STRIDE) -> list[str]:
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return []
    if len(lines) <= window:
        return ["\n".join(lines)]
    out = []
    for start in range(0, len(lines), stride):
        piece = lines[start:start + window]
        if not piece:
            break
        out.append("\n".join(piece))
        if start + window >= len(lines):
            break
    return out


def load_source_docs() -> dict[str, dict]:
    if not SOURCE_DOCS.exists():
        return {}
    out = {}
    with SOURCE_DOCS.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            out[d["doc_id"]] = d
    return out


def build(pack: dict, source_docs: dict[str, dict]) -> list[dict]:
    case_id = pack["case_id"]
    rows: list[dict] = []

    # 1) 조사 가능한 문서(simulation_date 이전)
    for doc in pack["available_documents"]:
        for i, text in enumerate(chunk_lines(doc["original_text"])):
            rows.append({
                "chunk_id": f"{case_id}:{doc['document_id']}:{i:03d}",
                "case_id": case_id,
                "doc_id": doc["doc_id"],
                "document_id": doc["document_id"],
                "document_date": doc["document_date"],
                "title": doc["title"],
                "source_type": doc["source_type"],
                "text": text,
            })

    # 2) 미래 문서(simulation_date 이후) — 날짜 필터가 걸러내야 할 대상
    for j, fe in enumerate(pack["future_events"]):
        doc_id = fe["source_document_id"]
        title = f"[FUTURE] {fe.get('report_nm', doc_id)}"
        texts: list[str] = []
        src = source_docs.get(doc_id)
        if src is not None:
            body, _ = render_document(src, max_chars=20000)
            texts = chunk_lines(body)
        if not texts:
            # _source_docs.jsonl이 없으면 Case Pack에 담긴 발췌만으로 색인한다.
            texts = [fe.get("source_text") or fe["event"]]
        for i, text in enumerate(texts):
            rows.append({
                "chunk_id": f"{case_id}:FUT{j:02d}:{i:03d}",
                "case_id": case_id,
                "doc_id": doc_id,
                "document_id": None,
                "document_date": fe["date"],
                "title": title,
                "source_type": doc_id.split("_", 1)[0],
                "text": text,
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack-dir", default=str(PACK_DIR))
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    pack_dir = Path(args.pack_dir)
    packs = sorted(pack_dir.glob("CASE-*.json"))
    if not packs:
        print("Case Pack이 없다. scripts/build_case_packs.py를 먼저 실행하라.", file=sys.stderr)
        return 1

    source_docs = load_source_docs()
    if not source_docs:
        print(f"[warn] {SOURCE_DOCS} 없음 — 미래 문서는 Case Pack 발췌만 색인한다.",
              file=sys.stderr)

    rows: list[dict] = []
    for p in packs:
        pack = json.loads(p.read_text(encoding="utf-8"))
        got = build(pack, source_docs)
        n_future = sum(1 for r in got if r["document_id"] is None)
        print(f"[ok] {pack['case_id']}: {len(got)} chunks "
              f"(past {len(got) - n_future} / future {n_future})")
        rows.extend(got)

    out = Path(args.out)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[done] {len(rows)} chunks -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
