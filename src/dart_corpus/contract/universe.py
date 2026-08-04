from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

EXPECTED_COMPANY_COUNT = 70


@dataclass(frozen=True)
class CompanyRecord:
    corp_code: str
    stock_code: str
    corp_name: str
    listed_name: str
    corp_eng_name: str
    market: str
    industry: str
    sector_no: int
    sector: str
    listing_date: str
    fiscal_month: str
    market_cap: int
    n_periodic: int
    n_major: int
    n_exchange: int
    n_holding: int
    note: str


class UniverseLoader:
    def __init__(self, corpus_root: Path):
        self.corpus_root = Path(corpus_root)

    def load(self) -> list[CompanyRecord]:
        path = self.corpus_root / "universe.csv"
        records: list[CompanyRecord] = []
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                records.append(
                    CompanyRecord(
                        corp_code=str(row["corp_code"]),
                        stock_code=str(row["stock_code"]),
                        corp_name=row["corp_name"],
                        listed_name=row["listed_name"],
                        corp_eng_name=row["corp_eng_name"],
                        market=row["market"],
                        industry=row["industry"],
                        sector_no=int(row["sector_no"]),
                        sector=row["sector"],
                        listing_date=row["listing_date"],
                        fiscal_month=row["fiscal_month"],
                        market_cap=int(row["market_cap"]),
                        n_periodic=int(row["n_periodic"]),
                        n_major=int(row["n_major"]),
                        n_exchange=int(row["n_exchange"]),
                        n_holding=int(row["n_holding"]),
                        note=row.get("note") or "",
                    )
                )
        if len(records) != EXPECTED_COMPANY_COUNT:
            logger.warning(
                "universe.csv row count=%d, expected %d",
                len(records), EXPECTED_COMPANY_COUNT,
            )
        return records
