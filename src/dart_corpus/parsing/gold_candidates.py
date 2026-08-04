"""Parser Gold 후보 생성 — 아직 정답(gold)이 아니다. doc_group x parse_quality_tier로
층화한 후보 목록과, 사람이 직접 채울 annotation template만 만든다. 자동 라벨링 금지
(선정 이유는 "왜 이 문서를 사람이 봐야 하는지"이지 "이 문서가 맞다"가 아니다).
"""
from __future__ import annotations

import csv
import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dart_corpus.parsing.audit import ParseAuditRecord

ANNOTATION_COLUMNS = [
    "doc_id", "doc_group", "parse_quality_tier", "selection_reason",
    "reviewer_name", "review_date",
    "structure_correct", "section_hierarchy_correct", "table_correct", "consolidation_basis_correct",
    "issues_found", "decision", "notes",
]


@dataclass
class GoldCandidate:
    doc_id: str
    doc_group: str
    parse_quality_tier: str
    selection_reason: str
    warning_codes: list[str] = field(default_factory=list)
    n_tables: int = 0
    n_sections: int = 0
    text_preservation_ratio: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _proportional_allocation(strata: dict, target_total: int) -> dict:
    """stratum 크기 비례 배분(최소 1건, stratum 크기 초과 불가) + 나머지는 소수부가
    큰 stratum부터 채워 target_total에 최대한 맞춘다(고전적 largest-remainder 방식)."""
    keys = sorted(strata.keys())
    total_docs = sum(len(v) for v in strata.values())
    if total_docs == 0:
        return {}

    raw_share = {k: target_total * len(strata[k]) / total_docs for k in keys}
    alloc = {k: min(max(1, int(raw_share[k])), len(strata[k])) for k in keys}

    remainder_order = sorted(keys, key=lambda k: raw_share[k] - int(raw_share[k]), reverse=True)
    current_total = sum(alloc.values())
    idx = 0
    while current_total < target_total and any(alloc[k] < len(strata[k]) for k in keys):
        k = remainder_order[idx % len(remainder_order)]
        if alloc[k] < len(strata[k]):
            alloc[k] += 1
            current_total += 1
        idx += 1

    while current_total > target_total:
        k = max(keys, key=lambda k: alloc[k])
        if alloc[k] <= 1:
            break
        alloc[k] -= 1
        current_total -= 1

    return alloc


def select_gold_candidates(audits: list[ParseAuditRecord], *, target_total: int = 90, seed: int = 0) -> list[GoldCandidate]:
    """doc_group x parse_quality_tier로 층화 후, stratum 크기 비례로 target_total건을
    뽑는다. 각 non-empty stratum은 최소 1건은 포함(있는지 눈으로 확인해야 하므로).
    실제 gold 판정(맞다/틀리다)은 하지 않는다 — 사람이 검수할 후보만 고른다."""
    strata: dict[tuple[str, str], list[ParseAuditRecord]] = {}
    for a in audits:
        strata.setdefault((a.doc_group, a.parse_quality_tier), []).append(a)
    if not strata:
        return []

    alloc = _proportional_allocation(strata, target_total)
    rng = random.Random(seed)

    candidates: list[GoldCandidate] = []
    for key in sorted(strata.keys()):
        doc_group, tier = key
        n = alloc.get(key, 0)
        if n == 0:
            continue
        stratum = sorted(strata[key], key=lambda a: a.doc_id)   # 샘플링 전 정렬 — seed만으로 재현 가능하게
        chosen = rng.sample(stratum, n)
        reason = (
            f"stratified sample: doc_group={doc_group} parse_quality_tier={tier} "
            f"(stratum_size={len(stratum)}, selected={n}/{target_total} target)"
        )
        for a in chosen:
            candidates.append(GoldCandidate(
                doc_id=a.doc_id, doc_group=doc_group, parse_quality_tier=tier, selection_reason=reason,
                warning_codes=list(a.warning_codes), n_tables=a.n_tables, n_sections=a.n_sections,
                text_preservation_ratio=a.text_preservation_ratio,
            ))
    return candidates


def write_gold_candidates_jsonl(candidates: list[GoldCandidate], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False))
            f.write("\n")


def write_annotation_template_csv(candidates: list[GoldCandidate], path: Path) -> None:
    """사람이 직접 채우는 검수 템플릿 — doc_id/선정근거만 미리 채우고 판정 컬럼은
    전부 빈칸으로 둔다(자동 정답처리 금지)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ANNOTATION_COLUMNS)
        writer.writeheader()
        for c in candidates:
            writer.writerow({
                "doc_id": c.doc_id, "doc_group": c.doc_group, "parse_quality_tier": c.parse_quality_tier,
                "selection_reason": c.selection_reason,
                "reviewer_name": "", "review_date": "",
                "structure_correct": "", "section_hierarchy_correct": "", "table_correct": "",
                "consolidation_basis_correct": "", "issues_found": "", "decision": "", "notes": "",
            })
