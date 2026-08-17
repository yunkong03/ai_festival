#!/usr/bin/env python3
"""데모 Case Pack 정의 - 사람이 쓰는 유일한 파일.

여기에는 '어떤 공시의 어떤 줄을 쓸 것인가'와 해설(교육 목적 문장)만 적는다.
숫자와 원문은 build_case_packs.py가 DocumentIR에서 직접 뽑아 채운다.

match 규칙: 렌더된 줄 리스트에서 patterns의 모든 문자열을 포함하는 첫 줄을 찾고,
그 줄부터 span줄을 이어붙여 source_text로 쓴다. 항상 original_text의 연속 부분 문자열이다.

evidence[].text에 쓰는 숫자는 반드시 source_text에 있는 숫자여야 한다
(원 단위 금액의 억원 환산만 예외 - validate_case_pack.py가 검사한다).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# CASE-001 에코프로비엠 - CAM9 신증설 투자 (2023-05-23)
# ---------------------------------------------------------------------------
CASE_001 = {
    "case_id": "CASE-001",
    "case_title": "4,732억원 증설 결정 — 2차전지 양극재 CAM9",
    "simulation_date": "2023-05-23",
    "difficulty": "normal",
    "mission": (
        "2023년 5월 23일. 에코프로비엠 이사회가 자기자본의 31.8%에 해당하는 신규 증설 투자를 "
        "결의했다. 이 시점까지 공개된 공시만 조사해서, 이 투자가 회사의 체력으로 감당 가능한 "
        "규모인지 판단하라."
    ),
    "intro": (
        "전기차 배터리 수요가 폭발하던 시기다. 에코프로비엠은 하이니켈 양극재를 만들어 "
        "삼성SDI·SK온 같은 셀 제조사에 판다. 회사는 포항 제4캠퍼스에 연 54,000톤 규모의 "
        "CAM9 라인을 새로 짓겠다고 발표했다. 발표문에는 투자금액과 자기자본 대비 비율이 "
        "적혀 있다. 그런데 같은 시점 분기보고서에는 다른 이야기도 함께 적혀 있다. "
        "당신은 2023년 5월 23일의 투자자다. 미래 주가는 모른다. 공시만 본다."
    ),
    "documents": [
        {
            "document_id": "D01",
            "doc_id": "exchange_20230523900365",
            "title": "신규시설투자등 (2023-05-23 이사회 결의)",
            "role": "trigger",
            "excerpt": {"match": ["1. 투자구분"], "span": 8},
        },
        {
            "document_id": "D02",
            "doc_id": "periodic_20230515001464",
            "title": "분기보고서 (2023.03) — III. 재무에 관한 사항 / 1. 요약재무정보",
            "role": "financials",
            "sections": ["1. 요약재무정보"],
            "max_chars": 20000,
            "excerpt": {"match": ["[유동자산]"], "span": 6},
        },
        {
            "document_id": "D03",
            "doc_id": "periodic_20230515001464",
            "title": "분기보고서 (2023.03) — II. 사업의 내용",
            "role": "business",
            "sections": ["1. 사업의 개요", "3. 원재료 및 생산설비", "4. 매출 및 수주상황"],
            "max_chars": 40000,
            "excerpt": {"match": ["## 1. 사업의 개요"], "span": 3},
        },
        {
            "document_id": "D04",
            "doc_id": "periodic_20230515001464",
            "title": "분기보고서 (2023.03) — III-7. 증권의 발행을 통한 자금조달",
            "role": "risk",
            "sections": ["증권의 발행을 통한 자금조달"],
            "max_chars": 20000,
            "excerpt": {"match": ["1) 채무증권 발행실적"], "span": 5},
        },
        {
            "document_id": "D05",
            "doc_id": "major_20230425000692",
            "title": "주요사항보고서(자기주식처분결정) (2023-04-25)",
            "role": "context",
            "excerpt": {"match": ["## 자기주식 처분 결정"], "span": 6},
        },
    ],
    "evidence": [
        {
            "evidence_id": "E01", "document_id": "D01", "match": ["투자금액(원)"],
            "text": "이번 신규시설투자의 투자금액은 473,200,000,000원(약 4,732억원)이다.",
            "category": "investment", "importance": "critical",
            "educational_reason": "투자 규모를 회사 체력과 비교하는 모든 판단의 출발점이다.",
        },
        {
            "evidence_id": "E02", "document_id": "D01", "match": ["자기자본(원)"], "span": 3,
            "text": "자기자본은 1,488,215,127,423원이고 투자금액은 자기자본의 31.8%에 해당하며, "
                    "대규모법인여부는 '해당'이다.",
            "category": "finance", "importance": "critical",
            "educational_reason": "자기자본 대비 31.8%는 한 건의 설비투자로는 매우 큰 비중이다. "
                                  "이 비율이 커질수록 실패했을 때 회사가 받는 타격도 커진다.",
        },
        {
            "evidence_id": "E03", "document_id": "D01", "match": ["4. 투자기간 | 종료일"],
            "text": "투자 종료 예정일은 2024-12-31이다.",
            "category": "timeline", "importance": "critical",
            "educational_reason": "약 1년 7개월 만에 4,732억원을 집행하겠다는 뜻이다. "
                                  "기간이 짧을수록 연간 자금 부담이 커진다.",
        },
        {
            "evidence_id": "E04", "document_id": "D01", "match": ["8. 기타 투자판단에 참고할 사항"],
            "text": "국내 CAM9 신증설 투자로 투자규모는 54,000톤/년, 투자지역은 경북 포항시 "
                    "제4캠퍼스 내이며, 회사는 투자금액·투자기간·자금조달 계획이 집행 과정에서 "
                    "일부 변경될 수 있다고 밝혔다.",
            "category": "investment", "importance": "optional",
            "educational_reason": "공시 본문이 스스로 '변경될 수 있다'고 적어둔 부분이다. "
                                  "공시의 숫자는 확정이 아니라 현재 계획이라는 신호다.",
        },
        {
            "evidence_id": "E05", "document_id": "D02",
            "match": ["구분 | (2023년 3월말)"], "span": 3,
            "text": "2023년 3월말 연결 기준 현금및현금성자산은 239,036,839,774원(약 2,390억원)이다.",
            "category": "finance", "importance": "critical",
            "educational_reason": "보유 현금이 투자금액 4,732억원의 절반에 못 미친다. "
                                  "즉 이 투자는 외부 자금조달 없이는 완주할 수 없다.",
        },
        {
            "evidence_id": "E06", "document_id": "D02", "match": ["부채총계", "2,581,553,023,711"],
            "text": "연결 부채총계는 2,581,553,023,711원이다.",
            "category": "finance", "importance": "critical",
            "educational_reason": "자본총계와 함께 보면 부채비율이 나온다. 이미 부채가 자본보다 큰 "
                                  "상태에서 대규모 투자를 더 얹는 상황인지 확인해야 한다.",
        },
        {
            "evidence_id": "E07", "document_id": "D02", "match": ["자본총계", "1,560,432,172,300"],
            "text": "연결 자본총계는 1,560,432,172,300원이다.",
            "category": "finance", "importance": "critical",
            "educational_reason": "부채총계와 나눠 보면 부채비율이 약 165%다. "
                                  "공시의 '자기자본'이 어느 숫자에서 왔는지도 여기서 확인된다.",
        },
        {
            "evidence_id": "E08", "document_id": "D02",
            "match": ["(2023년 1월1일~2023년 3월31일)"], "span": 3,
            "text": "2023년 1월1일~2023년 3월31일 매출액은 2,010,989,897,316원, "
                    "영업이익은 107,327,003,425원이다.",
            "category": "finance", "importance": "optional",
            "educational_reason": "분기 영업이익 약 1,073억원이다. 이 속도로 벌어서 4,732억원을 "
                                  "메우려면 얼마가 걸리는지 계산해 보면 투자 부담이 체감된다.",
        },
        {
            "evidence_id": "E09", "document_id": "D03", "match": ["68% 가까이 급락"],
            "text": "중국산 탄산리튬 가격이 2022년 11월 최고치 톤당 581,500위안에서 2023년 4월 "
                    "최저치 톤당 188,500위안으로 68% 가까이 급락했다.",
            "category": "risk", "importance": "critical",
            "educational_reason": "양극재 판가는 원재료 시세에 연동된다. 리튬 가격 급락은 "
                                  "매출 단가 하락으로 이어질 수 있다 — 증설이 곧 이익이 아니라는 신호다.",
        },
        {
            "evidence_id": "E10", "document_id": "D03", "match": ["98.1%"],
            "text": "주요 매출처는 삼성SDI, SK온, TMM 등 이차전지 셀 제조업체이며 이들에 대한 "
                    "매출비중은 98.1%다.",
            "category": "risk", "importance": "critical",
            "educational_reason": "매출의 거의 전부가 소수 고객에게서 나온다. 고객사 한 곳의 "
                                  "생산계획이 바뀌면 증설한 라인이 놀 수 있다.",
        },
        {
            "evidence_id": "E11", "document_id": "D03", "match": ["(단위 : 톤/월)"], "span": 3,
            "text": "양극활물질(NCA, NCM) 생산능력은 2020년 말 약 5,000톤에서 2022년 말 약 "
                    "15,000톤으로 늘었다(단위: 톤/월).",
            "category": "business", "importance": "optional",
            "educational_reason": "이미 2년 만에 생산능력을 3배로 키운 뒤 또 증설하는 국면이다. "
                                  "증설 속도가 수요 증가 속도를 앞지르는지 봐야 한다.",
        },
        {
            "evidence_id": "E12", "document_id": "D03", "match": ["연산 18만톤"],
            "text": "회사는 2023년 1분기말 기준 연산 18만톤의 양극활물질 생산능력을 확보했다고 "
                    "밝혔다.",
            "category": "business", "importance": "optional",
            "educational_reason": "기존 18만톤에 CAM9의 54,000톤을 더하는 결정이라는 뜻이다. "
                                  "증설 비중을 가늠할 기준값이다.",
        },
        {
            "evidence_id": "E13", "document_id": "D04", "match": ["BBB+"],
            "text": "미상환 회사채 권면총액은 50,000백만원, 이자율 2.95%, 신용평가등급은 BBB+, "
                    "만기일은 2023년 07월 19일이다.",
            "category": "risk", "importance": "optional",
            "educational_reason": "BBB+는 투자적격 등급 중 낮은 편이다. 등급이 낮을수록 "
                                  "증설 자금을 빌릴 때 이자를 더 물어야 한다.",
        },
        {
            "evidence_id": "E14", "document_id": "D04",
            "match": ["미상환 전환사채 및 신주인수권부사채"],
            "text": "작성 기준일 현재 미상환 전환사채·신주인수권부사채 등 향후 자본금을 증가시킬 "
                    "수 있는 사채의 발행은 없다.",
            "category": "finance", "importance": "optional",
            "educational_reason": "지금은 주식으로 바뀔 사채가 없다는 뜻이다. 앞으로 회사가 "
                                  "어떤 방식으로 돈을 조달하는지 비교할 기준선이 된다.",
        },
        {
            "evidence_id": "E15", "document_id": "D05",
            "match": ["배당가능이익범위 내 취득(주)", "146,339"],
            "text": "처분 전 자기주식 보유는 보통주 146,339주로 발행주식의 0.15%다.",
            "category": "finance", "importance": "optional",
            "educational_reason": "자기주식을 팔아 투자재원을 마련하는 회사도 있지만, "
                                  "0.15%로는 4,732억원 조달에 거의 도움이 되지 않는다.",
        },
    ],
    "finance_terms": [
        {
            "term": "자기자본",
            "short_definition": "회사 자산에서 빚을 뺀, 주주 몫의 돈. 재무상태표의 자본총계다.",
            "why_it_matters_here": "이번 공시의 '자기자본 1,488,215,127,423원'은 2022년 말 연결 "
                                   "자본총계다. 투자금액을 이 값으로 나눈 31.8%가 곧 투자 부담의 크기다.",
            "source_evidence_ids": ["E02", "E07"],
        },
        {
            "term": "자기자본대비 비율 / 대규모법인",
            "short_definition": "투자금액이 자기자본의 몇 %인지. 이 비율이 일정 기준을 넘으면 "
                                "거래소에 의무적으로 공시해야 한다.",
            "why_it_matters_here": "31.8%·'대규모법인 해당'이기 때문에 이 투자는 회사가 자율적으로 "
                                   "알린 게 아니라 알릴 의무가 있어서 공개된 정보다.",
            "source_evidence_ids": ["E01", "E02"],
        },
        {
            "term": "영업이익",
            "short_definition": "본업에서 번 이익. 매출액에서 원가와 판매관리비를 뺀 값이다.",
            "why_it_matters_here": "분기 영업이익 약 1,073억원과 투자금액 4,732억원을 비교하면 "
                                   "'몇 분기치 이익을 한 번에 쓰는 결정인가'가 바로 보인다.",
            "source_evidence_ids": ["E08"],
        },
        {
            "term": "부채비율",
            "short_definition": "부채총계 ÷ 자본총계. 남의 돈을 자기 돈의 몇 배 쓰고 있는지를 나타낸다.",
            "why_it_matters_here": "부채 2,581,553,023,711원 ÷ 자본 1,560,432,172,300원 ≈ 165%다. "
                                   "이미 빚이 자기 돈보다 많은 상태에서 증설을 더하는 국면이다.",
            "source_evidence_ids": ["E06", "E07"],
        },
        {
            "term": "신용등급",
            "short_definition": "신용평가사가 매기는 '빚 갚을 능력' 등급. BBB+는 투자적격 등급 중 낮은 축이다.",
            "why_it_matters_here": "증설 자금을 빚으로 조달해야 하는데 등급이 BBB+라면 조달 금리가 "
                                   "높아진다. 투자 결정과 자금조달 조건은 붙어 있는 문제다.",
            "source_evidence_ids": ["E13"],
        },
    ],
    "decision_options": [
        {
            "option_id": "O1", "label": "예정대로 진행",
            "description": "2024년 말까지 4,732억원을 계획대로 집행한다.",
            "supporting_evidence_ids": ["E08", "E11", "E12"],
            "counter_evidence_ids": ["E05", "E06", "E09"],
            "feedback_if_missing_critical": "현금 보유액(E05)과 리튬 가격 급락(E09)을 보지 않고 "
                                            "진행을 택했다면, 자금조달 부담과 판가 하락 위험을 "
                                            "빼놓고 판단한 것이다.",
        },
        {
            "option_id": "O2", "label": "규모 축소",
            "description": "54,000톤/년 계획을 줄여 투자금액을 낮춘다.",
            "supporting_evidence_ids": ["E05", "E06", "E09", "E10"],
            "counter_evidence_ids": ["E12"],
            "feedback_if_missing_critical": "축소를 택했다면 근거가 된 재무 압박(E05·E06)과 "
                                            "수요 신호(E09·E10)를 실제로 확인했는지 돌아보라.",
        },
        {
            "option_id": "O3", "label": "일정 연기",
            "description": "규모는 유지하되 완공 시점을 뒤로 미뤄 연간 자금 부담을 낮춘다.",
            "supporting_evidence_ids": ["E03", "E05", "E09"],
            "counter_evidence_ids": ["E10", "E12"],
            "feedback_if_missing_critical": "연기를 택했다면 종료일(E03)과 현금(E05)의 관계를 "
                                            "확인했는지 점검하라.",
        },
        {
            "option_id": "O4", "label": "추가 조사 후 결정",
            "description": "고객사 장기공급계약과 자금조달 계획이 확인될 때까지 판단을 유보한다.",
            "supporting_evidence_ids": ["E10", "E13", "E14"],
            "counter_evidence_ids": ["E04"],
            "feedback_if_missing_critical": "유보를 택했다면 '무엇을 더 알아야 하는지'가 "
                                            "구체적이어야 한다. E10(고객 집중)과 E14(자금조달 수단)이 "
                                            "그 출발점이다.",
        },
    ],
    "future_events": [
        {
            "doc_id": "major_20230630000403",
            "event": "제5회 전환사채(CB) 4,400억원 발행 결정. 표면이자율 0.0% / 만기이자율 2.0%, "
                     "만기 2028-07-24, 사모 발행. 조달 목적은 운영자금 1,400억원 + "
                     "타법인 증권 취득자금 3,000억원.",
            "match": ["2. 사채의 권면(전자등록)총액 (원)"], "span": 16,
        },
        {
            "doc_id": "exchange_20231201900749",
            "event": "삼성SDI와 하이니켈계 NCA 양극소재 중장기 공급계약 체결. "
                     "계약기간 2024-01-01~2028-12-31, 계약금액 총액 43,867,615,524,480원.",
            "match": ["43,867,615,524,480"], "span": 1,
        },
        {
            "doc_id": "exchange_20241022900223",
            "event": "신규시설투자 정정공시. 정정사유는 '전방시장 수요 변동성 확대에 따른 "
                     "증설속도 조정'으로, 투자 종료일을 2024-12-31에서 2026-12-31로 2년 미뤘다. "
                     "투자금액 473,200,000,000원은 그대로 유지했다.",
            "match": ["3. 정정사유"], "span": 1,
            "changed_fields": [
                {"field": "4. 투자기간 (종료일)", "before": "2024-12-31", "after": "2026-12-31"},
            ],
        },
        {
            "doc_id": "major_20241028000368",
            "event": "채권형 신종자본증권(자본으로 인정되는 채무증권) 2,440억원 발행 결정. "
                     "표면이자율 6.281%, 만기 2054-10-29(30년), 조달 목적은 "
                     "채무상환자금 2,200억원 + 운영자금 240억원.",
            "match": ["2. 사채의 권면(전자등록)총액 (원)"], "span": 12,
        },
    ],
}

# ---------------------------------------------------------------------------
# CASE-002 LS ELECTRIC - 초고압 변압기 시설증설 (2024-05-21)
# ---------------------------------------------------------------------------
CASE_002 = {
    "case_id": "CASE-002",
    "case_title": "803억원 증설 결정 — 초고압 변압기 자작 Capa",
    "simulation_date": "2024-05-21",
    "difficulty": "easy",
    "mission": (
        "2024년 5월 21일. LS ELECTRIC이 초고압 변압기 생산설비 증설을 결정했다. "
        "이 시점까지 공개된 공시만 조사해서, 이 증설이 '수요를 따라가는 투자'인지 "
        "'수요를 앞서가는 투자'인지 판단하라."
    ),
    "intro": (
        "미국 전력망 교체와 데이터센터 증설로 전 세계에서 변압기가 부족하던 시기다. "
        "LS ELECTRIC은 803억원을 들여 초고압 변압기를 직접 만드는 설비를 늘리겠다고 "
        "자율공시했다. 자기자본 대비 4.7% — 앞선 CASE-001과 비교하면 훨씬 작은 비중이다. "
        "작은 투자라고 안전한 걸까? 수주잔고와 해외법인 매출을 보고 판단하라."
    ),
    "documents": [
        {
            "document_id": "D01",
            "doc_id": "exchange_20240521800037",
            "title": "신규시설투자등(자율공시) (2024-05-21 내부 결정)",
            "role": "trigger",
            "excerpt": {"match": ["1. 투자구분"], "span": 9},
        },
        {
            "document_id": "D02",
            "doc_id": "periodic_20240514001662",
            "title": "분기보고서 (2024.03) — III. 재무에 관한 사항 / 1. 요약재무정보",
            "role": "financials",
            "sections": ["1. 요약재무정보"],
            "max_chars": 20000,
            "excerpt": {"match": ["[유동자산]"], "span": 6},
        },
        {
            "document_id": "D03",
            "doc_id": "periodic_20240313001659",
            "title": "사업보고서 (2023.12) — II. 사업의 내용 / 4. 매출 및 수주상황",
            "role": "business",
            "sections": ["4. 매출 및 수주상황"],
            "max_chars": 40000,
            "excerpt": {"match": ["다. 수주 상황"], "span": 9},
        },
        {
            "document_id": "D04",
            "doc_id": "exchange_20240103800430",
            "title": "단일판매·공급계약체결 — 영국 Widow Hill BESS PJT (2024-01-03)",
            "role": "context",
            "excerpt": {"match": ["- 체결계약명"], "span": 5},
        },
        {
            "document_id": "D05",
            "doc_id": "exchange_20240109800112",
            "title": "단일판매·공급계약체결 — 미국 BESS Power Supply System (2024-01-09)",
            "role": "context",
            "excerpt": {"match": ["- 체결계약명"], "span": 5},
        },
    ],
    "evidence": [
        {
            "evidence_id": "E01", "document_id": "D01", "match": ["투자금액(원)"],
            "text": "투자금액은 80,300,000,000원(약 803억원)이다.",
            "category": "investment", "importance": "critical",
            "educational_reason": "투자 규모를 회사 체력과 비교하는 출발점이다.",
        },
        {
            "evidence_id": "E02", "document_id": "D01", "match": ["자기자본(원)"], "span": 3,
            "text": "자기자본은 1,724,042,303,163원이고 투자금액은 자기자본의 4.7%이며 "
                    "대규모법인여부는 '해당'이다.",
            "category": "finance", "importance": "critical",
            "educational_reason": "자기자본 대비 4.7%는 실패해도 회사가 흔들릴 규모가 아니다. "
                                  "같은 '신규시설투자' 공시라도 비중에 따라 위험이 전혀 다르다.",
        },
        {
            "evidence_id": "E03", "document_id": "D01", "match": ["3. 투자목적"],
            "text": "투자목적은 '수주 증가 물량 대응을 위한 초고압 변압기 자작 Capa 확보'다.",
            "category": "investment", "importance": "critical",
            "educational_reason": "회사 스스로 '수주가 이미 늘어서' 짓는다고 적었다. "
                                  "이 주장이 수주잔고 숫자로 뒷받침되는지 확인해야 한다.",
        },
        {
            "evidence_id": "E04", "document_id": "D01", "match": ["4. 투자기간 | 시작일"], "span": 2,
            "text": "투자기간은 2024-06-01 시작, 2025-09-30 종료 예정이다.",
            "category": "timeline", "importance": "optional",
            "educational_reason": "약 16개월짜리 증설이다. 변압기 부족이 그때까지 이어질지가 관건이다.",
        },
        {
            "evidence_id": "E05", "document_id": "D02", "match": ["| 2024년 3월말 |"], "span": 3,
            "text": "2024년 3월말 연결 현금및현금성자산은 659,580백만원이다(단위: 백만원).",
            "category": "finance", "importance": "critical",
            "educational_reason": "보유 현금이 투자금액 803억원의 8배가 넘는다. "
                                  "외부에서 돈을 빌리지 않고도 집행할 수 있다는 뜻이다.",
        },
        {
            "evidence_id": "E06", "document_id": "D02", "match": ["| 2024년 1월~3월 |"], "span": 3,
            "text": "매출은 2024년 1월~3월 1,038,639백만원, 2023년 1월~12월 4,230,483백만원, "
                    "2022년 1월~12월 3,377,070백만원이고, 영업이익은 각각 93,738 / 324,878 / "
                    "187,524백만원이다.",
            "category": "finance", "importance": "critical",
            "educational_reason": "영업이익이 1년 만에 187,524에서 324,878백만원으로 뛰었다. "
                                  "투자 여력이 실적에서 나오고 있는지 확인하는 근거다.",
        },
        {
            "evidence_id": "E07", "document_id": "D02", "match": ["자본총계 | 1,708,125"],
            "text": "연결 자본총계는 최근 분기말 1,708,125백만원, 직전 사업연도말 "
                    "1,724,042백만원이다.",
            "category": "finance", "importance": "optional",
            "educational_reason": "공시의 '자기자본 1,724,042,303,163원'이 2023년 12월말 "
                                  "연결 자본총계에서 왔다는 것을 여기서 대조 확인할 수 있다.",
        },
        {
            "evidence_id": "E08", "document_id": "D02", "match": ["부채총계 | 2,186,742"],
            "text": "연결 부채총계는 2,186,742백만원이다.",
            "category": "finance", "importance": "optional",
            "educational_reason": "자본총계 1,708,125백만원과 비교하면 부채비율은 약 128%다. "
                                  "증설 여력을 볼 때 함께 봐야 하는 숫자다.",
        },
        {
            "evidence_id": "E09", "document_id": "D03", "match": ["다. 수주 상황"], "span": 9,
            "text": "LS ELECTRIC 수주 현황은 당기 수주금액 19,950억원, 기납품액 17,379억원, "
                    "기말 수주잔고 23,261억원이며 이 중 전력 T&D 수주잔고가 21,911억원이다.",
            "category": "business", "importance": "critical",
            "educational_reason": "수주잔고가 연 매출을 넘어선다는 뜻이다. 투자목적에 적힌 "
                                  "'수주 증가 물량 대응'이 실제 숫자로 뒷받침된다.",
        },
        {
            "evidence_id": "E10", "document_id": "D03",
            "match": ["LS ELECTRICAmerica", "합계"],
            "text": "미국 법인 LS ELECTRIC America 매출 합계는 오래된 사업연도부터 순서대로 "
                    "58,242 → 126,512 → 320,126백만원이다(단위: 백만원).",
            "category": "business", "importance": "critical",
            "educational_reason": "2년 만에 5배가 넘게 늘었다. 초고압 변압기 수요가 어디서 오는지를 "
                                  "보여주는 직접 증거다.",
        },
        {
            "evidence_id": "E11", "document_id": "D04", "match": ["2. 계약내역 | 계약금액(원)"],
            "span": 3,
            "text": "영국 Widow Hill BESS 공사수주 계약금액은 121,729,345,200원이며 "
                    "최근매출액 3,377,070,215,838원 대비 3.6%다.",
            "category": "business", "importance": "optional",
            "educational_reason": "증설 결정 4개월 전에 이미 대형 해외 프로젝트를 따냈다는 사실이다. "
                                  "수요가 국내에 한정되지 않는다는 근거다.",
        },
        {
            "evidence_id": "E12", "document_id": "D05", "match": ["3. 계약상대 | LS Energy Solution"],
            "span": 2,
            "text": "계약상대는 LS Energy Solution이며 회사와의 관계는 '계열회사'다.",
            "category": "risk", "importance": "optional",
            "educational_reason": "계열회사와의 거래는 외부 고객 수요와 성격이 다르다. "
                                  "수주 숫자를 볼 때 누구에게서 온 것인지 구분해야 한다.",
        },
        {
            "evidence_id": "E13", "document_id": "D05",
            "match": ["2. 계약내역 | 계약금액(원) | 86,829,106,688"], "span": 3,
            "text": "미국 BESS Power Supply System 공급계약 금액은 86,829,106,688원으로 "
                    "최근매출액 대비 2.6%다.",
            "category": "business", "importance": "optional",
            "educational_reason": "이 한 건의 계약금액이 이번 증설 투자금액 803억원과 비슷한 규모다. "
                                  "투자 대비 수주 체급을 비교해 볼 수 있다.",
        },
    ],
    "finance_terms": [
        {
            "term": "수주잔고",
            "short_definition": "이미 계약은 따냈지만 아직 납품하지 않아 앞으로 매출로 잡힐 금액.",
            "why_it_matters_here": "수주잔고 23,261억원은 앞으로 만들어야 할 물량이다. "
                                   "증설이 '희망'이 아니라 '이미 밀린 주문' 때문이라는 근거가 된다.",
            "source_evidence_ids": ["E09"],
        },
        {
            "term": "자기자본대비 비율",
            "short_definition": "투자금액이 자기자본의 몇 %인지. 투자 실패 시 회사가 받는 타격의 크기.",
            "why_it_matters_here": "4.7%다. 같은 '신규시설투자' 공시라도 이 비율이 30%를 넘는 "
                                   "회사와는 위험의 성격이 완전히 다르다.",
            "source_evidence_ids": ["E01", "E02"],
        },
        {
            "term": "영업이익",
            "short_definition": "본업에서 번 이익. 매출액에서 원가와 판매관리비를 뺀 값이다.",
            "why_it_matters_here": "2022년 187,524백만원 → 2023년 324,878백만원. "
                                   "증설 자금을 벌어들인 이익으로 감당할 수 있는지 보여준다.",
            "source_evidence_ids": ["E06"],
        },
        {
            "term": "자율공시",
            "short_definition": "법으로 반드시 알려야 하는 건 아니지만 회사가 스스로 알리는 공시.",
            "why_it_matters_here": "이 투자는 '신규시설투자등(자율공시)'로 나왔다. 회사가 먼저 "
                                   "알리고 싶어 한 정보라는 뜻이므로, 톤이 긍정적으로 기울 수 있다는 "
                                   "점을 감안하고 읽어야 한다.",
            "source_evidence_ids": ["E03"],
        },
        {
            "term": "특수관계자 거래(계열회사 거래)",
            "short_definition": "같은 그룹 안의 회사끼리 하는 거래. 외부 고객 수요와는 구분해서 봐야 한다.",
            "why_it_matters_here": "868억원 규모 계약의 상대가 계열회사 LS Energy Solution이다. "
                                   "수주가 전부 외부 시장에서 온 것은 아니라는 뜻이다.",
            "source_evidence_ids": ["E12", "E13"],
        },
    ],
    "decision_options": [
        {
            "option_id": "O1", "label": "예정대로 진행",
            "description": "803억원을 2025년 9월까지 계획대로 집행한다.",
            "supporting_evidence_ids": ["E05", "E06", "E09", "E10"],
            "counter_evidence_ids": ["E12"],
            "feedback_if_missing_critical": "수주잔고(E09)와 미국 매출(E10)을 보지 않고 진행을 "
                                            "택했다면, 근거 없이 회사 말을 믿은 것이다.",
        },
        {
            "option_id": "O2", "label": "규모 확대",
            "description": "수요가 더 강하다고 보고 투자금액을 늘린다.",
            "supporting_evidence_ids": ["E09", "E10", "E11"],
            "counter_evidence_ids": ["E12", "E08"],
            "feedback_if_missing_critical": "확대를 택했다면 수요 근거(E09·E10)뿐 아니라 "
                                            "계열사 비중(E12)도 확인했어야 한다.",
        },
        {
            "option_id": "O3", "label": "일정 연기",
            "description": "변압기 호황이 꺾일 위험을 보고 집행을 늦춘다.",
            "supporting_evidence_ids": ["E04", "E12"],
            "counter_evidence_ids": ["E09", "E10"],
            "feedback_if_missing_critical": "연기를 택했다면 수주잔고(E09)가 이미 쌓여 있다는 "
                                            "반대 근거를 어떻게 설명할지 생각해 보라.",
        },
        {
            "option_id": "O4", "label": "추가 조사 후 결정",
            "description": "수주가 계열사 물량인지 외부 수요인지 확인될 때까지 유보한다.",
            "supporting_evidence_ids": ["E12", "E13"],
            "counter_evidence_ids": ["E05", "E09"],
            "feedback_if_missing_critical": "유보를 택했다면 현금 여력(E05)이 충분해 "
                                            "'기다리는 비용'이 크다는 점도 함께 따져야 한다.",
        },
    ],
    "future_events": [
        {
            "doc_id": "major_20240523000347",
            "event": "자기주식 299,000주(635억원) 처분 결정. 처분목적은 "
                     "'투자재원 확보 및 재무구조 개선' — 증설 결정 이틀 뒤다.",
            "match": ["5. 처분목적"], "span": 1,
        },
        {
            "doc_id": "exchange_20240813800252",
            "event": "신규시설투자 정정공시. 정정사유는 '투자금액 및 투자기간 변경'으로, "
                     "투자금액을 80,300,000,000원에서 100,800,000,000원으로 205억원 늘리고 "
                     "종료일을 2025-09-30에서 2025-10-31로 한 달 미뤘다. "
                     "자기자본대비 비율은 4.7%에서 5.8%가 됐다.",
            "match": ["3. 정정사유"], "span": 1,
            "changed_fields": [
                {"field": "2. 투자금액", "before": "80,300,000,000", "after": "100,800,000,000"},
                {"field": "4. 투자기간 종료일", "before": "2025-09-30", "after": "2025-10-31"},
            ],
        },
        {
            "doc_id": "periodic_20240814001155",
            "event": "반기보고서(2024.06) 제출. 2024년 상반기 매출 2,171,076백만원, "
                     "영업이익 203,368백만원으로 전년 연간 영업이익 324,878백만원의 "
                     "60%를 반년 만에 달성했다.",
            "sections": ["1. 요약재무정보"],
            "match": ["매출 | 2,171,076"], "span": 2,
        },
    ],
}

# ---------------------------------------------------------------------------
# CASE-003 삼성바이오로직스 - 송도 5공장 신설 (2023-03-17)
# ---------------------------------------------------------------------------
CASE_003 = {
    "case_id": "CASE-003",
    "case_title": "1조 9,801억원 공장 신설 — 송도 제2바이오캠퍼스 5공장",
    "simulation_date": "2023-03-17",
    "difficulty": "hard",
    "mission": (
        "2023년 3월 17일. 삼성바이오로직스 이사회가 자기자본의 22.01%를 들여 "
        "송도에 5공장을 새로 짓기로 했다. 이 시점까지 공개된 공시만 조사해서, "
        "이 투자를 뒷받침할 만큼 수주가 실제로 늘고 있는지 판단하라."
    ),
    "intro": (
        "삼성바이오로직스는 다른 제약사의 의약품을 대신 만들어 주는 회사(CMO)다. "
        "공장을 먼저 지어야 계약을 딸 수 있고, 계약이 없으면 공장은 비어 있는 자산이 된다. "
        "회사는 180,000L 규모 5공장을 짓겠다고 발표했다. 발표 직전 몇 주 동안 "
        "위탁생산계약 공시가 여러 건 나왔는데, 금액이 늘어난 것도 있고 줄어든 것도 있다. "
        "주의: 이 사건 시점에는 코퍼스 수집 범위상 직전 사업보고서가 없다. "
        "판단은 공급계약 공시에 적힌 '최근매출액'과 '매출액대비 비율'로 해야 한다."
    ),
    "documents": [
        {
            "document_id": "D01",
            "doc_id": "exchange_20230317800146",
            "title": "신규시설투자등 — 송도 제2바이오캠퍼스 5공장 신설 (2023-03-17)",
            "role": "trigger",
            "excerpt": {"match": ["1. 투자구분"], "span": 9},
        },
        {
            "document_id": "D02",
            "doc_id": "exchange_20230302800001",
            "title": "단일판매·공급계약체결 — Pfizer 의약품 위탁생산계약 (2023-03-02)",
            "role": "business",
            "excerpt": {"match": ["- 체결계약명"], "span": 6},
        },
        {
            "document_id": "D03",
            "doc_id": "exchange_20230306800412",
            "title": "[기재정정]단일판매·공급계약체결 — Eli Lilly 계약금액 증액 (2023-03-06)",
            "role": "business",
            "excerpt": {"match": ["정정항목 | 정정전 | 정정후"], "span": 3},
        },
        {
            "document_id": "D04",
            "doc_id": "exchange_20230206800712",
            "title": "[기재정정]단일판매·공급계약체결 — GSK 계약금액 감액 (2023-02-06)",
            "role": "risk",
            "excerpt": {"match": ["정정항목 | 정정전 | 정정후"], "span": 4},
        },
    ],
    "evidence": [
        {
            "evidence_id": "E01", "document_id": "D01", "match": ["투자금액(원)"],
            "text": "투자금액은 1,980,100,000,000원(약 19,801억원)이다.",
            "category": "investment", "importance": "critical",
            "educational_reason": "단일 설비투자로는 국내 최상위권 규모다. 판단의 출발점이다.",
        },
        {
            "evidence_id": "E02", "document_id": "D01", "match": ["자기자본(원)"], "span": 3,
            "text": "자기자본은 8,995,284,255,250원이고 투자금액은 자기자본의 22.01%이며 "
                    "대규모법인여부는 '해당'이다.",
            "category": "finance", "importance": "critical",
            "educational_reason": "자기자본의 5분의 1이 넘는 금액을 공장 하나에 넣는 결정이다.",
        },
        {
            "evidence_id": "E03", "document_id": "D01", "match": ["4. 투자기간 | 시작일"], "span": 2,
            "text": "투자기간은 2023-03-17 시작, 2025-09-30 종료 예정이다.",
            "category": "timeline", "importance": "critical",
            "educational_reason": "약 2년 6개월짜리 공사다. 완공 시점에 수요가 남아 있어야 "
                                  "투자가 회수된다.",
        },
        {
            "evidence_id": "E04", "document_id": "D01", "match": ["180,000L"],
            "text": "5공장은 180,000L 규모로 건설될 예정이며, 투자기간 종료일은 향후 투자 "
                    "집행과정에서 경영환경 변화 및 내부 진행일정에 따라 변동될 수 있다.",
            "category": "investment", "importance": "optional",
            "educational_reason": "CMO는 생산능력(L)이 곧 매출 상한이다. 동시에 공시가 스스로 "
                                  "'변동될 수 있다'고 적어둔 부분이기도 하다.",
        },
        {
            "evidence_id": "E05", "document_id": "D02",
            "match": ["2. 계약내역 | 계약금액(원) | 240,993,039,040"], "span": 3,
            "text": "Pfizer와의 위탁생산계약 금액은 240,993,039,040원이고 최근매출액 "
                    "1,568,006,928,039원 대비 15.37%다.",
            "category": "business", "importance": "critical",
            "educational_reason": "한 건의 계약이 연 매출의 15%를 넘는다. 대형 고객 수주가 "
                                  "실제로 들어오고 있다는 직접 증거다.",
        },
        {
            "evidence_id": "E06", "document_id": "D02", "match": ["5. 계약기간 | 종료일 | 2029-12-31"],
            "text": "Pfizer 계약의 종료일은 2029-12-31이다.",
            "category": "timeline", "importance": "optional",
            "educational_reason": "CMO 계약은 수년에 걸쳐 매출로 나뉘어 잡힌다. 계약금액을 "
                                  "한 해 매출로 착각하면 안 된다.",
        },
        {
            "evidence_id": "E07", "document_id": "D03",
            "match": ["2. 계약내역- 계약금액(원) | 112,133,915,790"], "span": 2,
            "text": "Eli Lilly 계약금액이 112,133,915,790원에서 327,826,300,620원으로 정정됐고 "
                    "매출액대비 비율은 9.63%에서 28.14%로 올랐다.",
            "category": "business", "importance": "critical",
            "educational_reason": "고객 수요가 늘어 계약금액이 3배 가까이 커진 사례다. "
                                  "공장을 더 지어야 할 이유로 읽을 수 있다.",
        },
        {
            "evidence_id": "E08", "document_id": "D04",
            "match": ["2. 계약내역- 계약금액(원) | 270,765,248,908"], "span": 3,
            "text": "GSK 계약금액은 270,765,248,908원에서 257,732,228,908원으로 줄었고, "
                    "매출액대비 비율은 38.59%에서 36.74%로, 계약 종료일은 2023-12-31에서 "
                    "2024-12-31로 바뀌었다.",
            "category": "risk", "importance": "critical",
            "educational_reason": "같은 시기에 줄어든 계약도 있다. 증액 공시만 보고 "
                                  "'수요는 무조건 늘고 있다'고 결론 내면 안 된다는 반대 증거다.",
        },
        {
            "evidence_id": "E09", "document_id": "D04", "match": ["3. 정정사유"],
            "text": "GSK 계약 정정의 사유는 '고객사의 요청에 따른 계약금액 변경'이다.",
            "category": "risk", "importance": "optional",
            "educational_reason": "계약금액을 정하는 주체가 고객사라는 뜻이다. CMO의 매출은 "
                                  "고객 사정에 따라 위아래로 움직인다.",
        },
    ],
    "finance_terms": [
        {
            "term": "자기자본",
            "short_definition": "회사 자산에서 빚을 뺀, 주주 몫의 돈.",
            "why_it_matters_here": "8,995,284,255,250원의 22.01%를 공장 하나에 쓴다. "
                                   "회사 체력 대비 투자 크기를 재는 기준이다.",
            "source_evidence_ids": ["E02"],
        },
        {
            "term": "매출액대비 비율",
            "short_definition": "계약금액이 최근 1년 매출의 몇 %인지. 공급계약 공시의 의무 기재 항목이다.",
            "why_it_matters_here": "Pfizer 15.37%, Eli Lilly 28.14%처럼 비율로 보면 "
                                   "'이 계약이 회사에 얼마나 큰가'를 회사 규모와 무관하게 비교할 수 있다.",
            "source_evidence_ids": ["E05", "E07"],
        },
        {
            "term": "정정공시",
            "short_definition": "이미 낸 공시의 내용이 바뀌었을 때 무엇이 어떻게 바뀌었는지 다시 알리는 공시.",
            "why_it_matters_here": "이 사건의 핵심 단서 두 건(E07 증액·E08 감액)이 모두 정정공시다. "
                                   "정정공시의 '정정전/정정후' 표는 회사 계획이 어느 방향으로 "
                                   "움직였는지를 직접 보여준다.",
            "source_evidence_ids": ["E07", "E08"],
        },
        {
            "term": "위탁생산(CMO) 계약",
            "short_definition": "다른 회사의 의약품을 대신 생산해 주고 대가를 받는 계약.",
            "why_it_matters_here": "CMO는 생산능력을 먼저 지어야 계약을 딸 수 있다. "
                                   "180,000L 증설과 수주 공시를 반드시 함께 읽어야 하는 이유다.",
            "source_evidence_ids": ["E04", "E05"],
        },
        {
            "term": "대규모법인",
            "short_definition": "자기자본이 일정 규모를 넘는 상장사. 공시 의무 기준이 더 엄격하게 적용된다.",
            "why_it_matters_here": "'대규모법인여부: 해당'이라서 이 투자 결정은 회사 선택이 아니라 "
                                   "의무로 공개됐다. 즉 숨길 수 없는 정보였다.",
            "source_evidence_ids": ["E02"],
        },
    ],
    "decision_options": [
        {
            "option_id": "O1", "label": "예정대로 진행",
            "description": "1조 9,801억원을 2025년 9월까지 계획대로 집행한다.",
            "supporting_evidence_ids": ["E05", "E07"],
            "counter_evidence_ids": ["E08", "E09"],
            "feedback_if_missing_critical": "증액 공시(E07)만 보고 감액 공시(E08)를 놓쳤다면 "
                                            "한쪽 근거만으로 판단한 것이다.",
        },
        {
            "option_id": "O2", "label": "규모 축소",
            "description": "180,000L 계획을 줄여 투자금액을 낮춘다.",
            "supporting_evidence_ids": ["E02", "E08", "E09"],
            "counter_evidence_ids": ["E05", "E07"],
            "feedback_if_missing_critical": "축소를 택했다면 Pfizer·Eli Lilly 수주(E05·E07)라는 "
                                            "반대 근거를 어떻게 설명할지 정리해 보라.",
        },
        {
            "option_id": "O3", "label": "일정 앞당기기",
            "description": "수요가 강하다고 보고 완공 시점을 당겨 먼저 생산능력을 확보한다.",
            "supporting_evidence_ids": ["E05", "E07", "E04"],
            "counter_evidence_ids": ["E02", "E08"],
            "feedback_if_missing_critical": "앞당기기를 택했다면 자기자본 대비 22.01%(E02)라는 "
                                            "부담을 감수할 근거가 충분한지 따져 보라.",
        },
        {
            "option_id": "O4", "label": "추가 조사 후 결정",
            "description": "감액된 계약의 배경이 확인될 때까지 판단을 유보한다.",
            "supporting_evidence_ids": ["E08", "E09"],
            "counter_evidence_ids": ["E05", "E07"],
            "feedback_if_missing_critical": "유보를 택했다면 무엇을 더 알아야 하는지가 "
                                            "구체적이어야 한다. E09의 '고객사 요청'이 출발점이다.",
        },
    ],
    "future_events": [
        {
            "doc_id": "exchange_20230605800274",
            "event": "신규시설투자 정정공시. 정정사유는 '투자 종료일 변경'으로, "
                     "종료일을 2025-09-30에서 2025-04-01로 약 5개월 앞당겼다 — 축소가 아니라 가속이다.",
            "match": ["3. 정정사유"], "span": 1,
            "changed_fields": [
                {"field": "4. 투자기간- 종료일", "before": "2025-09-30", "after": "2025-04-01"},
            ],
        },
        {
            "doc_id": "exchange_20230704800004",
            "event": "Pfizer와 추가 의약품 위탁생산계약 체결. 계약금액 922,746,708,000원으로 "
                     "최근매출액 대비 30.74%다. 3월 계약(2,409억원)의 약 4배 규모다.",
            "match": ["2. 계약내역 | 계약금액(원)"], "span": 3,
        },
        {
            "doc_id": "exchange_20241218800350",
            "event": "신규시설투자 정정공시. 정정사유는 '투자 금액 변경'으로, "
                     "투자금액을 1,980,100,000,000원에서 2,009,800,000,000원으로 297억원 늘렸다. "
                     "자기자본대비 비율은 22.01%에서 22.34%가 됐다.",
            "match": ["3. 정정사유"], "span": 1,
            "changed_fields": [
                {"field": "2. 투자내역- 투자금액(원)", "before": "1,980,100,000,000",
                 "after": "2,009,800,000,000"},
            ],
        },
    ],
}

CASES = [CASE_001, CASE_002, CASE_003]
