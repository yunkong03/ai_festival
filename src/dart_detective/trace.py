"""Trace 기록기 — 데모/발표에서 "무엇이 왜 그렇게 나왔는지"를 보여주는 장치.

한 턴마다 최소 다음을 남긴다:
    현재 State 스냅샷 / 사용자 Action / 호출된 Node / Retriever Query /
    검색된 문서 / 적용된 날짜 필터 / Agent 출력 / Evidence Validation 결과 / Latency
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceSpan:
    name: str
    started_at: float
    payload: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0

    def finish(self, **payload: Any) -> dict[str, Any]:
        self.latency_ms = int((time.perf_counter() - self.started_at) * 1000)
        self.payload.update(payload)
        return {"span": self.name, "latency_ms": self.latency_ms, **self.payload}


class TraceRecorder:
    """세션 하나의 trace를 모은다. LangGraph State에도 요약본을 넣는다."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.records: list[dict[str, Any]] = []

    def span(self, name: str, **payload: Any) -> TraceSpan:
        return TraceSpan(name=name, started_at=time.perf_counter(), payload=dict(payload))

    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        entry = {
            "trace_id": uuid.uuid4().hex[:12],
            "session_id": self.session_id,
            "ts": time.time(),
            **entry,
        }
        self.records.append(entry)
        return entry

    def turn(
        self,
        *,
        action: str,
        node: str,
        state_before: dict[str, Any],
        state_after: dict[str, Any],
        retriever_query: str | None = None,
        retrieved: list[dict[str, Any]] | None = None,
        date_filter: dict[str, Any] | None = None,
        agent_output: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        llm: dict[str, Any] | None = None,
        latency_ms: int = 0,
        error: str | None = None,
    ) -> dict[str, Any]:
        return self.record({
            "action": action,
            "node": node,
            "state_before": state_before,
            "state_after": state_after,
            "retriever_query": retriever_query,
            "retrieved": retrieved or [],
            "date_filter": date_filter,
            "agent_output": agent_output,
            "validation": validation,
            "llm": llm,
            "latency_ms": latency_ms,
            "error": error,
        })

    def dump(self) -> list[dict[str, Any]]:
        return list(self.records)
