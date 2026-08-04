"""공통 tokenizer — 모든 chunking 전략(Fixed Token, 이후 Section-aware/Table Row 등)이
동일한 token counting 규칙을 쓰도록 이 모듈 하나로 모은다. tiktoken의 cl100k_base(OpenAI
계열 임베딩에서 512/64 같은 chunk 크기 관례의 기준이 되는 BPE)를 쓴다.

encode/decode가 완전히 lossless(어떤 token id 리스트든 decode(encode(text)) == text이고,
서로 다른 두 조각을 encode해서 이어붙인 뒤 decode해도 각 조각을 decode한 걸 이어붙인
것과 같다)라는 성질을 sliding-window chunking에서 그대로 이용한다 — encoding을 한 번씩만
하고, window 슬라이싱은 순수하게 정수 리스트 위에서 하면 된다.
"""
from __future__ import annotations

import tiktoken

_ENCODING_NAME = "cl100k_base"
_encoding = None


def _get_encoding():
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding(_ENCODING_NAME)
    return _encoding


def encode(text: str) -> list[int]:
    # disallowed_special=() — DART 원문에 우연히 "<|endoftext|>" 같은 tiktoken 특수토큰
    # 문자열이 섞여 있어도(발생 가능성은 낮지만 실제 코퍼스 전수 실행에서 예외로 죽으면
    # 안 됨) 그냥 일반 텍스트로 취급한다.
    return _get_encoding().encode(text, disallowed_special=())


def decode(token_ids: list[int]) -> str:
    return _get_encoding().decode(token_ids)


def count_tokens(text: str) -> int:
    return len(encode(text))
