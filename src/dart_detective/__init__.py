"""dart_detective — 금융 탐정게임 Agent Backend.

Case Pack(data/artifacts/case_packs/CASE-*.json)을 읽어 LangGraph 기반 플레이 세션을 돌린다.

MVP에서 확실히 동작해야 하는 세 가지:
  1) Point-in-Time Retrieval — document_date <= simulation_date를 Retriever 계층에서 차단
  2) Evidence 기반 AI Hint — 정답을 알려주지 않고 조사 방향만 제시
  3) LangGraph State 관리 — checkpoint 지원
"""

__all__ = ["state", "graph", "retriever", "case_store", "llm", "trace"]
