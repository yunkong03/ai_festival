"""Evidence Agent — 자유 질문을 받아 실제 공시에서 근거를 찾아 답한다.

규칙:
  - 검색은 반드시 PointInTimeRetriever를 통해서만 한다(미래 문서 차단은 그쪽 책임).
  - 원문에 없는 숫자를 만들지 않는다. 만들면 Validator가 UNSUPPORTED로 잡고,
    이 모듈은 LLM 답변을 버리고 결정론적 발췌 답변으로 되돌린다.
  - 근거가 부족하면 부족하다고 답한다.

출력 형태:
    {"answer": "", "evidence": [{"document_id": "", "quote_or_fact": ""}], "uncertainty": ""}
"""
from __future__ import annotations

from typing import Any

from ..llm import LLMResult, LLMUnavailable
from ..retriever import PointInTimeRetriever, RetrievedDoc, tokenize
from . import validator

# 질문 → 조사 관점 확장. LLM이 없을 때도 "이 회사가 이 투자를 감당할 수 있어?" 같은
# 질문이 현금/자기자본/부채/영업이익으로 퍼지도록 하는 결정론적 사전.
ASPECT_KEYWORDS: dict[str, list[str]] = {
    "감당 여력": ["현금및현금성자산", "자기자본", "자본총계", "부채총계", "영업이익", "매출액"],
    "투자 규모": ["투자금액", "자기자본대비", "투자기간", "종료일", "대규모법인여부"],
    "시장 수요": ["매출", "수주", "계약금액", "매출처", "생산능력", "수주잔고"],
    "위험": ["가격", "급락", "변동", "위험", "매출처", "신용", "등급", "미상환"],
    "자금조달": ["회사채", "전환사채", "채무증권", "발행", "자기주식", "이자율"],
}

