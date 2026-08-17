"""LangGraph GameState 정의.

State는 명시적으로 선언한다 — 노드가 무엇을 읽고 무엇을 쓰는지 코드로 드러나야
trace와 checkpoint가 의미를 갖는다.
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

Action = Literal["research", "hint", "term", "decision", "replay", "open_document"]

ACTIONS: tuple[str, ...] = ("research", "hint", "term", "decision", "replay", "open_document")

# 행동별 조사 포인트 비용. 버튼으로 구분되는 행동이라 LLM routing을 쓰지 않는 것처럼,
# 비용도 결정론적으로 고정한다.
ACTION_COST: dict[str, int] = {
    "open_document": 5,
    "research": 10,
    "hint": 15,
    "term": 0,
    "decision": 0,
    "replay": 0,
}

INITIAL_POINTS = 100


class GameState(TypedDict, total=False):
    # --- 케이스 고정값 ---
    case_id: str
    simulation_date: str
    points_enabled: bool          # False면 조사 포인트를 차감하지 않는다(데모 편의)

    # --- 플레이어 진행 상태 ---
    opened_documents: list[str]      # document_id ("D01" …)
    found_evidence: list[str]        # evidence_id ("E01" …)
    learned_terms: list[str]         # finance_terms[].term
    investigation_points: int

    # --- 대화 로그 ---
    conversation: list[dict[str, Any]]

    # --- 판단 / 미래 공개 ---
    decision: str | None
    decision_record: dict[str, Any] | None
    future_unlocked: bool
    future_events: list[dict[str, Any]]

    # --- 힌트 단계(1~3) ---
    hint_level: int

    # --- 이번 턴 입력/출력 ---
    action: str
    action_input: dict[str, Any]
    last_response: dict[str, Any]
    error: str | None

    # --- trace ---
    trace: list[dict[str, Any]]


def new_state(case_id: str, simulation_date: str,
              points_enabled: bool = True) -> GameState:
    return GameState(
        case_id=case_id,
        simulation_date=simulation_date,
        points_enabled=points_enabled,
        opened_documents=[],
        found_evidence=[],
        learned_terms=[],
        investigation_points=INITIAL_POINTS,
        conversation=[],
        decision=None,
        decision_record=None,
        future_unlocked=False,
        future_events=[],
        hint_level=0,
        action="",
        action_input={},
        last_response={},
        error=None,
        trace=[],
    )


def public_state(state: GameState) -> dict[str, Any]:
    """프론트엔드에 내려보내는 상태. future_events는 unlock 전에는 절대 나가지 않는다."""
    out = {
        "case_id": state.get("case_id"),
        "simulation_date": state.get("simulation_date"),
        "opened_documents": list(state.get("opened_documents") or []),
        "found_evidence": list(state.get("found_evidence") or []),
        "learned_terms": list(state.get("learned_terms") or []),
        "investigation_points": state.get("investigation_points"),
        "points_enabled": bool(state.get("points_enabled", True)),
        "decision": state.get("decision"),
        "decision_record": state.get("decision_record"),
        "future_unlocked": bool(state.get("future_unlocked")),
        "hint_level": state.get("hint_level", 0),
        "conversation": list(state.get("conversation") or []),
    }
    if state.get("future_unlocked"):
        out["future_events"] = list(state.get("future_events") or [])
    return out
