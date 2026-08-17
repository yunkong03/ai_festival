"""LLM provider 추상화.

의미 판단이 필요한 곳(Evidence Agent의 자유질문 해석, Tutor의 힌트 문장)에서만 쓴다.
버튼으로 구분되는 행동에는 LLM을 부르지 않는다.

자격증명이 없으면 `get_llm()`이 None을 반환하고, 각 Agent는 결정론적 fallback으로
동작한다 — 데모가 네트워크/키 없이도 끝까지 돌아가야 하기 때문이다.
강제로 끄려면 환경변수 `DART_DETECTIVE_LLM=off`.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Claude 모델 ID는 날짜 접미사 없이 그대로 쓴다.
DEFAULT_MODEL = "claude-opus-5"


@dataclass
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    latency_ms: int
    raw_text: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


class LLMUnavailable(RuntimeError):
    """호출 가능한 LLM이 없다."""


class AnthropicLLM:
    """Anthropic Messages API + Structured Outputs.

    JSON 스키마를 `output_config.format`으로 강제하므로 파싱 실패를 걱정하지 않는다.
    """

    provider = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = "low",
                 max_tokens: int = 4000):
        import anthropic  # 지연 import — 패키지가 없어도 rule-based 경로는 살아야 한다

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        t0 = time.perf_counter()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=[{"role": "user", "content": user}],
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if response.stop_reason == "refusal":
            raise LLMUnavailable("모델이 요청을 거절했다(stop_reason=refusal)")

        text = next((b.text for b in response.content if b.type == "text"), "")
        return LLMResult(
            data=json.loads(text),
            provider=self.provider,
            model=response.model,
            latency_ms=latency_ms,
            raw_text=text,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )


def _has_credentials() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    # `ant auth login`으로 저장된 프로파일이 있으면 SDK가 자동으로 집어간다.
    config_dir = os.environ.get("ANTHROPIC_CONFIG_DIR")
    candidates = [Path(config_dir)] if config_dir else [
        Path.home() / ".config" / "anthropic",
        Path(os.environ.get("APPDATA", "")) / "Anthropic" if os.environ.get("APPDATA") else None,
    ]
    for base in candidates:
        if base and (base / "credentials").exists():
            return True
    return False


def get_llm(model: str = DEFAULT_MODEL) -> AnthropicLLM | None:
    """호출 가능한 LLM이 있으면 반환, 없으면 None(= 결정론적 fallback 사용)."""
    if os.environ.get("DART_DETECTIVE_LLM", "").lower() in {"off", "0", "false"}:
        return None
    if not _has_credentials():
        return None
    try:
        return AnthropicLLM(model=model)
    except Exception:  # SDK 미설치, 클라이언트 생성 실패 등
        return None
