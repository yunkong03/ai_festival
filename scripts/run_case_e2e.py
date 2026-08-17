#!/usr/bin/env python3
"""Case 1건을 처음부터 끝까지 플레이하는 E2E 실행기.

조사 → 힌트 → 용어 → 판단 → Reality Replay 순서로 돌리고, 중간에
Point-in-Time 차단이 실제로 작동하는지 직접 증명한 뒤 trace를 파일로 남긴다.

사용법:
    PYTHONIOENCODING=utf-8 python scripts/run_case_e2e.py
    PYTHONIOENCODING=utf-8 python scripts/run_case_e2e.py --case CASE-002 --llm
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from dart_detective.errors import FutureLeakageError  # noqa: E402
from dart_detective.graph import GameServer  # noqa: E402

OUT_DIR = REPO / "work" / "agent-runs"


def rule(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="CASE-001")
    ap.add_argument("--llm", action="store_true", help="자격증명이 있으면 LLM 경로 사용")
    ap.add_argument("--question", default="이 회사가 이 투자를 감당할 수 있어?")
    ap.add_argument("--option", default="O2")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    server = GameServer(use_llm=args.llm)
    session = server.start(args.case)
    pack = session.pack
    brief = pack.briefing()

    rule(f"{brief['case_id']} — {brief['case_title']}")
    print(f"기업: {brief['company']['listed_name']} ({brief['company']['stock_code']})")
    print(f"simulation_date: {brief['simulation_date']}  난이도: {brief['difficulty']}")
    print(f"LLM: {'on' if session.runtime.llm else 'off (결정론적 fallback)'}")
    print(f"\n미션: {brief['mission']}")
    print(f"\n조사 가능한 문서 {len(brief['documents'])}건:")
    for d in brief["documents"]:
        print(f"  {d['document_id']} [{d['document_date']}] {d['title']}")

    # ---------------- Point-in-Time 차단 증명 ----------------
    rule("Point-in-Time Retrieval 차단 확인")
    retriever = session.runtime.retriever
    stats = retriever.stats()
    print(f"인덱스: 전체 {stats['n_chunks']} chunk "
          f"(과거 {stats['n_past_chunks']} / 미래 {stats['n_future_chunks']})")
    probe = "정정 신규시설투자 계약"
    unfiltered = retriever.search(probe, k=3, enforce_date_filter=False)
    filtered = retriever.search(probe, k=3)
    print(f"\n필터 OFF (테스트 전용) — '{probe}':")
    for r in unfiltered:
        mark = "  <-- 미래 문서" if r.document_date > pack.simulation_date else ""
        print(f"  {r.document_date} {r.title[:44]:<44} score={r.score}{mark}")
    print(f"\n필터 ON (운영 경로) — '{probe}':")
    for r in filtered:
        print(f"  {r.document_date} {r.title[:44]:<44} score={r.score}")
    n_future_leaked = sum(1 for r in unfiltered if r.document_date > pack.simulation_date)
    print(f"\n필터 OFF일 때 미래 문서 {n_future_leaked}건이 상위에 잡힌다 -> 필터가 실제로 일한다.")
    try:
        retriever.assert_no_future(unfiltered)
        print("[WARN] 이 쿼리에서는 미래 문서가 안 잡혔다(assertion 미발동).")
    except FutureLeakageError as exc:
        print(f"assert_no_future(필터 OFF 결과) -> FutureLeakageError: "
              f"{len(exc.offending)}건 차단")

    # ---------------- 1. 문서 열람 + 단서 수집 ----------------
    rule("1) 문서 열람 + Evidence 수집")
    first_doc = brief["documents"][0]["document_id"]
    r = session.act("open_document", document_id=first_doc)
    options = r["response"]["evidence_options"]
    print(f"{first_doc} 열람 — 수집 가능한 단서 {len(options)}건")
    to_collect = [o["evidence_id"] for o in options if o["importance"] == "critical"][:3]
    r = session.act("open_document", document_id=first_doc, collect=to_collect)
    print(f"수집: {r['response']['newly_collected']}")
    print(f"조사 포인트: {r['state']['investigation_points']}")

    # ---------------- 2. 자유 질문 조사 ----------------
    rule("2) Evidence Agent 조사")
    r = session.act("research", question=args.question)
    resp = r["response"]
    print(f"질문: {args.question}\n")
    print(resp["answer"])
    print(f"\n근거 {len(resp['evidence'])}건:")
    for e in resp["evidence"]:
        print(f"  [{e['document_id']}] {e['quote_or_fact'][:90]}")
    print(f"\n불확실성: {resp['uncertainty']}")
    print(f"Evidence Validation: {resp['validation']['status']}")
    for c in resp["validation"]["checks"]:
        print(f"  - {c['check']}: {'PASS' if c['passed'] else 'FAIL'} "
              f"{c.get('note', '')}".rstrip())
    print(f"검색된 문서 {len(resp['retrieved'])}건 (전부 <= {pack.simulation_date}):")
    for d in resp["retrieved"]:
        print(f"  {d['document_date']} {d['document_id']} score={d['score']}")
    print(f"새로 수집된 단서: {resp['newly_collected']}")

    # ---------------- 3. 힌트 3단계 ----------------
    rule("3) Tutor Agent — 힌트 3단계")
    for level in (1, 2, 3):
        r = session.act("hint", level=level)
        h = r["response"]
        print(f"Level {h['level']}: {h['hint']}")
    print(f"남은 critical 단서: {h['remaining_critical']}")

    # ---------------- 4. 금융용어 ----------------
    rule("4) Glossary")
    r = session.act("term")
    for t in r["response"]["terms"]:
        print(f"  - {t['term']}: {t['short_definition'][:60]}")
    first_term = r["response"]["terms"][0]["term"]
    r = session.act("term", term=first_term)
    t = r["response"]["term"]
    print(f"\n{t['term']} — {t['short_definition']}")
    print(f"이번 사건에서: {t['why_it_matters_here']}")

    # ---------------- 5. Replay 잠금 확인 ----------------
    rule("5) Reality Replay 잠금 확인 (판단 전)")
    r = session.act("replay")
    print(f"error: {r['error']}")
    print(f"future_unlocked: {r['state']['future_unlocked']}")
    assert r["state"]["future_unlocked"] is False, "판단 전에 미래가 열렸다"

    # ---------------- 6. 판단 ----------------
    rule("6) Decision")
    r = session.act("decision", option_id=args.option)
    rec = r["response"]
    print(f"선택: {rec['decision']} ({rec['option_id']})")
    print(f"사용한 단서: {rec['used_evidence_ids']}")
    print("\n조사 요약:")
    for label, v in rec["investigation_summary"].items():
        if label == "critical_coverage":
            print(f"  critical 단서: {v['checked']}/{v['total']} "
                  f"(미확인 {v['missing']})")
        else:
            print(f"  {label}: {v['checked']}/{v['total']}")
    print("\n피드백:")
    for f in rec["feedback"]:
        print(f"  - {f}")
    print(f"\n{rec['note']}")

    # ---------------- 7. Reality Replay ----------------
    rule("7) Reality Replay (판단 후)")
    r = session.act("replay")
    rep = r["response"]
    print(f"future_unlocked: {r['state']['future_unlocked']}")
    for e in rep["future_events"]:
        print(f"\n[{e['date']}] {e.get('report_nm', '')}")
        print(f"  {e['event']}")
        for ch in e.get("changed_fields", []):
            print(f"    {ch['field']}: {ch['before']} -> {ch['after']}")

    # ---------------- trace 저장 ----------------
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / f"{args.case}-e2e-trace.json"
    trace = session.trace()
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    rule("Trace")
    print(f"{len(trace)}턴 기록 -> {trace_path.relative_to(REPO)}")
    for t in trace:
        print(f"  {t['action']:<14} node={t['node']:<14} "
              f"{t['latency_ms']:>4}ms  retrieved={len(t['retrieved'])}  "
              f"validation={(t['validation'] or {}).get('status', '-')}"
              f"{'  ERROR=' + str(t['error']) if t['error'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
