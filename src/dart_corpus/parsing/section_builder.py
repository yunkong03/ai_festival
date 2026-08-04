"""Section Builder — TITLE 기반 section stack. dart3/dart4 공통(스키마 분기 없음).

실측 근거(periodic_20240516000601 dart4, periodic_20231114001884 dart3 — 두 스키마
모두 동일 패턴 확인):
  - 최상위 TITLE에는 ATOC 속성(Y/N)이 있다. ATOC="N"은 "목 차"(목차 그 자체) 1건뿐이며
    실제 section이 아니다.
  - 번호 패턴이 실제 계층을 그대로 반영한다: "Ⅰ."/"I." 로마숫자 또는 "【...】" 대괄호 =
    level 1, "N." 단일 숫자 = level 2, "N-M" 형태(예: "2-1.") = level 3.
  - TABLE-GROUP은 직계 자식으로 TITLE을 가질 수 있다(예: TABLE-GROUP[TITLE="2-1. 연결
    재무상태표", TABLE, TABLE]). 이 TITLE의 ATOC="Y"면 진짜 section(예: "2-1.", "3-1"
    ~ "3-25" 전부 확인됨) — 부모 섹션("2. 연결재무제표", "3. 연결재무제표 주석")의
    numbering과 그대로 이어진다. ATOC="N"이면 순수 표 캡션이다(예: "채무증권 발행실적",
    "최대주주 변동내역" 등 8건 확인 — 번호가 없고 목차에도 없음).
  - 기존 traversal은 TABLE-GROUP을 만나면 하위로 재귀하지 않아서, 이 내장 TITLE들이
    통째로 누락되고 있었다(partial 원인 분석에서 실측 발견 — SectionIR 개수가 원문
    TITLE 태그 수보다 적은 55/93건이 전부 이 케이스).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ROMAN_OR_BRACKET_RE = re.compile(r"^\s*(?:[IVXLCDM]+\.|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.?|【)")
_DASHED_NUMBER_RE = re.compile(r"^\s*\d+-\d+")
_SIMPLE_NUMBER_RE = re.compile(r"^\s*\d+[.\s]")


def classify_title_level(title_text: str) -> tuple[int, bool]:
    """번호 패턴만으로 레벨 추정(실측: 로마숫자/대괄호=1, 단일숫자=2, N-M=3).
    반환: (level, confident). confident=False면 패턴을 못 찾은 것 — 호출자가
    스택 깊이로 fallback하고 UNKNOWN_SECTION_DEPTH 경고를 남겨야 한다."""
    text = title_text.strip()
    if _DASHED_NUMBER_RE.match(text):
        return 3, True
    if _ROMAN_OR_BRACKET_RE.match(text):
        return 1, True
    if _SIMPLE_NUMBER_RE.match(text):
        return 2, True
    return 0, False


ROOT_SECTION_ID = "ROOT"


@dataclass
class _OpenSection:
    section_ir: object   # SectionIR — 순환 import 피하려고 object로 둠(canonical_parser에서 실제 타입으로 채움)
    level: int


class SectionStackBuilder:
    """TITLE을 순서대로 받아 section stack을 관리한다. ROOT는 가상(노드로 만들지 않음) —
    최상위 섹션의 parent_section_id는 항상 ROOT_SECTION_ID 문자열이다."""

    def __init__(self):
        self._stack: list[_OpenSection] = []

    def current_hierarchy_titles(self) -> list[str]:
        return [s.section_ir.title_text for s in self._stack]

    def push(self, section_ir, order_index: int) -> None:
        level, confident = classify_title_level(section_ir.title_text)
        if not confident:
            # 번호 없는 TITLE(예: 표 캡션이 section으로 승격된 경우) — 현재 열려 있는
            # 섹션의 자식으로 취급한다(현재 섹션의 level+1). 형제로 취급하면(<= 부모
            # level) while-pop 조건에 걸려 부모 자신이 닫혀버리는 버그가 있었다(실측
            # 테스트로 발견 — test_unnumbered_title_gets_sibling_level_and_hierarchy_flag).
            level = (self._stack[-1].level + 1) if self._stack else 1
        section_ir.level = level
        section_ir.level_confident = confident
        section_ir.start_order_index = order_index

        while self._stack and self._stack[-1].level >= level:
            self._close(self._stack.pop(), order_index)

        # 부모는 반드시 pop이 끝난 뒤(자기보다 얕은 레벨만 남은 상태)의 스택 top이어야 한다.
        section_ir.parent_section_id = self._stack[-1].section_ir.section_id if self._stack else ROOT_SECTION_ID
        section_ir.section_hierarchy = self.current_hierarchy_titles()

        self._stack.append(_OpenSection(section_ir=section_ir, level=level))

    def _close(self, open_section: _OpenSection, order_index: int) -> None:
        open_section.section_ir.end_order_index = order_index - 1

    def close_all(self, final_order_index: int) -> None:
        while self._stack:
            self._close(self._stack.pop(), final_order_index)
