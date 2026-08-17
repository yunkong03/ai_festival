"""동시 접속 대비 — 세션이 늘어도 자원이 선형으로 늘지 않아야 한다.

공개 링크를 여러 명이 동시에 누르는 상황(발표/심사)을 가정한다.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dart_detective.graph import DEFAULT_INDEX_PATH, GameServer
from dart_detective.nodes import get_retriever

requires_index = pytest.mark.skipif(
    not Path(DEFAULT_INDEX_PATH).exists(),
    reason="search_index.jsonl 없음 — scripts/build_case_search_index.py 실행 필요",
)


@requires_index
def test_retriever_is_shared_across_sessions_of_same_case():
    """세션마다 인덱스를 다시 읽으면 동시 접속에서 메모리·지연이 배로 는다."""
    server = GameServer(use_llm=False)
    a = server.start("CASE-001")
    b = server.start("CASE-001")
    try:
        assert a.runtime.retriever is b.runtime.retriever
    finally:
        server.end(a.session_id)
        server.end(b.session_id)


@requires_index
def test_different_cases_get_different_retrievers():
    """공유하더라도 사건이 다르면 simulation_date가 달라 반드시 분리돼야 한다."""
    server = GameServer(use_llm=False)
    a = server.start("CASE-001")
    b = server.start("CASE-002")
    try:
        assert a.runtime.retriever is not b.runtime.retriever
        assert a.runtime.retriever.simulation_date != b.runtime.retriever.simulation_date
    finally:
        server.end(a.session_id)
        server.end(b.session_id)


@requires_index
def test_sessions_do_not_leak_state_into_each_other():
    """한 사람의 단서 수집이 다른 사람 화면에 나타나면 안 된다."""
    server = GameServer(use_llm=False)
    a = server.start("CASE-001")
    b = server.start("CASE-001")
    try:
        a.act("open_document", document_id="D01", collect=["E01"])
        assert a.state()["found_evidence"] == ["E01"]
        assert b.state()["found_evidence"] == []
        assert b.state()["opened_documents"] == []
    finally:
        server.end(a.session_id)
        server.end(b.session_id)


@requires_index
def test_shared_retriever_still_enforces_point_in_time():
    """공유 캐시를 쓰더라도 날짜 차단은 그대로여야 한다."""
    r = get_retriever(DEFAULT_INDEX_PATH, "CASE-001", "2023-05-23")
    hits = r.search("정정 신규시설투자", k=5)
    assert hits
    assert all(h.document_date <= "2023-05-23" for h in hits)


@requires_index
def test_many_concurrent_sessions_stay_within_cap():
    """상한을 넘겨도 서버가 죽지 않고 오래된 세션부터 회수한다."""
    server = GameServer(use_llm=False, max_sessions=10)
    sessions = [server.start("CASE-001") for _ in range(25)]
    try:
        assert server.stats()["active_sessions"] == 10
        # 가장 최근 세션은 살아 있어야 한다
        assert sessions[-1].state()["case_id"] == "CASE-001"
    finally:
        for s in sessions:
            server.end(s.session_id)
