#!/usr/bin/env python3
"""데모 Case Pack이 참조하는 DocumentIR만 뽑아 캐시로 저장한다.

periodic.jsonl은 실측 8.1GB라 매번 훑을 수 없다. Case Pack 빌드에 필요한 doc_id만
한 번 스캔해서 `data/artifacts/case_packs/_source_docs.jsonl`에 캐시해 두고,
build_case_packs.py는 이 캐시만 읽는다.

사용법:
    PYTHONIOENCODING=utf-8 python scripts/extract_case_source_docs.py
    PYTHONIOENCODING=utf-8 python scripts/extract_case_source_docs.py --doc-id periodic_20230515001464
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IR_DIR = REPO / "data" / "artifacts" / "document_ir"
OUT_DIR = REPO / "data" / "artifacts" / "case_packs"
OUT_PATH = OUT_DIR / "_source_docs.jsonl"

# case_definitions.py와 동기화되는 기본 목록. Case Pack이 늘어나면 여기에 추가한다.
DEFAULT_DOC_IDS = [
    # --- CASE-001 에코프로비엠 CAM9 ---
    "exchange_20230523900365",  # 신규시설투자등 (원본, simulation_date)
    "exchange_20241022900223",  # [기재정정]신규시설투자등 (미래)
    "exchange_20231201900749",  # 투자판단관련주요경영사항 - NCA 중장기 공급계약 (미래)
    "periodic_20230515001464",  # 분기보고서 (2023.03)
    "periodic_20240318000873",  # 사업보고서 (2023.12) (미래)
    "major_20230425000692",     # 주요사항보고서(자기주식처분결정)
    "major_20230630000403",     # 주요사항보고서(전환사채권발행결정) (미래)
    "major_20241028000368",     # 주요사항보고서(자본으로인정되는채무증권발행결정) (미래)
    # --- CASE-002 LS ELECTRIC 초고압 변압기 ---
    "exchange_20240521800037",  # 신규시설투자등(자율공시) (원본, simulation_date)
    "exchange_20240813800252",  # [기재정정]신규시설투자등(자율공시) (미래)
    "periodic_20240313001659",  # 사업보고서 (2023.12)
    "periodic_20240514001662",  # 분기보고서 (2024.03)
    "exchange_20240103800430",  # 단일판매ㆍ공급계약체결
    "exchange_20240109800112",  # 단일판매ㆍ공급계약체결
    "periodic_20240814001155",  # 반기보고서 (2024.06) (미래)
    "major_20240523000347",     # 주요사항보고서(자기주식처분결정) (미래)
    # --- CASE-003 삼성바이오로직스 5공장 ---
    "exchange_20230317800146",  # 신규시설투자등 (원본, simulation_date)
    "exchange_20230605800274",  # [기재정정]신규시설투자등 - 종료일 단축 (미래)
    "exchange_20241218800350",  # [기재정정]신규시설투자등 - 금액 증액 (미래)
    "exchange_20230302800001",  # 단일판매ㆍ공급계약체결
    "exchange_20230306800412",  # [기재정정]단일판매ㆍ공급계약체결
    "exchange_20230206800712",  # [기재정정]단일판매ㆍ공급계약체결
    "exchange_20230704800004",  # 단일판매ㆍ공급계약체결 (미래)
    "periodic_20230515002481",  # 분기보고서 (2023.03) (미래)
]

GROUP_FILES = {
    "periodic": "periodic.jsonl",
    "major": "major.jsonl",
    "exchange": "exchange.jsonl",
    "holding": "holding.jsonl",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc-id", action="append", default=None,
                    help="추출할 doc_id (반복 가능). 생략하면 DEFAULT_DOC_IDS 사용")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--ir-dir", default=str(IR_DIR))
    args = ap.parse_args()

    doc_ids = args.doc_id or DEFAULT_DOC_IDS
    wanted = set(doc_ids)
    ir_dir = Path(args.ir_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    by_group: dict[str, set[str]] = {}
    for did in wanted:
        by_group.setdefault(did.split("_", 1)[0], set()).add(did)

    found: dict[str, dict] = {}
    for group, ids in by_group.items():
        path = ir_dir / GROUP_FILES[group]
        if not path.exists():
            print(f"[WARN] missing {path} - {group} 문서 {len(ids)}건 건너뜀", file=sys.stderr)
            continue
        remaining = set(ids)
        print(f"[scan] {path.name} ({path.stat().st_size / 1e9:.2f}GB) for {len(remaining)} docs",
              file=sys.stderr)
        with path.open(encoding="utf-8") as f:
            for line in f:
                # doc_id는 항상 첫 필드다 - 전체 JSON 파싱 전에 프리픽스로 걸러 비용을 줄인다.
                head = line[:80]
                hit = next((d for d in remaining if d in head), None)
                if hit is None:
                    continue
                doc = json.loads(line)
                if doc["doc_id"] in remaining:
                    found[doc["doc_id"]] = doc
                    remaining.discard(doc["doc_id"])
                    print(f"  [hit] {doc['doc_id']}", file=sys.stderr)
                    if not remaining:
                        break
        if remaining:
            print(f"[WARN] not found in {path.name}: {sorted(remaining)}", file=sys.stderr)

    with out_path.open("w", encoding="utf-8") as f:
        for did in doc_ids:
            if did in found:
                f.write(json.dumps(found[did], ensure_ascii=False) + "\n")

    print(f"[done] {len(found)}/{len(wanted)} docs -> {out_path}", file=sys.stderr)
    return 0 if len(found) == len(wanted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
