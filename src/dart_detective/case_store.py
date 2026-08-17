"""Case Pack 로더.

Case Pack은 정적 산출물이다(scripts/build_case_packs.py). 여기서는 읽기만 한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import CaseNotFoundError

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_PACK_DIR = REPO / "data" / "artifacts" / "case_packs"


@dataclass(frozen=True)
class CasePack:
    raw: dict[str, Any]

    @property
    def case_id(self) -> str:
        return self.raw["case_id"]

    @property
    def simulation_date(self) -> str:
        return self.raw["simulation_date"]

    @property
    def documents(self) -> list[dict[str, Any]]:
        return self.raw["available_documents"]

    @property
    def evidence(self) -> list[dict[str, Any]]:
        return self.raw["evidence"]

    @property
    def finance_terms(self) -> list[dict[str, Any]]:
        return self.raw["finance_terms"]

    @property
    def decision_options(self) -> list[dict[str, Any]]:
        return self.raw["decision_options"]

    @property
    def future_events(self) -> list[dict[str, Any]]:
        return self.raw["future_events"]

    def document(self, document_id: str) -> dict[str, Any] | None:
        return next((d for d in self.documents if d["document_id"] == document_id), None)

    def evidence_by_id(self, evidence_id: str) -> dict[str, Any] | None:
        return next((e for e in self.evidence if e["evidence_id"] == evidence_id), None)

    def critical_evidence(self) -> list[dict[str, Any]]:
        return [e for e in self.evidence if e["importance"] == "critical"]

    def briefing(self) -> dict[str, Any]:
        """플레이 시작 시 프론트에 내려보내는 정보. future_events는 포함하지 않는다."""
        return {
            "case_id": self.case_id,
            "company": self.raw["company"],
            "case_title": self.raw["case_title"],
            "simulation_date": self.simulation_date,
            "difficulty": self.raw.get("difficulty", "normal"),
            "mission": self.raw["mission"],
            "intro": self.raw["intro"],
            "documents": [
                {
                    "document_id": d["document_id"],
                    "title": d["title"],
                    "document_date": d["document_date"],
                    "source_type": d["source_type"],
                    "role": d.get("role"),
                    "display_excerpt": d["display_excerpt"],
                }
                for d in self.documents
            ],
            "decision_options": [
                {"option_id": o["option_id"], "label": o["label"], "description": o["description"]}
                for o in self.decision_options
            ],
        }


class CaseStore:
    def __init__(self, pack_dir: Path | str = DEFAULT_PACK_DIR):
        self.pack_dir = Path(pack_dir)
        self._cache: dict[str, CasePack] = {}

    def list_cases(self) -> list[dict[str, Any]]:
        index_path = self.pack_dir / "index.json"
        if index_path.exists():
            return json.loads(index_path.read_text(encoding="utf-8"))["cases"]
        return [
            {"case_id": p.stem, "file": p.name}
            for p in sorted(self.pack_dir.glob("CASE-*.json"))
        ]

    def load(self, case_id: str) -> CasePack:
        if case_id in self._cache:
            return self._cache[case_id]
        path = self.pack_dir / f"{case_id}.json"
        if not path.exists():
            raise CaseNotFoundError(
                f"{case_id} 없음 ({path}). scripts/build_case_packs.py를 먼저 실행하라."
            )
        pack = CasePack(json.loads(path.read_text(encoding="utf-8")))
        self._cache[case_id] = pack
        return pack
