"""Case Pack 검증기 자체를 검증한다.

빌드된 팩이 통과하는 것만으로는 부족하다 — 검증기가 실제로 leakage/날조를 잡는지
망가뜨린 팩으로 확인한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from validate_case_pack import (  # noqa: E402
    Report,
    allowed_numbers,
    check_future_leakage,
    check_grounding,
    check_references,
)

PACK_DIR = REPO / "data" / "artifacts" / "case_packs"
PACK_PATHS = sorted(PACK_DIR.glob("CASE-*.json"))
requires_packs = pytest.mark.skipif(
    not PACK_PATHS,
    reason="Case Pack 없음 - scripts/build_case_packs.py를 먼저 실행하라",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@requires_packs
@pytest.mark.parametrize("path", PACK_PATHS, ids=lambda p: p.stem)
def test_built_pack_has_no_leakage_and_is_grounded(path: Path) -> None:
    pack = load(path)
    rep = Report(pack["case_id"])
    check_future_leakage(pack, rep)
    check_grounding(pack, rep)
    check_references(pack, rep)
    assert rep.errors == []
    assert rep.checks["all_evidence_grounded"] is True
    assert rep.checks["future_leakage"] is False


@requires_packs
def test_detects_future_document_in_available_documents() -> None:
    """미래 문서를 available_documents에 끼워 넣으면 반드시 잡혀야 한다."""
    pack = load(PACK_PATHS[0])
    doc = dict(pack["available_documents"][0])
    doc["document_id"] = "D99"
    doc["document_date"] = pack["future_events"][-1]["date"]
    pack["available_documents"].append(doc)

    rep = Report(pack["case_id"])
    check_future_leakage(pack, rep)
    assert any(e.startswith("[leakage]") for e in rep.errors)
    assert rep.checks["future_leakage"] is True


@requires_packs
def test_detects_future_doc_id_leaked_into_intro() -> None:
    """미래 공시의 doc_id가 intro에 새어 들어가면 잡혀야 한다."""
    pack = load(PACK_PATHS[0])
    leaked = pack["future_events"][0]["source_document_id"]
    pack["intro"] = pack["intro"] + f" (참고: {leaked})"

    rep = Report(pack["case_id"])
    check_future_leakage(pack, rep)
    assert any("새어나" in e or leaked in e for e in rep.errors)


@requires_packs
def test_detects_fabricated_number_in_evidence_text() -> None:
    """원문에 없는 숫자를 evidence.text에 넣으면 잡혀야 한다."""
    pack = load(PACK_PATHS[0])
    pack["evidence"][0]["text"] = "투자금액은 999,999,999,999원이다."

    rep = Report(pack["case_id"])
    check_grounding(pack, rep)
    assert any("날조" in e for e in rep.errors)
    assert rep.checks["all_evidence_grounded"] is False


@requires_packs
def test_detects_ungrounded_source_text() -> None:
    """source_text가 원문에 없으면 잡혀야 한다."""
    pack = load(PACK_PATHS[0])
    pack["evidence"][0]["source_text"] = "이 문장은 어떤 공시에도 없다."

    rep = Report(pack["case_id"])
    check_grounding(pack, rep)
    assert any("original_text에 없음" in e for e in rep.errors)


@requires_packs
def test_detects_dangling_evidence_reference() -> None:
    pack = load(PACK_PATHS[0])
    pack["finance_terms"][0]["source_evidence_ids"] = ["E99"]

    rep = Report(pack["case_id"])
    check_references(pack, rep)
    assert any("E99" in e for e in rep.errors)


def test_allowed_numbers_permits_only_unit_conversion() -> None:
    allowed = allowed_numbers("2. 투자내역 | 투자금액(원) | 473,200,000,000")
    assert "473200000000" in allowed
    assert "4732" in allowed          # 억원 환산은 허용
    assert "473200" in allowed        # 백만원 환산도 허용
    assert "47320000" in allowed      # 만원 환산도 허용
    assert "4733" not in allowed      # 근처 값이라도 새 숫자는 불허
    assert "999999999999" not in allowed