_ASPECT_TRIGGERS: list[tuple[tuple[str, ...], str]] = [
    (("감당", "여력", "가능", "버틸", "재무", "돈", "자금여력"), "감당 여력"),
    (("규모", "얼마", "투자금액", "크기", "비중"), "투자 규모"),
    (("수요", "시장", "팔", "매출", "수주", "고객"), "시장 수요"),
    (("위험", "리스크", "문제", "불안", "우려"), "위험"),
    (("조달", "빌", "자금", "차입", "증자", "사채"), "자금조달"),
]

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "quote_or_fact": {"type": "string"},
                },
                "required": ["document_id", "quote_or_fact"],
                "additionalProperties": False,
            },
        },
        "uncertainty": {"type": "string"},
    },
    "required": ["answer", "evidence", "uncertainty"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """너는 금융 탐정게임의 Evidence Agent다. 플레이어의 질문에 대해
아래에 주어진 공시 발췌만 근거로 답한다.

절대 규칙:
- 발췌에 없는 숫자를 쓰지 마라. 숫자는 발췌에 적힌 그대로 옮겨라.
- evidence[].quote_or_fact는 발췌 원문을 **글자 그대로** 복사한 한 줄이어야 한다.
- 발췌만으로 답할 수 없으면 answer에 그렇게 적고, uncertainty에 무엇이 더 필요한지 써라.
- 결론(충분하다/부족하다 같은 판단)을 내리지 마라. 사실과 비교 가능한 숫자만 제시하고
  판단은 플레이어에게 남겨라.
- 주어진 발췌 밖의 지식(회사에 대해 네가 아는 사실, 미래에 일어난 일)을 쓰지 마라."""


def pick_aspects(question: str) -> list[str]:
    q = question.lower()
    hits = [name for triggers, name in _ASPECT_TRIGGERS if any(t in q for t in triggers)]
    return hits or ["감당 여력", "투자 규모"]


def build_queries(question: str) -> list[str]:
    queries = [question]
    for aspect in pick_aspects(question):
        queries.extend(ASPECT_KEYWORDS[aspect])
    return queries


def gather(retriever: PointInTimeRetriever, question: str, k_per_query: int = 3,
           max_docs: int = 6) -> tuple[list[RetrievedDoc], list[str]]:
    """여러 관점 쿼리를 돌려 중복 없는 상위 발췌를 모은다."""
    queries = build_queries(question)
    seen: dict[str, RetrievedDoc] = {}
    for q in queries:
        for r in retriever.search(q, k=k_per_query):
            prev = seen.get(r.chunk_id)
            if prev is None or r.score > prev.score:
                seen[r.chunk_id] = r
    ranked = sorted(seen.values(), key=lambda r: (-r.score, r.chunk_id))
    return ranked[:max_docs], queries


def _informative_lines(docs: list[RetrievedDoc], question: str, limit: int = 5
                       ) -> list[tuple[RetrievedDoc, str]]:
    """질문 토큰과 겹치는 원문 줄을 골라낸다(발췌 답변의 재료)."""
    qt = set(tokenize(question)) | {t for q in build_queries(question) for t in tokenize(q)}
    scored: list[tuple[float, RetrievedDoc, str]] = []
    for d in docs:
        for line in d.text.split("\n"):
            line = line.strip()
            if len(line) < 6:
                continue
            lt = tokenize(line)
            if not lt:
                continue
            overlap = sum(1 for t in lt if t in qt) / len(lt)
            if overlap <= 0:
                continue
            scored.append((overlap * d.score, d, line))
    scored.sort(key=lambda x: -x[0])
    out: list[tuple[RetrievedDoc, str]] = []
    seen_lines: set[str] = set()
    per_chunk: dict[str, int] = {}
    # 한 청크에서 두 줄까지만 뽑는다 — 같은 표의 인접 행으로 답변이 채워지는 것을 막는다.
    for _, d, line in scored:
        if line in seen_lines or per_chunk.get(d.chunk_id, 0) >= 2:
            continue
        seen_lines.add(line)
        per_chunk[d.chunk_id] = per_chunk.get(d.chunk_id, 0) + 1
        out.append((d, line))
        if len(out) >= limit:
            break
    return out


def fallback_answer(docs: list[RetrievedDoc], question: str) -> dict[str, Any]:
    """LLM 없이 만드는 답변. 원문 줄만 인용하므로 항상 grounded다."""
    picked = _informative_lines(docs, question)
    if not picked:
        return {
            "answer": "조사 시점까지 공개된 공시에서 이 질문에 답할 근거를 찾지 못했다.",
            "evidence": [],
            "uncertainty": "검색어를 바꾸거나 다른 문서를 열어 다시 조사해야 한다.",
        }
    lines = "\n".join(f"- {line}" for _, line in picked)
    return {
        "answer": "조사 시점까지 공개된 공시에서 확인되는 문장은 다음과 같다.\n" + lines,
        "evidence": [
            {"document_id": d.document_id, "quote_or_fact": line} for d, line in picked
        ],
        "uncertainty": "위 문장은 원문 발췌 그대로다. 해석과 결론은 플레이어가 내려야 한다.",
    }


def _llm_answer(llm: Any, question: str, docs: list[RetrievedDoc], simulation_date: str
                ) -> tuple[dict[str, Any], dict[str, Any]]:
    excerpts = "\n\n".join(
        f"[{d.document_id}] {d.title} ({d.document_date})\n{d.text}" for d in docs
    )
    user = (
        f"오늘은 {simulation_date}이다. 이 날짜 이후의 정보는 존재하지 않는다.\n\n"
        f"플레이어 질문: {question}\n\n"
        f"=== 공시 발췌 ===\n{excerpts}\n=== 발췌 끝 ==="
    )
    result: LLMResult = llm.complete_json(SYSTEM_PROMPT, user, ANSWER_SCHEMA)
    meta = {
        "provider": result.provider,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "usage": result.usage,
    }
    return result.data, meta


def answer_question(
    question: str,
    retriever: PointInTimeRetriever,
    *,
    llm: Any | None = None,
    simulation_date: str = "",
) -> dict[str, Any]:
    docs, queries = gather(retriever, question)
    sources = [d.to_dict() for d in docs]

    llm_meta: dict[str, Any] = {"used": False}
    payload = fallback_answer(docs, question)
    degraded_from: dict[str, Any] | None = None

    if llm is not None and docs:
        try:
            llm_payload, meta = _llm_answer(llm, question, docs, simulation_date)
            llm_meta = {"used": True, **meta}
            llm_validation = validator.validate(
                llm_payload.get("answer", ""),
                llm_payload.get("evidence", []),
                sources,
            )
            if llm_validation["status"] == "UNSUPPORTED":
                # 근거 없는 수치/인용이면 LLM 답변을 버리고 발췌 답변으로 되돌린다.
                degraded_from = {"answer": llm_payload.get("answer", ""),
                                 "validation": llm_validation}
                llm_meta["degraded"] = True
            else:
                payload = llm_payload
        except (LLMUnavailable, Exception) as exc:  # noqa: BLE001 — 어떤 실패든 fallback
            llm_meta = {"used": False, "error": f"{type(exc).__name__}: {exc}"}

    validation = validator.validate(
        payload.get("answer", ""), payload.get("evidence", []), sources
    )

    return {
        "answer": payload.get("answer", ""),
        "evidence": payload.get("evidence", []),
        "uncertainty": payload.get("uncertainty", ""),
        "retrieved": sources,
        "queries": queries,
        "validation": validation,
        "llm": llm_meta,
        "degraded_from": degraded_from,
    }


def match_case_evidence(case_evidence: list[dict[str, Any]], docs: list[dict[str, Any]]
                        ) -> list[str]:
    """검색 결과에 Case Pack evidence의 source_text가 통째로 들어 있으면 수집 처리."""
    blob = "\n".join(d["text"] for d in docs)
    found = []
    for ev in case_evidence:
        if ev["source_text"] in blob:
            found.append(ev["evidence_id"])
    return found
