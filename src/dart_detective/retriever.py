"""Point-in-Time Retriever — 이 백엔드에서 가장 중요한 부품.

원칙:
  모든 검색은 `document_date <= simulation_date`를 통과해야 한다.
  Prompt에 "미래를 보지 마라"라고 적는 것으로 끝내지 않는다. 후보 풀을 만드는
  Query 계층에서 잘라내고, 점수화가 끝난 뒤에 한 번 더 assertion을 건다.
  미래 문서가 하나라도 살아남으면 FutureLeakageError를 던지고 trace에 남긴다.

인덱스에는 **미래 문서도 함께 들어 있다**. 그래야 날짜 필터가 실제로 일하는지
테스트로 증명할 수 있다(필터를 끄면 미래 문서가 상위에 잡힌다).
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .errors import FutureLeakageError

_WORD_RE = re.compile(r"[A-Za-z]+|[0-9][0-9,\.]*")
_HANGUL_RE = re.compile(r"[가-힣]+")


def tokenize(text: str) -> list[str]:
    """한국어 형태소 분석기 없이 쓰는 경량 토크나이저.

    - 영문/숫자는 단어 단위
    - 한글은 음절 bigram(+ 1음절 어절은 그대로) — 조사 변화에 견디는 값싼 방법
    """
    text = text.lower()
    tokens: list[str] = [m.group() for m in _WORD_RE.finditer(text)]
    for m in _HANGUL_RE.finditer(text):
        w = m.group()
        if len(w) == 1:
            tokens.append(w)
            continue
        tokens.extend(w[i:i + 2] for i in range(len(w) - 1))
    return tokens


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    case_id: str
    doc_id: str                 # DocumentIR doc_id (원본 추적용)
    document_id: str | None     # Case Pack 문서 ID (D01 …). 미래 문서는 None
    document_date: str          # YYYY-MM-DD
    title: str
    source_type: str
    text: str


@dataclass
class RetrievedDoc:
    document_id: str
    document_date: str
    title: str
    text: str
    score: float
    doc_id: str = ""
    chunk_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BM25:
    """의존성 없는 최소 BM25. 데모 규모(수백 chunk)에서는 이걸로 충분하다."""

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = corpus_tokens
        self.n = len(corpus_tokens)
        self.doc_len = [len(t) for t in corpus_tokens]
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        self.tf: list[Counter] = [Counter(t) for t in corpus_tokens]
        df: Counter = Counter()
        for t in corpus_tokens:
            df.update(set(t))
        self.idf = {
            term: math.log(1 + (self.n - c + 0.5) / (c + 0.5))
            for term, c in df.items()
        }

    def score(self, query_tokens: Iterable[str], index: int) -> float:
        tf = self.tf[index]
        dl = self.doc_len[index] or 1
        total = 0.0
        for term in query_tokens:
            f = tf.get(term)
            if not f:
                continue
            idf = self.idf.get(term, 0.0)
            total += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return total


@dataclass
class PointInTimeRetriever:
    """simulation_date 이전 문서만 반환하는 Retriever.

    `enforce_date_filter=False`는 **테스트 전용**이다 — 필터를 끄면 미래 문서가
    잡힌다는 것을 보여 필터가 실제로 일하고 있음을 증명하는 용도로만 쓴다.
    운영 경로에서는 절대 False로 부르지 않는다.
    """

    chunks: list[Chunk]
    simulation_date: str
    _bm25: BM25 = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._bm25 = BM25([tokenize(c.text) for c in self.chunks])

    # ---------- 인덱스 로딩 ----------
    @classmethod
    def from_index_file(cls, path: Path | str, case_id: str, simulation_date: str
                        ) -> "PointInTimeRetriever":
        chunks = [c for c in load_index(path) if c.case_id == case_id]
        if not chunks:
            raise ValueError(f"{case_id}에 해당하는 chunk가 인덱스에 없다: {path}")
        return cls(chunks=chunks, simulation_date=simulation_date)

    # ---------- 검색 ----------
    def candidate_indices(self, enforce_date_filter: bool = True) -> list[int]:
        """후보 풀 자체를 날짜로 자른다 — 점수화 전에 미래 문서를 제거한다."""
        if not enforce_date_filter:
            return list(range(len(self.chunks)))
        return [i for i, c in enumerate(self.chunks) if c.document_date <= self.simulation_date]

    def search(self, query: str, k: int = 5, *, enforce_date_filter: bool = True,
               min_score: float = 0.0) -> list[RetrievedDoc]:
        qt = tokenize(query)
        scored: list[tuple[float, int]] = []
        for i in self.candidate_indices(enforce_date_filter):
            s = self._bm25.score(qt, i)
            if s > min_score:
                scored.append((s, i))
        scored.sort(key=lambda x: (-x[0], self.chunks[x[1]].chunk_id))
        results = [
            RetrievedDoc(
                document_id=self.chunks[i].document_id or self.chunks[i].doc_id,
                document_date=self.chunks[i].document_date,
                title=self.chunks[i].title,
                text=self.chunks[i].text,
                score=round(s, 4),
                doc_id=self.chunks[i].doc_id,
                chunk_id=self.chunks[i].chunk_id,
            )
            for s, i in scored[:k]
        ]
        if enforce_date_filter:
            self.assert_no_future(results)
        return results

    # ---------- 사후 검증 ----------
    def assert_no_future(self, results: list[RetrievedDoc]) -> None:
        """검색 이후 한 번 더 날짜 assertion. 필터가 뚫렸다면 여기서 반드시 죽는다."""
        offending = [r.to_dict() for r in results if r.document_date > self.simulation_date]
        if offending:
            raise FutureLeakageError(
                f"검색 결과에 simulation_date({self.simulation_date}) 이후 문서 "
                f"{len(offending)}건이 포함됨",
                offending=offending,
            )

    # ---------- 진단용 ----------
    def stats(self) -> dict[str, int]:
        past = sum(1 for c in self.chunks if c.document_date <= self.simulation_date)
        return {
            "n_chunks": len(self.chunks),
            "n_past_chunks": past,
            "n_future_chunks": len(self.chunks) - past,
        }


def load_index(path: Path | str) -> list[Chunk]:
    out: list[Chunk] = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(Chunk(
                chunk_id=d["chunk_id"],
                case_id=d["case_id"],
                doc_id=d["doc_id"],
                document_id=d.get("document_id"),
                document_date=d["document_date"],
                title=d["title"],
                source_type=d["source_type"],
                text=d["text"],
            ))
    return out
