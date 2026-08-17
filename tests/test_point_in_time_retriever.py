"""Point-in-Time Retriever — 날짜 차단이 실제로 일하는지 검증.

인덱스에는 미래 문서가 들어 있다. 필터를 끄면 미래 문서가 잡히고, 켜면 안 잡힌다.
"둘 다 안 잡히는" 인덱스로 통과하는 가짜 테스트가 되지 않도록 먼저 미래 문서가
검색 가능하다는 것부터 확인한다.
"""
from __future__ import annotations

import pytest

from dart_detective.errors import FutureLeakageError
from dart_detective.retriever import Chunk, PointInTimeRetriever

SIM = "2023-05-23"

PAST = Chunk(
    chunk_id="c-past", case_id="T", doc_id="exchange_1", document_id="D01",
    document_date="2023-05-23", title="신규시설투자등", source_type="exchange",
    text="2. 투자내역 | 투자금액(원) | 473,200,000,000\n4. 투자기간 | 종료일 | 2024-12-31",
)
FUTURE = Chunk(
    chunk_id="c-future", case_id="T", doc_id="exchange_2", document_id=None,
    document_date="2024-10-22", title="[FUTURE] [기재정정]신규시설투자등",
    source_type="exchange",
    text="3. 정정사유 | 전방시장 수요 변동성 확대에 따른 증설속도 조정\n"
         "4. 투자기간 | 종료일 | 2026-12-31",
)


@pytest.fixture
def retriever() -> PointInTimeRetriever:
    return PointInTimeRetriever(chunks=[PAST, FUTURE], simulation_date=SIM)


def test_future_chunk_is_actually_searchable_without_filter(retriever):
    """전제 확인: 필터를 끄면 미래 문서가 잡힌다(안 잡히면 아래 테스트가 무의미)."""
    hits = retriever.search("증설속도 조정 정정사유", k=5, enforce_date_filter=False)
    assert any(h.document_date > SIM for h in hits)


def test_filter_removes_future_documents(retriever):
    hits = retriever.search("증설속도 조정 정정사유", k=5)
    assert all(h.document_date <= SIM for h in hits)
    assert not any(h.chunk_id == "c-future" for h in hits)


def test_filter_keeps_past_documents_that_match(retriever):
    """필터가 '전부 버리는' 것이 아니라 미래만 버린다는 것도 확인한다."""
    hits = retriever.search("투자기간 종료일", k=5)
    assert hits and all(h.document_date <= SIM for h in hits)
    assert any(h.chunk_id == "c-past" for h in hits)


def test_candidate_pool_is_cut_before_scoring(retriever):
    """점수화 이전 단계(후보 풀)에서 잘린다 — 사후 필터가 아니다."""
    assert len(retriever.candidate_indices(enforce_date_filter=True)) == 1
    assert len(retriever.candidate_indices(enforce_date_filter=False)) == 2


def test_assert_no_future_raises_with_trace_payload(retriever):
    leaked = retriever.search("증설속도 조정", k=5, enforce_date_filter=False)
    with pytest.raises(FutureLeakageError) as exc:
        retriever.assert_no_future(leaked)
    assert exc.value.offending
    assert all(o["document_date"] > SIM for o in exc.value.offending)


def test_stats_report_past_and_future_counts(retriever):
    assert retriever.stats() == {"n_chunks": 2, "n_past_chunks": 1, "n_future_chunks": 1}


def test_results_carry_required_fields(retriever):
    hit = retriever.search("투자금액", k=1)[0]
    d = hit.to_dict()
    for key in ("document_id", "document_date", "title", "text", "score"):
        assert key in d
