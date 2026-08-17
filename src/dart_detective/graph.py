"""LangGraph 그래프 조립 + 세션 파사드.

    User
      ↓
    LangGraph Game Master (entry: 유효성 + 포인트)
      ↓
    Action Router (deterministic)
      ├─ research  → Evidence Agent → Point-in-Time Retriever
      ├─ hint      → Tutor Agent
      ├─ term      → Glossary
      ├─ decision  → Decision Evaluator
      └─ replay    → Future Event Unlock
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .case_store import CaseStore, DEFAULT_PACK_DIR
from .errors import SessionNotFoundError
from .nodes import (
    SessionRuntime,
    decision_node,
    drop_runtime,
    entry_node,
    hint_node,
    make_runtime,
    open_document_node,
    replay_node,
    research_node,
    route_action,
    term_node,
)
from .state import GameState, new_state, public_state

DEFAULT_INDEX_PATH = DEFAULT_PACK_DIR / "search_index.jsonl"

NODE_FUNCS = {
    "open_document": open_document_node,
    "research": research_node,
    "hint": hint_node,
    "term": term_node,
    "decision": decision_node,
    "replay": replay_node,
}


def build_graph(checkpointer: Any | None = None):
    builder = StateGraph(GameState)
    builder.add_node("entry", entry_node)
    for name, fn in NODE_FUNCS.items():
        builder.add_node(name, fn)

    builder.add_edge(START, "entry")
    builder.add_conditional_edges(
        "entry",
        route_action,
        {**{name: name for name in NODE_FUNCS}, "end": END},
    )
    for name in NODE_FUNCS:
        builder.add_edge(name, END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())


class GameSession:
    """세션 하나 = LangGraph thread 하나. checkpointer가 상태를 보관한다."""

    def __init__(self, session_id: str, runtime: SessionRuntime, graph: Any):
        self.session_id = session_id
        self.runtime = runtime
        self.graph = graph
        self.config = {"configurable": {"thread_id": session_id}}

    @property
    def pack(self):
        return self.runtime.pack

    def state(self) -> GameState:
        snapshot = self.graph.get_state(self.config)
        return snapshot.values  # type: ignore[return-value]

    def act(self, action: str, **action_input: Any) -> dict[str, Any]:
        result = self.graph.invoke(
            {"action": action, "action_input": action_input, "error": None},
            config=self.config,
        )
        return {
            "session_id": self.session_id,
            "action": action,
            "error": result.get("error"),
            "response": result.get("last_response") or {},
            "state": public_state(result),  # type: ignore[arg-type]
        }

    def trace(self) -> list[dict[str, Any]]:
        return self.runtime.trace.dump()


class GameServer:
    """세션 레지스트리. 그래프는 하나, thread_id로 세션을 가른다.

    공개 배포(아무나 접속)를 견디도록 세션 수와 유휴 시간에 상한을 둔다. 상한이 없으면
    InMemorySaver checkpoint와 SessionRuntime(retriever 포함)이 무한히 쌓인다.
    """

    def __init__(self, pack_dir: Path | str = DEFAULT_PACK_DIR,
                 index_path: Path | str = DEFAULT_INDEX_PATH,
                 use_llm: bool = True,
                 max_sessions: int = 50,
                 session_ttl_sec: int = 1800):
        self.store = CaseStore(pack_dir)
        self.index_path = Path(index_path)
        self.use_llm = use_llm
        self.max_sessions = max_sessions
        self.session_ttl_sec = session_ttl_sec
        self.graph = build_graph()
        self._sessions: dict[str, GameSession] = {}
        self._last_seen: dict[str, float] = {}

    # ---------------- 세션 수명 관리 ----------------
    def _touch(self, session_id: str) -> None:
        self._last_seen[session_id] = time.monotonic()

    def _evict(self) -> int:
        """유휴 세션을 먼저 버리고, 그래도 상한을 넘으면 가장 오래된 것부터 버린다."""
        now = time.monotonic()
        dropped = 0
        for sid, seen in list(self._last_seen.items()):
            if now - seen > self.session_ttl_sec:
                self.end(sid)
                dropped += 1
        while len(self._sessions) > self.max_sessions:
            oldest = min(self._last_seen, key=self._last_seen.get)  # type: ignore[arg-type]
            self.end(oldest)
            dropped += 1
        return dropped

    def stats(self) -> dict[str, Any]:
        return {
            "active_sessions": len(self._sessions),
            "max_sessions": self.max_sessions,
            "session_ttl_sec": self.session_ttl_sec,
        }

    def list_cases(self) -> list[dict[str, Any]]:
        return self.store.list_cases()

    def start(self, case_id: str, session_id: str | None = None,
              points_enabled: bool = True) -> GameSession:
        pack = self.store.load(case_id)
        session_id = session_id or f"s_{uuid.uuid4().hex[:12]}"
        runtime = make_runtime(session_id, pack, self.index_path, use_llm=self.use_llm)
        session = GameSession(session_id, runtime, self.graph)
        # 초기 State를 checkpoint에 심는다(액션 없이 update_state만 수행).
        self.graph.update_state(
            session.config,
            new_state(pack.case_id, pack.simulation_date, points_enabled=points_enabled),
        )
        self._sessions[session_id] = session
        self._touch(session_id)
        self._evict()
        return session

    def reset(self, session_id: str) -> GameSession:
        """시연용 Reset — 같은 case를 새 세션으로 다시 시작한다."""
        old = self.get(session_id)
        case_id = old.pack.case_id
        points_enabled = bool(old.state().get("points_enabled", True))
        self.end(session_id)
        return self.start(case_id, points_enabled=points_enabled)

    def get(self, session_id: str) -> GameSession:
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"세션 없음: {session_id}")
        self._touch(session_id)
        return self._sessions[session_id]

    def end(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._last_seen.pop(session_id, None)
        drop_runtime(session_id)
        try:
            self.graph.checkpointer.delete_thread(session_id)   # checkpoint도 함께 회수
        except Exception:  # noqa: BLE001 — 체크포인터 구현에 따라 없을 수 있다
            pass


def mermaid() -> str:
    """문서/발표용 Mermaid 소스."""
    return """flowchart TD
    U([User]) --> GM["LangGraph Game Master<br/>entry_node: 행동 검증 + 포인트 차감"]
    GM -->|error| E([END])
    GM --> R{{"Action Router<br/>(deterministic, no LLM)"}}
    R -->|open_document| OD["open_document_node<br/>문서 열람 · Evidence 수집"]
    R -->|research| RS["research_node"]
    R -->|hint| HT["hint_node"]
    R -->|term| TM["term_node (Glossary)"]
    R -->|decision| DC["decision_node<br/>Decision Evaluator"]
    R -->|replay| RP["replay_node<br/>Future Event Unlock"]
    RS --> EA["Evidence Agent"]
    EA --> PIT["Point-in-Time Retriever<br/>document_date &lt;= simulation_date"]
    PIT --> IDX[("search_index.jsonl<br/>past + future chunks")]
    EA --> VD["Evidence Validator<br/>SUPPORTED / PARTIALLY / UNSUPPORTED"]
    HT --> TA["Tutor Agent<br/>Level 1/2/3"]
    DC -.->|decision 확정| RP
    OD --> E
    RS --> E
    HT --> E
    TM --> E
    DC --> E
    RP --> E
"""
