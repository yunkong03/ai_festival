"""Table Serializer — raw cell 목록(rowspan/colspan 보존)을 받아 정규화 rows/헤더/
shape 진단을 만든다. dart3/dart4·KIND HTML 공통(태그 종류 무관, TableCellIR만 소비).

실측 근거(periodic_20240516000601 "2-1. 연결 재무상태표" TABLE-GROUP):
  - 같은 TABLE-GROUP 안에 TABLE이 2개 있을 수 있다(제목/기간 표시용 1행짜리 표 +
    실제 헤더/데이터 표). 헤더 행은 TH 태그가 다수인 행으로 식별 가능(실측: 컬럼헤더
    행("　"/"제 19 기 1분기말"/"제 18 기말")은 전부 TH, 데이터 행은 전부 TE).
  - merged cell(rowspan/colspan>1)이 사실상 표마다 있다시피 함(파일럿 240건에서
    13,631회) — "무시"가 아니라 실제로 rectangular grid로 펼쳐야 다운스트림(Chunking/
    Facts)이 쓸 수 있다.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from dart_corpus.parsing.document_ir import ParserWarning, TableCellIR, WarningCode

_UNIT_RE = re.compile(r"\(\s*단위\s*[:：]\s*([^)]+)\)")
_PERIOD_RE = re.compile(r"제\s*\d+\s*기[^,\)\]\s]*")


def group_into_raw_rows(cells: list[TableCellIR]) -> list[list[TableCellIR]]:
    """row 인덱스 기준으로 묶는다(순서 보존). row 번호에 구멍이 있어도(빈 행) 유지."""
    if not cells:
        return []
    max_row = max(c.row for c in cells)
    rows: list[list[TableCellIR]] = [[] for _ in range(max_row + 1)]
    for c in cells:
        rows[c.row].append(c)
    for row in rows:
        row.sort(key=lambda c: c.col)
    return rows


def expand_normalized_rows(raw_rows: list[list[TableCellIR]]) -> list[list[str]]:
    """rowspan/colspan을 반영해 직사각형 grid로 확장한다(HTML rowspan/colspan 표준
    확장 알고리즘 — occupancy grid에 각 셀 text를 덮는 모든 칸에 채워 넣는다)."""
    if not raw_rows:
        return []
    n_rows = len(raw_rows)
    # 먼저 필요한 최대 컬럼 수를 추정(원본 col 인덱스 + colspan 고려)
    max_col = 0
    for row in raw_rows:
        for c in row:
            max_col = max(max_col, c.col + c.colspan)
    grid: list[list[str | None]] = [[None] * max_col for _ in range(n_rows)]

    for row_idx, row in enumerate(raw_rows):
        col_cursor = 0
        for c in row:
            # 이미 이전 행의 rowspan에 의해 점유된 칸은 건너뛴다
            while col_cursor < max_col and grid[row_idx][col_cursor] is not None:
                col_cursor += 1
            for dr in range(c.rowspan):
                for dc in range(c.colspan):
                    r, cc = row_idx + dr, col_cursor + dc
                    if r < n_rows and cc < max_col:
                        grid[r][cc] = c.text
            col_cursor += c.colspan

    return [[cell if cell is not None else "" for cell in row] for row in grid]


def detect_header_row_indices(raw_rows: list[list[TableCellIR]]) -> list[int]:
    """TH 태그가 그 행 셀의 과반이면 header row로 본다(다중 header 행 지원 —
    실측: 컬럼 헤더 행이 TH 다수인 패턴을 그대로 이용, 추정 아님)."""
    header_rows = []
    for idx, row in enumerate(raw_rows):
        if not row:
            continue
        th_count = sum(1 for c in row if c.tag.upper() in ("TH",))
        if th_count > len(row) / 2:
            header_rows.append(idx)
    return header_rows


def compute_shape_diagnostics(raw_rows: list[list[TableCellIR]]) -> tuple[int | None, list[int]]:
    """row별 실제 컬럼 수(colspan 반영)와 최빈 컬럼 수(=선언된 컬럼 수 대체 지표)."""
    actual_col_counts = [sum(c.colspan for c in row) for row in raw_rows]
    if not actual_col_counts:
        return None, []
    n_declared_cols = Counter(actual_col_counts).most_common(1)[0][0]
    return n_declared_cols, actual_col_counts


def shape_mismatch_warning(doc_id: str, rel_path: str, node_id: str, actual_col_counts: list[int],
                            n_declared_cols: int | None) -> ParserWarning | None:
    if n_declared_cols is None:
        return None
    mismatched = [i for i, n in enumerate(actual_col_counts) if n != n_declared_cols]
    if not mismatched:
        return None
    return ParserWarning(
        doc_id, rel_path, WarningCode.TABLE_SHAPE_MISMATCH, "info",
        f"table {node_id}: {len(mismatched)}/{len(actual_col_counts)} rows have column count "
        f"!= mode({n_declared_cols}) — rows {mismatched[:5]}{'...' if len(mismatched) > 5 else ''}",
    )


@dataclass
class TableMetadata:
    title: str | None
    title_confirmed: bool
    unit_text: str | None
    period_text: str | None


def infer_consolidation_basis(section_hierarchy: list[str]) -> tuple[str | None, str | None]:
    """section_hierarchy(루트→직계부모 순, 표 자신 제외)에서 "연결"/"별도" 표시를
    찾는다. 표에 가장 가까운(리스트 끝) 제목부터 역순으로 훑어 첫 매치를 채택한다 —
    더 구체적인(가까운) 계층이 상위(조부모) 계층보다 신뢰도가 높다는 가정. 한 제목
    안에 "연결"과 "별도"가 동시에 있으면(예: "연결 및 별도 재무제표 비교") 판정이
    모호하므로 None + ambiguous 사유를 남긴다. 아무 표시도 못 찾으면 None, 사유 없음
    (불확실 그 자체가 정보이므로 억지 추론하지 않는다)."""
    for title in reversed(section_hierarchy):
        has_consolidated = "연결" in title
        has_separate = "별도" in title
        if has_consolidated and has_separate:
            return None, f"ambiguous: title={title!r} contains both 연결 and 별도"
        if has_consolidated:
            return "연결", f"matched '연결' in section_hierarchy title={title!r}"
        if has_separate:
            return "별도", f"matched '별도' in section_hierarchy title={title!r}"
    return None, None


def extract_table_metadata(embedded_title_text: str | None) -> TableMetadata:
    """title은 TABLE-GROUP에 같이 있는 TITLE에서만 채운다(확인된 값 — 추정 아님).
    unit/period는 그 title 문자열 안에서 명확한 패턴이 매치될 때만 채우고, 그 외에는
    None(호출자가 TABLE_METADATA_UNCERTAIN 경고를 남긴다)."""
    if embedded_title_text is None:
        return TableMetadata(title=None, title_confirmed=False, unit_text=None, period_text=None)
    text = embedded_title_text.strip()
    unit_m = _UNIT_RE.search(text)
    period_m = _PERIOD_RE.search(text)
    return TableMetadata(
        title=text, title_confirmed=True,
        unit_text=unit_m.group(1).strip() if unit_m else None,
        period_text=period_m.group(0).strip() if period_m else None,
    )
