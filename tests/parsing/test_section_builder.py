from dart_corpus.parsing.document_ir import SectionIR, SourceLocation
from dart_corpus.parsing.section_builder import ROOT_SECTION_ID, SectionStackBuilder, classify_title_level


def test_classify_roman_numeral():
    assert classify_title_level("I. 회사의 개요") == (1, True)


def test_classify_bracket():
    assert classify_title_level("【 대표이사 등의 확인 】") == (1, True)


def test_classify_simple_number():
    assert classify_title_level("1. 회사의 개요") == (2, True)


def test_classify_dashed_number():
    assert classify_title_level("2-1. 연결 재무상태표") == (3, True)


def test_classify_unnumbered_returns_not_confident():
    level, confident = classify_title_level("채무증권 발행실적")
    assert confident is False


def _sec(idx: int, title: str) -> SectionIR:
    node_id = f"doc::rel::n{idx}"
    return SectionIR(node_id=node_id, title_text=title, source=SourceLocation("rel", idx), section_id=node_id)


def test_stack_builds_real_periodic_hierarchy():
    """실측 재현(아모레퍼시픽 periodic_20240516000601, dart4): I. -> 1. -> 2. -> 2-1.
    -> 2-2. -> 3. 순서로 TITLE이 등장했을 때 부모/레벨이 실제 문서 구조와 일치해야 한다."""
    builder = SectionStackBuilder()
    titles = [
        "III. 재무에 관한 사항", "1. 요약재무정보", "2. 연결재무제표",
        "2-1. 연결 재무상태표", "2-2. 연결 포괄손익계산서", "3. 연결재무제표 주석",
        "3-1 일반사항 (연결)",
    ]
    sections = [_sec(i, t) for i, t in enumerate(titles)]
    for i, s in enumerate(sections):
        builder.push(s, order_index=i * 10)
    builder.close_all(final_order_index=1000)

    by_title = {s.title_text: s for s in sections}
    assert by_title["III. 재무에 관한 사항"].level == 1
    assert by_title["III. 재무에 관한 사항"].parent_section_id == ROOT_SECTION_ID
    assert by_title["1. 요약재무정보"].level == 2
    assert by_title["1. 요약재무정보"].parent_section_id == by_title["III. 재무에 관한 사항"].section_id
    assert by_title["2. 연결재무제표"].level == 2
    # "1."과 "2."는 형제 — "2."가 들어오면 "1."은 닫히고 부모는 여전히 "III."여야 한다
    assert by_title["2. 연결재무제표"].parent_section_id == by_title["III. 재무에 관한 사항"].section_id
    assert by_title["1. 요약재무정보"].end_order_index == 19  # "2."가 order_index=20에 들어오기 직전
    assert by_title["2-1. 연결 재무상태표"].level == 3
    assert by_title["2-1. 연결 재무상태표"].parent_section_id == by_title["2. 연결재무제표"].section_id
    assert by_title["2-2. 연결 포괄손익계산서"].parent_section_id == by_title["2. 연결재무제표"].section_id
    # "3."이 들어오면 "2."와 그 자식("2-2.")이 모두 닫혀야 한다
    assert by_title["2. 연결재무제표"].end_order_index == 49
    assert by_title["3. 연결재무제표 주석"].parent_section_id == by_title["III. 재무에 관한 사항"].section_id
    assert by_title["3-1 일반사항 (연결)"].parent_section_id == by_title["3. 연결재무제표 주석"].section_id
    # 문서 끝까지 열려 있던 섹션들도 close_all 후엔 전부 end_order_index가 채워져 있어야 한다
    assert all(s.end_order_index is not None for s in sections)


def test_unnumbered_title_gets_child_level_and_hierarchy_flag():
    """실측 재현(TABLE-GROUP 내장 캡션, 예: "채무증권 발행실적") — 번호 패턴이 없으면
    현재 열린 섹션의 자식(level+1)으로 취급하고 level_confident=False로 표시해야 한다
    (호출자가 이를 보고 UNKNOWN_SECTION_DEPTH 경고를 남긴다). 부모의 형제로 취급하면
    while-pop 조건 때문에 부모 자신이 닫혀버리는 버그가 있었다(이 테스트로 발견)."""
    builder = SectionStackBuilder()
    parent = _sec(0, "7. 기타 참고사항")
    builder.push(parent, order_index=0)
    caption = _sec(1, "채무증권 발행실적")
    builder.push(caption, order_index=10)
    assert caption.level_confident is False
    assert caption.parent_section_id == parent.section_id
    assert caption.level == parent.level + 1
    assert parent.end_order_index is None  # 아직 안 닫혔어야 함(자식이 들어왔다고 부모가 닫히면 버그)


def test_repeated_identical_title_text_creates_separate_sections():
    """동일 TITLE 문자열이 두 번 등장해도(예: 서로 다른 재무제표 그룹에서 "일반사항"이
    반복) 병합되지 않고 각각 독립된 section_id/end_order_index를 가져야 한다."""
    builder = SectionStackBuilder()
    parent1 = _sec(0, "3. 연결재무제표 주석")
    builder.push(parent1, order_index=0)
    child1 = _sec(1, "일반사항")
    builder.push(child1, order_index=10)
    parent2 = _sec(2, "5. 재무제표 주석")
    builder.push(parent2, order_index=100)
    child2 = _sec(3, "일반사항")
    builder.push(child2, order_index=110)
    builder.close_all(final_order_index=1000)

    assert child1.section_id != child2.section_id
    assert child1.parent_section_id == parent1.section_id
    assert child2.parent_section_id == parent2.section_id
    assert child1.end_order_index == 99  # parent2가 들어오면서 child1도 같이 닫힘
    assert child1.title_text == child2.title_text == "일반사항"
