#!/usr/bin/env python3
"""Case Pack 검증 - Future Leakage 검사 + Evidence Grounding 검사.

핵심 invariant:
  1) available_document.document_date <= simulation_date
  2) future_event.date            >  simulation_date
  3) 미래 문서의 doc_id/rcept_no가 플레이 전 노출 영역(available_documents, evidence,
     intro, mission, decision_options)에 단 한 번도 등장하지 않는다
  4) 모든 evidence.source_text는 해당 문서 original_text의 부분 문자열이다
  5) evidence.text에 등장하는 모든 숫자는 source_text에 존재한다 (게임용 수치 날조 방지)
하나라도 깨지면 해당 Case는 INVALID이며 exit code 1.

사용법:
    PYTHONIOENCODING=utf-8 python scripts/validate_case_pack.py
    PYTHONIOENCODING=utf-8 python scripts/validate_case_pack.py data/artifacts/case_packs/CASE-001.json
    PYTHONIOENCODING=utf-8 python scripts/validate_case_pack.py --strict   # 경고도 실패로 취급
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACK_DIR = REPO / "data" / "artifacts" / "case_packs"
SCHEMA_PATH = REPO / "schemas" / "case_pack_schema_v0.json"
MANIFEST_PATH = REPO / "data" / "3.공시" / "corpus" / "manifest.jsonl"

NUM_RE = re.compile(r"\d[\d,\.]*")


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def norm_num(tok: str) -> str:
    """1,200억 / 1200 / 1,200.0 을 비교 가능한 형태로 정규화."""
    tok = tok.replace(",", "").rstrip(".")
    if tok.endswith(".0"):
        tok = tok[:-2]
    return tok


def numbers_in(text: str) -> list[str]:
    return [norm_num(m.group()) for m in NUM_RE.finditer(text)]


# 원문이 '원' 단위일 때 evidence.text에 억원/백만원/만원 환산값을 쓰는 것만 허용한다.
# 그 외의 새 숫자는 전부 '원문에 없는 수치'로 간주해 실패시킨다.
_UNIT_DIVISORS = (10_000, 1_000_000, 100_000_000, 1_000_000_000_000)


def allowed_numbers(source_text: str) -> set[str]:
    allowed = set()
    for tok in numbers_in(source_text):
        allowed.add(tok)
        if tok.isdigit():
            n = int(tok)
            for d in _UNIT_DIVISORS:
                if n >= d:
                    allowed.add(str(n // d))
    return allowed


class Report:
    def __init__(self, case_id: str):
        self.case_id = case_id
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks: dict[str, int | bool] = {}

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def check_future_leakage(pack: dict, rep: Report) -> None:
    sim = parse_date(pack["simulation_date"])
    docs = pack["available_documents"]
    futures = pack["future_events"]

    for d in docs:
        dd = parse_date(d["document_date"])
        if dd > sim:
            rep.err(f"[leakage] available_documents {d['document_id']}({d['doc_id']}) "
                    f"document_date={dd} > simulation_date={sim}")
    for i, fe in enumerate(futures):
        fd = parse_date(fe["date"])
        if fd <= sim:
            rep.err(f"[leakage] future_events[{i}] date={fd} <= simulation_date={sim}")

    # 미래 문서 식별자가 플레이 전 영역에 문자열로도 새어나오지 않아야 한다.
    future_ids = {fe["source_document_id"] for fe in futures}
    future_rcept = {fid.split("_", 1)[1] for fid in future_ids if "_" in fid}
    pre_play = json.dumps(
        {
            "intro": pack["intro"],
            "mission": pack["mission"],
            "available_documents": docs,
            "evidence": pack["evidence"],
            "finance_terms": pack["finance_terms"],
            "decision_options": pack["decision_options"],
        },
        ensure_ascii=False,
    )
    for fid in sorted(future_ids | future_rcept):
        if fid in pre_play:
            rep.err(f"[leakage] 미래 문서 식별자 '{fid}'가 플레이 전 영역에 노출됨")

    # 미래 날짜 문자열(YYYY-MM-DD)이 플레이 전 영역에 있으면 경고.
    # 공시 원문 자체가 미래 예정일(투자 종료일 등)을 담는 것은 정상이므로 error가 아니다.
    for m in set(re.findall(r"\d{4}-\d{2}-\d{2}", pre_play)):
        try:
            if parse_date(m) > sim:
                rep.warn(f"[future-date] 플레이 전 영역에 simulation_date 이후 날짜 '{m}' 등장 "
                         f"(공시 원문의 예정일이면 정상)")
        except ValueError:
            pass

    rep.checks["n_available_documents"] = len(docs)
    rep.checks["n_future_events"] = len(futures)
    rep.checks["future_leakage"] = any(e.startswith("[leakage]") for e in rep.errors)


def check_grounding(pack: dict, rep: Report) -> None:
    by_id = {d["document_id"]: d for d in pack["available_documents"]}

    for d in pack["available_documents"]:
        if d["display_excerpt"] not in d["original_text"]:
            rep.err(f"[grounding] {d['document_id']}.display_excerpt가 original_text의 "
                    f"부분 문자열이 아님")

    n_ok = 0
    for ev in pack["evidence"]:
        doc = by_id.get(ev["document_id"])
        if doc is None:
            rep.err(f"[ref] {ev['evidence_id']}가 존재하지 않는 문서 {ev['document_id']} 참조")
            continue
        if ev["source_text"] not in doc["original_text"]:
            rep.err(f"[grounding] {ev['evidence_id']}.source_text가 "
                    f"{ev['document_id']}.original_text에 없음")
            continue
        src_nums = allowed_numbers(ev["source_text"])
        missing = [n for n in numbers_in(ev["text"]) if n not in src_nums]
        if missing:
            rep.err(f"[grounding] {ev['evidence_id']}.text의 숫자 {missing}가 source_text에 없음 "
                    f"(게임용 수치 날조 의심)")
            continue
        n_ok += 1

    rep.checks["n_evidence"] = len(pack["evidence"])
    rep.checks["n_evidence_grounded"] = n_ok
    rep.checks["all_evidence_grounded"] = n_ok == len(pack["evidence"])


def check_references(pack: dict, rep: Report) -> None:
    ev_ids = {e["evidence_id"] for e in pack["evidence"]}
    for t in pack["finance_terms"]:
        for eid in t["source_evidence_ids"]:
            if eid not in ev_ids:
                rep.err(f"[ref] finance_term '{t['term']}'가 없는 evidence {eid} 참조")
    for o in pack["decision_options"]:
        for key in ("supporting_evidence_ids", "counter_evidence_ids"):
            for eid in o[key]:
                if eid not in ev_ids:
                    rep.err(f"[ref] decision_option {o['option_id']}.{key}가 없는 evidence "
                            f"{eid} 참조")
    n_critical = sum(1 for e in pack["evidence"] if e["importance"] == "critical")
    if n_critical < 3:
        rep.warn(f"[quality] critical evidence가 {n_critical}건뿐 (권장 3건 이상)")
    rep.checks["n_critical_evidence"] = n_critical
    rep.checks["n_finance_terms"] = len(pack["finance_terms"])
    rep.checks["n_decision_options"] = len(pack["decision_options"])


def check_manifest_consistency(pack: dict, manifest: dict[str, dict], rep: Report) -> None:
    if not manifest:
        rep.warn("[manifest] manifest.jsonl 없음 - 원본 대조 생략")
        return
    for d in pack["available_documents"]:
        m = manifest.get(d["doc_id"])
        if m is None:
            rep.err(f"[manifest] {d['doc_id']}가 corpus manifest에 없음")
            continue
        expect = f"{m['rcept_dt'][:4]}-{m['rcept_dt'][4:6]}-{m['rcept_dt'][6:]}"
        if expect != d["document_date"]:
            rep.err(f"[manifest] {d['doc_id']} document_date={d['document_date']} != "
                    f"manifest rcept_dt={expect}")
        if m["corp_code"] != pack["company"]["corp_code"]:
            rep.err(f"[manifest] {d['doc_id']}는 다른 기업({m['corp_name']}) 문서")
    for fe in pack["future_events"]:
        m = manifest.get(fe["source_document_id"])
        if m is None:
            rep.err(f"[manifest] future_event 원본 {fe['source_document_id']}가 manifest에 없음")
            continue
        expect = f"{m['rcept_dt'][:4]}-{m['rcept_dt'][4:6]}-{m['rcept_dt'][6:]}"
        if expect != fe["date"]:
            rep.err(f"[manifest] future_event {fe['source_document_id']} date={fe['date']} != "
                    f"manifest rcept_dt={expect}")


def check_schema(pack: dict, rep: Report) -> None:
    try:
        import jsonschema
    except ImportError:
        rep.warn("[schema] jsonschema 미설치 - JSON Schema 검증 생략 (pip install jsonschema)")
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for e in jsonschema.Draft202012Validator(schema).iter_errors(pack):
        rep.err(f"[schema] {'/'.join(str(p) for p in e.absolute_path)}: {e.message}")


def load_manifest() -> dict[str, dict]:
    if not MANIFEST_PATH.exists():
        return {}
    out = {}
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["doc_id"]] = r
    return out


def validate(path: Path, manifest: dict[str, dict]) -> Report:
    pack = json.loads(path.read_text(encoding="utf-8"))
    rep = Report(pack.get("case_id", path.stem))
    check_schema(pack, rep)
    check_future_leakage(pack, rep)
    check_grounding(pack, rep)
    check_references(pack, rep)
    check_manifest_consistency(pack, manifest, rep)

    # 팩 안에 기록된 validation 블록이 실제 검사 결과와 일치하는지 대조
    declared = pack.get("validation", {})
    if declared.get("future_leakage") is not False:
        rep.err("[validation] validation.future_leakage는 false여야 한다")
    if declared.get("all_evidence_grounded") is not True:
        rep.err("[validation] validation.all_evidence_grounded는 true여야 한다")
    if rep.checks.get("future_leakage") is True:
        rep.err("[validation] 실제 leakage가 검출되었는데 팩은 false로 선언함")
    if rep.checks.get("all_evidence_grounded") is False:
        rep.err("[validation] grounding 실패가 있는데 팩은 true로 선언함")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="검증할 Case Pack JSON (생략 시 case_packs/CASE-*.json 전부)")
    ap.add_argument("--strict", action="store_true", help="경고도 실패로 취급")
    args = ap.parse_args()

    paths = [Path(p) for p in args.paths] or sorted(PACK_DIR.glob("CASE-*.json"))
    if not paths:
        print("검증할 Case Pack이 없다. 먼저 scripts/build_case_packs.py를 실행하라.", file=sys.stderr)
        return 1

    manifest = load_manifest()
    n_fail = 0
    for p in paths:
        rep = validate(p, manifest)
        status = "INVALID" if rep.errors else ("WARN" if rep.warnings else "VALID")
        print(f"=== {rep.case_id} [{status}] {p.name}")
        for k, v in rep.checks.items():
            print(f"    {k}: {v}")
        for e in rep.errors:
            print(f"    ERROR   {e}")
        for w in rep.warnings:
            print(f"    WARNING {w}")
        if rep.errors or (args.strict and rep.warnings):
            n_fail += 1

    print(f"\n{len(paths) - n_fail}/{len(paths)} case packs valid")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
