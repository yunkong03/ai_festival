"""LangGraph 노드 구현 + Deterministic Action Router.

버튼으로 명확히 구분되는 행동에는 LLM routing을 쓰지 않는다. `state["action"]`
문자열을 그대로 노드 이름에 매핑한다. LLM은 research(자유질문 해석)와
hint(문장 생성)에서만 등장한다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableConfig

from .agents import evidence_agent, tutor_agent
from .case_store import CasePack
from .errors import FutureLeakageError
from .llm import get_llm
from .retriever import PointInTimeRetriever
from .state import ACTION_COST, ACTIONS, GameState, public_state
from .trace import TraceRecorder

# 판단 피드백에 쓰는 조사 관점 <-> evidence category 매핑
PERSPECTIVES: dict[str, str] = {
    "재무여력 조사": "finance",
    "시장성 조사": "business",
    "위험 조사": "risk",
    "투자규모 조사": "investment",
    "판단 수정 가능성": "timeline",
}


@dataclass
class SessionRuntime:
    """State에 넣을 수 없는(직렬화 불가) 세션 부품."""

    session_id: str
    pack: CasePack
    retriever: PointInTimeRetriever
    trace: TraceRecorder
    llm: Any | None = field(default=None)


_RUNTIMES: dict[str, SessionRuntime] = {}


def register_runtime(runtime: SessionRuntime) -> None:
    _RUNTIMES[runtime.session_id] = runtime


def get_runtime(session_id: str) -> SessionRuntime:
    if session_id not in _RUNTIMES:
        raise KeyError(f"runtime 미등록: {session_id}")
    return _RUNTIMES[session_id]


def drop_runtime(session_id: str) -> None:
    _RUNTIMES.pop(session_id, None)


# Retriever는 읽기 전용(chunk + BM25 통계)이라 세션끼리 공유해도 안전하다.
# case별로 한 번만 만든다 — 세션마다 인덱스 파일을 다시 읽고 BM25를 다시 세우면
# 동시 접속이 늘 때 메모리와 세션 생성 지연이 그대로 배로 늘어난다.
_RETRIEVERS: dict[tuple[str, str, str], PointInTimeRetriever] = {}


def get_retriever(index_path: Any, case_id: str, simulation_date: str
                  ) -> PointInTimeRetriever:
    key = (str(index_path), case_id, simulation_date)
    if key not in _RETRIEVERS:
        _RETRIEVERS[key] = PointInTimeRetriever.from_index_file(
            index_path, case_id=case_id, simulation_date=simulation_date
        )
    return _RETRIEVERS[key]


def make_runtime(session_id: str, pack: CasePack, index_path: Any,
                 use_llm: bool = True) -> SessionRuntime:
    retriever = get_retriever(index_path, pack.case_id, pack.simulation_date)
    runtime = SessionRuntime(
        session_id=session_id,
        pack=pack,
        retriever=retriever,
        trace=TraceRecorder(session_id),
        llm=get_llm() if use_llm else None,
    )
    register_runtime(runtime)
    return runtime


def _runtime_from_config(config: RunnableConfig) -> SessionRuntime:
    return get_runtime(config["configurable"]["thread_id"])


# ---------------------------------------------------------------- entry / router

def entry_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    """행동 유효성 + 조사 포인트 차감. 여기서 걸리면 아무 노드도 실행되지 않는다."""
    action = state.get("action", "")
    if action not in ACTIONS:
        return {"error": f"알 수 없는 action: {action!r} (허용: {', '.join(ACTIONS)})",
                "last_response": {}}
    cost = ACTION_COST[action] if state.get("points_enabled", True) else 0
    points = state.get("investigation_points", 0)
    if cost and points < cost:
        return {"error": f"조사 포인트 부족: {action}에는 {cost}점이 필요하나 {points}점 남음",
                "last_response": {}}
    return {"error": None, "investigation_points": points - cost}


def route_action(state: GameState) -> str:
    """Deterministic Router — LLM을 부르지 않는다."""
    if state.get("error"):
        return "end"
    return state.get("action", "end")


# ---------------------------------------------------------------- nodes

def _finish(runtime: SessionRuntime, state: GameState, node: str, updates: dict[str, Any],
            *, started: float, retriever_query: str | None = None,
            retrieved: list[dict[str, Any]] | None = None,
            agent_output: dict[str, Any] | None = None,
            validation: dict[str, Any] | None = None,
            llm: dict[str, Any] | None = None,
            error: str | None = None) -> dict[str, Any]:
    latency_ms = int((time.perf_counter() - started) * 1000)
    after = {**state, **updates}
    entry = runtime.trace.turn(
        action=state.get("action", ""),
        node=node,
        state_before=public_state(state),
        state_after=public_state(after),  # type: ignore[arg-type]
        retriever_query=retriever_query,
        retrieved=retrieved,
        date_filter={
            "simulation_date": runtime.retriever.simulation_date,
            "rule": "document_date <= simulation_date",
            **runtime.retriever.stats(),
        },
        agent_output=agent_output,
        validation=validation,
        llm=llm,
        latency_ms=latency_ms,
        error=error,
    )
    updates["trace"] = list(state.get("trace") or []) + [{
        "trace_id": entry["trace_id"], "node": node, "action": state.get("action"),
        "latency_ms": latency_ms, "error": error,
    }]
    return updates


def open_document_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    started = time.perf_counter()
    rt = _runtime_from_config(config)
    document_id = (state.get("action_input") or {}).get("document_id", "")
    doc = rt.pack.document(document_id)
    if doc is None:
        return _finish(rt, state, "open_document",
                       {"error": f"존재하지 않는 document_id: {document_id!r}"},
                       started=started, error="unknown_document")

    opened = list(state.get("opened_documents") or [])
    if document_id not in opened:
        opened.append(document_id)

    collect = list((state.get("action_input") or {}).get("collect") or [])
    found = list(state.get("found_evidence") or [])
    in_doc = {e["evidence_id"] for e in rt.pack.evidence if e["document_id"] == document_id}
    newly = [eid for eid in collect if eid in in_doc and eid not in found]
    found.extend(newly)

    response = {
        "type": "document",
        "document_id": doc["document_id"],
        "title": doc["title"],
        "document_date": doc["document_date"],
        "original_text": doc["original_text"],
        "evidence_options": [
            {"evidence_id": e["evidence_id"], "document_id": e["document_id"],
             "text": e["text"], "source_text": e["source_text"],
             "category": e["category"], "importance": e["importance"],
             "educational_reason": e["educational_reason"],
             "collected": e["evidence_id"] in found}
            for e in rt.pack.evidence if e["document_id"] == document_id
        ],
        "newly_collected": newly,
    }
    conv = list(state.get("conversation") or [])
    conv.append({"role": "system", "action": "open_document", "document_id": document_id})
    return _finish(rt, state, "open_document",
                   {"opened_documents": opened, "found_evidence": found,
                    "conversation": conv, "last_response": response},
                   started=started, agent_output={"document_id": document_id,
                                                  "newly_collected": newly})


def research_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    started = time.perf_counter()
    rt = _runtime_from_config(config)
    question = (state.get("action_input") or {}).get("question", "").strip()
    if not question:
        return _finish(rt, state, "research", {"error": "question이 비어 있다"},
                       started=started, error="empty_question")

    try:
        result = evidence_agent.answer_question(
            question, rt.retriever, llm=rt.llm, simulation_date=rt.pack.simulation_date
        )
    except FutureLeakageError as exc:
        return _finish(rt, state, "research",
                       {"error": f"FutureLeakageError: {exc}"},
                       started=started, error=str(exc),
                       agent_output={"offending": exc.offending})

    found = list(state.get("found_evidence") or [])
    newly = [eid for eid in evidence_agent.match_case_evidence(rt.pack.evidence,
                                                              result["retrieved"])
             if eid not in found]
    found.extend(newly)

    conv = list(state.get("conversation") or [])
    conv.append({"role": "user", "action": "research", "content": question})
    conv.append({"role": "assistant", "action": "research", "content": result["answer"],
                 "evidence": result["evidence"], "uncertainty": result["uncertainty"],
                 "validation_status": result["validation"]["status"]})

    response = {
        "type": "research",
        "answer": result["answer"],
        "evidence": result["evidence"],
        "uncertainty": result["uncertainty"],
        "retrieved": result["retrieved"],
        "validation": result["validation"],
        "newly_collected": newly,
    }
    return _finish(rt, state, "research",
                   {"found_evidence": found, "conversation": conv,
                    "last_response": response},
                   started=started, retriever_query=question,
                   retrieved=result["retrieved"], agent_output={
                       "answer": result["answer"], "evidence": result["evidence"],
                       "uncertainty": result["uncertainty"],
                       "degraded_from": result["degraded_from"]},
                   validation=result["validation"], llm=result["llm"])


def hint_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    started = time.perf_counter()
    rt = _runtime_from_config(config)
    requested = (state.get("action_input") or {}).get("level")
    level = int(requested) if requested else min(tutor_agent.MAX_LEVEL,
                                                 state.get("hint_level", 0) + 1)
    result = tutor_agent.give_hint(
        pack_evidence=rt.pack.evidence,
        documents=rt.pack.documents,
        found_evidence=list(state.get("found_evidence") or []),
        level=level,
        llm=rt.llm,
        case_title=rt.pack.raw.get("case_title", ""),
    )
    conv = list(state.get("conversation") or [])
    conv.append({"role": "assistant", "action": "hint", "level": result["level"],
                 "content": result["hint"]})
    response = {"type": "hint", **result}
    return _finish(rt, state, "hint",
                   {"hint_level": result["level"], "conversation": conv,
                    "last_response": response},
                   started=started, agent_output=result, llm=result["llm"])


def term_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    started = time.perf_counter()
    rt = _runtime_from_config(config)
    requested = (state.get("action_input") or {}).get("term")
    learned = list(state.get("learned_terms") or [])

    if requested:
        term = next((t for t in rt.pack.finance_terms if t["term"] == requested), None)
        if term is None:
            return _finish(rt, state, "term",
                           {"error": f"존재하지 않는 용어: {requested!r}"},
                           started=started, error="unknown_term")
        if term["term"] not in learned:
            learned.append(term["term"])
        response = {"type": "term", "term": term,
                    "unlocked_by_evidence": [
                        eid for eid in term["source_evidence_ids"]
                        if eid in (state.get("found_evidence") or [])]}
    else:
        response = {
            "type": "term_list",
            "terms": [
                {"term": t["term"], "short_definition": t["short_definition"],
                 "learned": t["term"] in learned,
                 "source_evidence_ids": t["source_evidence_ids"]}
                for t in rt.pack.finance_terms
            ],
        }
    return _finish(rt, state, "term",
                   {"learned_terms": learned, "last_response": response},
                   started=started, agent_output={"requested": requested})


def _investigation_summary(pack: CasePack, found: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for label, category in PERSPECTIVES.items():
        pool = [e for e in pack.evidence if e["category"] == category]
        got = [e["evidence_id"] for e in pool if e["evidence_id"] in found]
        summary[label] = {
            "checked": len(got),
            "total": len(pool),
            "evidence_ids": got,
            "covered": bool(pool) and len(got) == len(pool),
        }
    critical = [e["evidence_id"] for e in pack.critical_evidence()]
    summary["critical_coverage"] = {
        "checked": len([e for e in critical if e in found]),
        "total": len(critical),
        "missing": [e for e in critical if e not in found],
    }
    return summary


def decision_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    started = time.perf_counter()
    rt = _runtime_from_config(config)
    ai = state.get("action_input") or {}
    option_id = ai.get("option_id", "")
    option = next((o for o in rt.pack.decision_options if o["option_id"] == option_id), None)
    if option is None:
        return _finish(rt, state, "decision",
                       {"error": f"존재하지 않는 option_id: {option_id!r}"},
                       started=started, error="unknown_option")

    found = list(state.get("found_evidence") or [])
    used = list(ai.get("used_evidence_ids") or found)
    summary = _investigation_summary(rt.pack, found)

    supporting = [e for e in option["supporting_evidence_ids"] if e in used]
    counter = [e for e in option["counter_evidence_ids"] if e in used]
    missing_counter = [e for e in option["counter_evidence_ids"] if e not in used]

    feedback: list[str] = []
    if supporting:
        feedback.append(f"이 선택을 뒷받침하는 근거 {len(supporting)}건을 실제로 확인했다: "
                        f"{', '.join(supporting)}.")
    else:
        feedback.append("이 선택을 뒷받침하는 근거를 하나도 확인하지 않았다.")
    if missing_counter:
        feedback.append(f"반대 방향 근거 {', '.join(missing_counter)}는 확인하지 않았다. "
                        f"반대 근거를 보지 않은 판단은 근거가 한쪽뿐이다.")
    elif counter:
        feedback.append(f"반대 근거 {', '.join(counter)}까지 보고도 이 선택을 했다.")
    if summary["critical_coverage"]["missing"]:
        feedback.append(option.get("feedback_if_missing_critical", ""))

    record = {
        "decision": option["label"],
        "option_id": option_id,
        "used_evidence_ids": used,
        "investigation_summary": summary,
        "feedback": [f for f in feedback if f],
        "note": "실제 기업의 행동과 같은지를 채점하지 않는다. "
                "무엇을 보고 판단했는지가 이 게임이 보는 지점이다.",
    }
    conv = list(state.get("conversation") or [])
    conv.append({"role": "user", "action": "decision", "content": option["label"]})
    conv.append({"role": "assistant", "action": "decision", "content": record["feedback"]})

    return _finish(rt, state, "decision",
                   {"decision": option["label"], "decision_record": record,
                    "conversation": conv,
                    "last_response": {"type": "decision", **record}},
                   started=started, agent_output=record)


def replay_node(state: GameState, config: RunnableConfig) -> dict[str, Any]:
    started = time.perf_counter()
    rt = _runtime_from_config(config)
    if not state.get("decision"):
        return _finish(rt, state, "replay",
                       {"error": "판단을 확정하기 전에는 Reality Replay를 볼 수 없다"},
                       started=started, error="replay_locked")

    # 미래 Event는 LLM이 생성하지 않는다 — Case Pack 데이터를 그대로 쓴다.
    events = [dict(e) for e in rt.pack.future_events]
    conv = list(state.get("conversation") or [])
    conv.append({"role": "system", "action": "replay", "n_events": len(events)})
    response = {
        "type": "replay",
        "simulation_date": rt.pack.simulation_date,
        "future_events": events,
        "your_decision": state.get("decision"),
        "note": "아래는 실제 공시로 확인되는 후속 행동이다. 정답이 아니라 실제 결과다.",
    }
    return _finish(rt, state, "replay",
                   {"future_unlocked": True, "future_events": events,
                    "conversation": conv, "last_response": response},
                   started=started, agent_output={"n_events": len(events)})
