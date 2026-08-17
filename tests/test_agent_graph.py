"""LangGraph 게임 흐름 — 라우팅/상태/잠금 검증.

LLM은 끈다(use_llm=False). 데모의 결정론적 경로가 항상 동작해야 하기 때문이다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dart_detective.graph import DEFAULT_INDEX_PATH, GameServer, build_graph, mermaid
from dart_detective.nodes import route_action
from dart_detective.state import ACTION_COST, INITIAL_POINTS

REPO = Path(__file__).resolve().parent.parent
CASE_ID = "CASE-001"

requires_index = pytest.mark.skipif(
    not Path(DEFAULT_INDEX_PATH).exists(),
    reason="search_index.jsonl 없음 — scripts/build_case_search_index.py 실행 필요",
)


@pytest.fixture
def session():
    server = GameServer(use_llm=False)
    s = server.start(CASE_ID)
    yield s
    server.end(s.session_id)


# ---------------------------------------------------------------- router

def test_router_is_deterministic_and_llm_free():
    for action in ("research", "hint", "term", "decision", "replay", "open_document"):
        assert route_action({"action": action, "error": None}) == action


def test_router_short_circuits_on_error():
    assert route_action({"action": "research", "error": "boom"}) == "end"


def test_unknown_action_is_rejected(session):
    result = session.act("teleport")
    assert result["error"] and "teleport" in result["error"]
    assert result["state"]["investigation_points"] == INITIAL_POINTS


# ---------------------------------------------------------------- state

@requires_index
def test_points_are_charged_per_action(session):
    before = session.state()["investigation_points"]
    session.act("research", question="현금은 얼마인가")
    after = session.state()["investigation_points"]
    assert before - after == ACTION_COST["research"]


@requires_index
def test_term_action_is_free_and_marks_learned(session):
    term = session.pack.finance_terms[0]["term"]
    result = session.act("term", term=term)
    assert result["state"]["investigation_points"] == INITIAL_POINTS
    assert term in result["state"]["learned_terms"]


@requires_index
def test_open_document_collects_only_evidence_in_that_document(session):
    doc_id = session.pack.documents[0]["document_id"]
    other = next(e for e in session.pack.evidence if e["document_id"] != doc_id)
    mine = next(e for e in session.pack.evidence if e["document_id"] == doc_id)
    result = session.act("open_document", document_id=doc_id,
                         collect=[mine["evidence_id"], other["evidence_id"]])
    assert result["response"]["newly_collected"] == [mine["evidence_id"]]
    assert other["evidence_id"] not in result["state"]["found_evidence"]


@requires_index
def test_state_persists_across_actions_via_checkpointer(session):
    doc_id = session.pack.documents[0]["document_id"]
    session.act("open_document", document_id=doc_id)
    session.act("hint")
    state = session.state()
    assert doc_id in state["opened_documents"]
    assert state["hint_level"] == 1


# ---------------------------------------------------------------- research

@requires_index
def test_research_returns_only_past_documents(session):
    result = session.act("research", question="투자금액과 자기자본은 얼마인가")
    assert result["error"] is None
    retrieved = result["response"]["retrieved"]
    assert retrieved
    assert all(d["document_date"] <= session.pack.simulation_date for d in retrieved)


@requires_index
def test_research_answer_is_grounded_without_llm(session):
    result = session.act("research", question="현금성자산은 얼마인가")
    assert result["response"]["validation"]["status"] == "SUPPORTED"


@requires_index
def test_empty_question_is_rejected(session):
    assert session.act("research", question="   ")["error"]


# ---------------------------------------------------------------- tutor

@requires_index
def test_hint_levels_never_leak_numbers(session):
    for level in (1, 2):
        result = session.act("hint", level=level)
        assert not any(ch.isdigit() for ch in result["response"]["hint"])


@requires_index
def test_hint_level_3_points_at_a_document(session):
    result = session.act("hint", level=3)
    assert result["response"]["target_document_id"] in {
        d["document_id"] for d in session.pack.documents
    }


@requires_index
def test_hint_does_not_reveal_evidence_text(session):
    result = session.act("hint", level=1)
    hint = result["response"]["hint"]
    for ev in session.pack.evidence:
        assert ev["text"] not in hint


# ---------------------------------------------------------------- decision / replay

@requires_index
def test_replay_is_locked_before_decision(session):
    result = session.act("replay")
    assert result["error"]
    assert result["state"]["future_unlocked"] is False
    assert "future_events" not in result["state"]


@requires_index
def test_decision_records_summary_without_grading_correctness(session):
    option = session.pack.decision_options[0]
    result = session.act("decision", option_id=option["option_id"])
    record = result["response"]
    assert record["decision"] == option["label"]
    assert "investigation_summary" in record
    assert "critical_coverage" in record["investigation_summary"]
    # 정답 플래그가 저장되지 않아야 한다
    assert "correct" not in record and "is_correct" not in record


@requires_index
def test_replay_unlocks_after_decision_and_uses_pack_data(session):
    session.act("decision", option_id=session.pack.decision_options[0]["option_id"])
    result = session.act("replay")
    assert result["error"] is None
    assert result["state"]["future_unlocked"] is True
    events = result["response"]["future_events"]
    assert events == session.pack.future_events  # LLM 생성이 아니라 Case Pack 그대로
    assert all(e["date"] > session.pack.simulation_date for e in events)


@requires_index
def test_unknown_decision_option_is_rejected(session):
    assert session.act("decision", option_id="O9")["error"]


# ---------------------------------------------------------------- trace

@requires_index
def test_trace_records_required_fields(session):
    session.act("research", question="부채총계는 얼마인가")
    entry = session.trace()[-1]
    for key in ("action", "node", "state_before", "state_after", "retriever_query",
                "retrieved", "date_filter", "agent_output", "validation", "latency_ms"):
        assert key in entry
    assert entry["date_filter"]["rule"] == "document_date <= simulation_date"


# ---------------------------------------------------------------- graph shape

def test_graph_compiles_and_exposes_all_nodes():
    graph = build_graph()
    nodes = set(graph.get_graph().nodes)
    for name in ("entry", "research", "hint", "term", "decision", "replay",
                 "open_document"):
        assert name in nodes


def test_mermaid_diagram_is_available():
    src = mermaid()
    assert "Action Router" in src and "Point-in-Time Retriever" in src
