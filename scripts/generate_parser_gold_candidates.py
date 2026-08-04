"""Parser Gold 후보 생성 — run_full_corpus.py가 만든 parse_audit.jsonl을 doc_group x
parse_quality_tier로 층화 추출해 사람이 검수할 후보 목록 + annotation template을 만든다.

★ 여기서 만드는 건 "후보"일 뿐, gold(정답)가 아니다. 자동 라벨링 없음 — 실제 검수는
별도 사람 작업(이번 스크립트 범위 밖).

실행: python3 scripts/generate_parser_gold_candidates.py [--out-dir data/artifacts] [--target-total 90] [--seed 0]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dart_corpus.parsing.audit import load_parse_audits_jsonl  # noqa: E402
from dart_corpus.parsing.gold_candidates import (  # noqa: E402
    select_gold_candidates, write_annotation_template_csv, write_gold_candidates_jsonl,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data" / "artifacts")
    ap.add_argument("--audit-path", type=Path, default=None, help="기본값: <out-dir>/parse_audit.jsonl")
    ap.add_argument("--target-total", type=int, default=90)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    audit_path = args.audit_path or (args.out_dir / "parse_audit.jsonl")
    if not audit_path.exists():
        print(f"오류: {audit_path} 없음 — 먼저 scripts/run_full_corpus.py를 실행해야 함")
        sys.exit(1)

    audits = load_parse_audits_jsonl(audit_path)
    print(f"parse_audit 로드: {len(audits)}건 ({audit_path})")

    candidates = select_gold_candidates(audits, target_total=args.target_total, seed=args.seed)
    stratum_hist = Counter((c.doc_group, c.parse_quality_tier) for c in candidates)

    candidates_path = args.out_dir / "parser_gold_candidates.jsonl"
    template_path = args.out_dir / "parser_gold_annotation_template.csv"
    write_gold_candidates_jsonl(candidates, candidates_path)
    write_annotation_template_csv(candidates, template_path)

    print(f"\n후보 {len(candidates)}건 선정(target_total={args.target_total}, seed={args.seed})")
    print("stratum(doc_group, tier)별 후보 수:")
    for key in sorted(stratum_hist):
        print(f"  {key}: {stratum_hist[key]}")
    print(f"\n저장: {candidates_path}")
    print(f"저장(검수 template): {template_path}")
    print("\n주의: 이 목록은 후보일 뿐 gold 정답이 아님 — 사람 검수 필요.")


if __name__ == "__main__":
    main()
