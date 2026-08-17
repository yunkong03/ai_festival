"""Tutor Agent — 정답을 알려주지 않고 스스로 조사하게 만드는 힌트.

나쁜 답변: "투자 규모가 너무 크므로 축소해야 합니다."
좋은 답변: "투자금액만 보면 규모를 판단하기 어려워요. 회사 전체 규모와 비교할 수 있는
           숫자를 찾아보면 어떨까요?"

힌트 3단계:
    Level 1  방향만
    Level 2  찾아야 할 정보의 종류
    Level 3  관련 문서 위치

안전장치: 어떤 단계에서도 힌트 문장에 **숫자를 넣지 않는다**. 숫자가 들어가면
결론이 새어나가므로, 생성된 힌트에 숫자가 있으면 템플릿 힌트로 되돌린다.
"""
from __future__ import annotations

import re
from typing import Any

from ..llm import LLMResult, LLMUnavailable

MAX_LEVEL = 3

_DIGIT_RE = re.compile(r"\d")

CATEGORY_DIRECTION: dict[str, str] = {
    "finance": "숫자 하나만 보면 크고 작음을 알 수 없어요. 회사 전체 체력과 비교할 수 있는 "
               "재무 항목을 찾아보면 어떨까요?",
    "investment": "결정문에 적힌 내용 자체를 다시 읽어보세요. 회사가 무엇을 얼마 동안 "
                  "하겠다고 했는지가 판단의 출발점이에요.",
    "business": "이 회사가 무엇을 팔아서 돈을 버는지, 그 물량이 늘고 있는지부터 확인해보세요.",
    "risk": "좋은 신호만 모으면 판단이 한쪽으로 기울어요. 반대 방향을 가리키는 문장도 "
            "같은 문서 안에 있을 수 있어요.",
    "timeline": "언제까지 하겠다고 했는지 확인해보세요. 기간이 바뀌면 부담의 크기도 달라져요.",
}

CATEGORY_INFO_TYPE: dict[str, str] = {
    "finance": "재무제표 요약에서 회사가 가진 돈과 갚아야 할 돈, 그리고 한 분기에 버는 이익을 "
               "찾아 투자금액과 나란히 놓아보세요.",
    "investment": "결정 공시의 금액·비율·기간 항목을 항목명 그대로 확인해보세요.",
    "business": "생산능력, 매출 실적, 수주 현황처럼 물량과 금액이 함께 적힌 표를 찾아보세요.",
    "risk": "원재료 가격 추이, 매출처 집중도, 신용등급처럼 회사가 통제하지 못하는 변수를 "
            "다룬 문단을 찾아보세요.",
    "timeline": "시작일과 종료일이 적힌 항목, 그리고 그 기간이 바뀔 수 있다고 밝힌 문장을 "
                "찾아보세요.",
}

HINT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"hint": {"type": "string"}},
    "required": ["hint"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """너는 금융 교육용 튜터다. 플레이어가 스스로 조사하도록 방향만 알려준다.

절대 규칙:
- 결론(충분하다/부족하다/축소해야 한다)을 말하지 마라.
- 숫자를 쓰지 마라. 금액, 비율, 연도 전부 금지다.
- 한두 문장으로 짧게, 질문형으로 끝내라.
- 플레이어가 아직 확인하지 않은 관점 하나만 가리켜라."""


def _target_evidence(pack_evidence: list[dict[str, Any]], found: list[str]) -> dict[str, Any] | None:
    """아직 수집되지 않은 critical evidence 중 첫 번째."""
    remaining = [e for e in pack_evidence
                 if e["importance"] == "critical" and e["evidence_id"] not in found]
    if remaining:
        return remaining[0]
    remaining = [e for e in pack_evidence if e["evidence_id"] not in found]
    return remaining[0] if remaining else None


def _template_hint(level: int, target: dict[str, Any] | None,
                   documents: list[dict[str, Any]]) -> str:
    if target is None:
        return ("critical 단서는 모두 모았어요. 지금까지 모은 근거만으로 판단을 내려도 "
                "설명이 되는지 스스로 점검해보세요.")
    category = target.get("category", "finance")
    if level <= 1:
        return CATEGORY_DIRECTION.get(category, CATEGORY_DIRECTION["finance"])
    if level == 2:
        return CATEGORY_INFO_TYPE.get(category, CATEGORY_INFO_TYPE["finance"])
    doc = next((d for d in documents if d["document_id"] == target["document_id"]), None)
    title = doc["title"] if doc else target["document_id"]
    return f"'{title}' 문서를 열어보세요. 거기에 지금 필요한 항목이 있어요."


def _sanitize(hint: str, fallback: str) -> tuple[str, bool]:
    """숫자가 섞이면 결론이 새어나간 것으로 보고 템플릿으로 되돌린다."""
    if _DIGIT_RE.search(hint):
        return fallback, True
    return hint, False


def give_hint(
    *,
    pack_evidence: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    found_evidence: list[str],
    level: int,
    llm: Any | None = None,
    case_title: str = "",
) -> dict[str, Any]:
    level = max(1, min(MAX_LEVEL, level))
    target = _target_evidence(pack_evidence, found_evidence)
    template = _template_hint(level, target, documents)

    llm_meta: dict[str, Any] = {"used": False}
    hint = template
    sanitized = False

    # Level 3는 문서 위치를 정확히 지목해야 하므로 템플릿을 그대로 쓴다.
    if llm is not None and target is not None and level < 3:
        try:
            user = (
                f"사건: {case_title}\n"
                f"플레이어가 아직 확인하지 않은 관점: {target.get('category')}\n"
                f"그 관점이 중요한 이유(그대로 말하지 말고 방향만 암시할 것): "
                f"{target.get('educational_reason', '')}\n"
                f"힌트 단계: Level {level} "
                f"({'방향만' if level == 1 else '찾아야 할 정보의 종류'})\n"
                "숫자를 쓰지 말고, 한두 문장으로 힌트를 만들어라."
            )
            result: LLMResult = llm.complete_json(SYSTEM_PROMPT, user, HINT_SCHEMA)
            hint, sanitized = _sanitize(result.data.get("hint", "").strip() or template,
                                        template)
            llm_meta = {
                "used": True,
                "provider": result.provider,
                "model": result.model,
                "latency_ms": result.latency_ms,
                "usage": result.usage,
                "sanitized": sanitized,
            }
        except (LLMUnavailable, Exception) as exc:  # noqa: BLE001
            llm_meta = {"used": False, "error": f"{type(exc).__name__}: {exc}"}
            hint = template

    return {
        "level": level,
        "hint": hint,
        "target_category": target.get("category") if target else None,
        "target_document_id": target["document_id"] if (target and level >= 3) else None,
        "remaining_critical": [
            e["evidence_id"] for e in pack_evidence
            if e["importance"] == "critical" and e["evidence_id"] not in found_evidence
        ],
        "contains_digits": bool(_DIGIT_RE.search(hint)),
        "llm": llm_meta,
    }
