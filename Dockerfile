# 공시 탐정사무소 웹 데모 — 단일 컨테이너.
# Hugging Face Spaces(Docker SDK) / Render / Fly.io / Cloud Run 어디서든 그대로 뜬다.
#
#   docker build -t dart-detective .
#   docker run -p 7860:7860 dart-detective
#   -> http://localhost:7860
#
# 주의: 세션은 프로세스 메모리(InMemorySaver)에 있다. 반드시 단일 워커로 띄운다.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PORT=7860 \
    DART_DETECTIVE_LLM=off

WORKDIR /app

# 런타임 의존성만 설치한다(파싱 파이프라인용 tiktoken/bs4는 데모에 필요 없다).
# anthropic은 넣어둔다 — LLM을 켤 때 이미지 재빌드 없이 환경변수만 바꾸면 되게.
RUN pip install --no-cache-dir \
        "langgraph>=0.2" \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.30" \
        "pydantic>=2.7" \
        "anthropic>=0.40"

# 앱 소스 + 데이터
COPY src/dart_detective/ /app/src/dart_detective/
COPY scripts/build_case_search_index.py scripts/case_pack_render.py /app/scripts/
COPY data/artifacts/case_packs/CASE-001.json \
     data/artifacts/case_packs/CASE-002.json \
     data/artifacts/case_packs/CASE-003.json \
     data/artifacts/case_packs/index.json \
     /app/data/artifacts/case_packs/

# 검색 인덱스는 이미지 빌드 시점에 Case Pack에서 만든다.
# (_source_docs.jsonl 캐시는 저장소에 없으므로 미래 문서는 Case Pack 발췌만 색인된다 —
#  어차피 Point-in-Time 필터가 걸러내므로 플레이에는 영향이 없다.)
RUN python scripts/build_case_search_index.py

# 임포트 스모크 — 깨진 이미지를 배포하지 않는다.
RUN python -c "from dart_detective.api import app; print('import ok')"

EXPOSE 7860

# 단일 워커. 멀티 워커로 띄우면 세션이 워커마다 따로 생겨 게임이 끊긴다.
CMD ["sh", "-c", "uvicorn dart_detective.api:app --host 0.0.0.0 --port ${PORT} --workers 1"]
