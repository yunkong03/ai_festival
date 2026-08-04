# 제출 계획 — 공식 요건 반영

> 근거: `미래에셋증권 AI Festival 공식 과제 소개.pdf` p.8

## 1. 제출 채널

주최 측 제공 **Github Organization 내 Private Repository**에 push. 대용량 제출물은 압축 후 범용 클라우드 스토리지에 올리고 다운로드 링크만 제출.

## 2. 제출 항목 (예선, 3종) — 마감 **09.06**

| # | 항목 | 내용 |
|---|---|---|
| 1 | 소스코드 | 구현체 소스코드 + 재현 가능한 개발 환경 정의(Dockerfile, requirements.txt 등) + README.md(환경구성·실행 명령어 포함) |
| 2 | 기술 제안서 | 자유 양식. 제안 요약, 문제 정의, 제안 방법, 시스템 구성도, 주요 기능 흐름도, 사용자 시나리오, 기대효과·확장성 |
| 3 | 평가용 API 서버 정보 | End-point URL + API 명세서(요청/응답 JSON 스키마) — **필수 명시** |

**마감 이후 커밋-push, 서버 배포 등 코드/결과물 변경 시 실격.** → 09.06 이전에 반드시 "이걸로 확정"하는 코드 프리즈 타이밍을 팀이 스스로 정해야 한다(`development_roadmap.md` 참조).

## 3. API 스키마 (고정)

```
GET /answer?question_id={id}&question={평가 질의}
```

응답 JSON:

```json
{
  "question_id": "Q-001",
  "question": "평가 질의 원문",
  "retrieved_context": "답변 생성에 참고한 검색 문서",
  "think_trace": "사고 · 추론 · 도구 사용 과정",
  "answer": "최종 생성 답변"
}
```

이는 `interface_contract_draft.md`의 `FinalResponse`와 1:1 대응이며, 공식 스키마 필드명(`question_id`, `question`, `retrieved_context`, `think_trace`, `answer`)을 **그대로** 써야 한다 — 필드명을 임의로 바꾸면 채점 자체가 안 될 위험이 있으므로 이 부분은 A/B/C 누구도 임의 변경 금지.

### `think_trace` 설계 원칙

사용자 지시대로: **비공개 chain-of-thought를 그대로 넣지 않는다.** 대신 구조화된 실행 기록만 담는다:

- 선택된 Task(`TaskPlan.routes`)
- 검색 문서(어떤 `doc_id`/`rcept_no`를 봤는지)
- Evidence(어떤 `evidence_id`를 근거로 썼는지)
- 계산(`CalculationRecord` — 계산식과 결과)
- Version Resolver 결과(`VersionResolutionResult` — 정정 연결 여부와 상태)
- Verifier 결과(`VerificationResult` — hallucination/citation 체크 결과)

이 필드들은 그대로 JSON 직렬화 가능한 dict로 만들면 된다 — 원시 LLM 추론 텍스트(raw CoT)를 그대로 붙여넣지 않는다는 점이 중요. `think_trace`가 구조화되어 있으면 정성평가의 "추론논리성" 항목도 채점자가 검증하기 쉬워진다는 부가 효과가 있다.

## 4. 평가용 API 서버 운영 요건

- 서버 환경 자유 (네이버클라우드(NCP) 제공 크레딧 활용 또는 팀 선호 환경) — **단, Public 망 통신 가능 네트워크 필수**
- 운영 기간: 예선 평가기간 중 정해진 기간 **09.07~09.20** 반드시 API 활성화 유지(변경 시 별도 공지 예정 — `official_qna_questions.md`에서 확정 여부 재확인 필요)
- NCP 자원 사용 시 크레딧 한도 초과 주의(초과분 주최 측 별도 비용보전 없음) — 트래픽/리소스 사용량을 사전에 가늠해 크레딧 한도 내로 설계
- 오프라인 설명회(08.06)에서 네이버클라우드 서비스·사용법 안내 및 Credit 사용 안내 예정, **팀당 최소 1명 필참**

## 5. 제출 전 체크리스트 (초안 — 최종본은 마감 임박 시 갱신)

- [ ] `GET /answer` 엔드포인트가 공식 스키마 그대로 응답하는가 (필드명/타입 확인)
- [ ] `question_id`를 반복 요청해도 동일 질의면 일관된 답변을 주는가 (비결정성 최소화)
- [ ] 코퍼스 밖 질의(기간/기업)에 대해 "확인할 수 없음" 류 명시적 응답을 주는가
- [ ] 모든 answer에 근거 공시(공시명·공시일)가 표시되는가
- [ ] Dockerfile로 처음부터 빌드·기동이 재현되는가 (팀원 본인 PC가 아닌 환경에서 1회 검증)
- [ ] README.md에 환경 구성·실행 명령어가 빠짐없이 있는가
- [ ] 기술 제안서에 시스템 구성도·주요 기능 흐름도·사용자 시나리오가 모두 포함됐는가
- [ ] 서버가 09.06 이전에 최종 코드로 프리즈되고, 09.07~09.20 동안 무중단 운영되는가
- [ ] 사용한 LLM이 HyperCLOVA X뿐인지 코드 전체에서 재확인(다른 LLM 호출 흔적이 있으면 평가대상 제외)
