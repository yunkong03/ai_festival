#!/usr/bin/env python3
"""DocumentIR -> Case Pack용 평문 렌더러.

Case Pack의 `original_text`는 여기서 만든다. 규칙:
  - 노드 등장 순서를 그대로 보존한다(DocumentIR nodes는 이미 원문 순서).
  - section  -> "## {title_text}"
  - paragraph-> text 그대로
  - table    -> 행마다 " | "로 join. 같은 행에서 연속 중복된 셀 텍스트는 1회만 남긴다
               (DART 표는 rowspan 확장 때문에 같은 값이 2~4회 반복된다).
  - 결과는 줄 리스트이며 original_text = "\n".join(lines).
    display_excerpt / evidence.source_text는 항상 이 줄들의 연속 부분집합이라
    문자열 부분집합 검사(grounding)가 항상 성립한다.
"""
from __future__ import annotations

import re


def _cell_text(c) -> str:
    if isinstance(c, dict):
        return (c.get("text") or "").strip()
    return str(c).strip()


def _dedup_row(cells: list[str]) -> list[str]:
    out: list[str] = []
    for c in cells:
        if out and out[-1] == c:
            continue
        out.append(c)
    return out


def render_table(node: dict) -> list[str]:
    lines = []
    for row in node.get("normalized_rows") or []:
        cells = _dedup_row([_cell_text(c) for c in row])
        line = " | ".join(cells).strip()
        if line and line.strip(" |"):
            lines.append(line)
    return lines


def render_nodes(nodes: list[dict]) -> list[str]:
    lines: list[str] = []
    for n in nodes:
        kind = n.get("kind")
        if kind == "section":
            t = (n.get("title_text") or "").strip()
            if t:
                lines.append(f"## {t}")
        elif kind == "paragraph":
            t = (n.get("text") or "").strip()
            if t:
                lines.append(t)
        elif kind == "table":
            lines.extend(render_table(n))
    return lines


def select_nodes(doc: dict, section_keywords: list[str] | None = None,
                 max_nodes: int | None = None) -> list[dict]:
    """정기보고서처럼 큰 문서는 관련 섹션만 남긴다.

    section_keywords가 주어지면, 노드의 section_hierarchy(또는 section 자신의 title_text)에
    키워드가 하나라도 포함된 노드만 남긴다. 노드 순서는 그대로 유지된다.
    """
    nodes = doc.get("nodes") or []
    if section_keywords:
        kept = []
        for n in nodes:
            hay = " / ".join(n.get("section_hierarchy") or [])
            if n.get("kind") == "section":
                hay = hay + " / " + (n.get("title_text") or "")
            if any(k in hay for k in section_keywords):
                kept.append(n)
        nodes = kept
    if max_nodes is not None:
        nodes = nodes[:max_nodes]
    return nodes


def render_document(doc: dict, section_keywords: list[str] | None = None,
                    max_nodes: int | None = None,
                    max_chars: int | None = None) -> tuple[str, list[str]]:
    lines = render_nodes(select_nodes(doc, section_keywords, max_nodes))
    if max_chars is not None:
        acc, total = [], 0
        for ln in lines:
            if total + len(ln) + 1 > max_chars:
                break
            acc.append(ln)
            total += len(ln) + 1
        lines = acc
    return "\n".join(lines), lines


def find_line(lines: list[str], patterns: list[str], start: int = 0) -> int:
    """patterns의 모든 문자열을 포함하는 첫 줄의 인덱스. 못 찾으면 -1."""
    for i in range(start, len(lines)):
        ln = lines[i]
        if all(p in ln for p in patterns):
            return i
    return -1


def find_block(lines: list[str], patterns: list[str], span: int = 1) -> str:
    """patterns가 맞는 줄부터 span줄을 이어 붙인 연속 블록(=original_text의 부분 문자열)."""
    i = find_line(lines, patterns)
    if i < 0:
        raise KeyError(f"패턴 {patterns}에 맞는 줄을 찾지 못했다")
    return "\n".join(lines[i:i + span])


NUM_RE = re.compile(r"\d[\d,]*")


def won_to_eok(text: str) -> str:
    """'473,200,000,000' -> '4,732억원' (표기 검증용 보조. Case Pack에는 원문 숫자를 쓴다)."""
    m = NUM_RE.search(text)
    if not m:
        return ""
    v = int(m.group().replace(",", ""))
    return f"{v // 100_000_000:,}억원"
