# DART Corpus MVP Fact Store — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a manifest-driven pipeline that loads the DART corpus contract (`manifest.jsonl` + `universe.csv`), routes each document to the correct structural parser, extracts investment/contract amounts for the three in-scope 거래소공시 subtypes with full row/cell traceability, and produces a best-effort (never auto-forced) correction↔original linkage.

**Architecture:** A read-only *contract layer* (`ManifestLoader`, `UniverseLoader`, `CorpAliasIndex`) is the single source of truth for what documents exist and where — nothing scans `raw/` directly. A *parsing layer* (`BaseDocumentParser` → `DartDocumentParser` / `KindXFormsParser`, dispatched by `ParserRouter`) turns each document's XML file(s) into `Chunk`/`Evidence` objects with deterministic, reproducible IDs. A *facts layer* extracts typed values (amounts, dates) from evidence via a label-alias table, writes them to an append-only `FactStore`, and a *corrections layer* (`CorrectionResolver`) proposes — but never silently applies — a link from a `[기재정정]` document back to its original.

**Tech Stack:** Python 3.12, stdlib `xml.etree.ElementTree` (DART schema, with a documented ampersand/bracket sanitizer — see Global Constraints), `beautifulsoup4` with the built-in `html.parser` backend (KIND xforms HTML), `pandas` (only for the README-documented convenience loaders, not for parsing), `pyyaml` (alias exceptions), `pytest`.

## Global Constraints

- **Manifest is the source of truth.** Never call `Path.rglob`/`os.walk` on `raw/` to discover documents. The only inputs are `manifest.jsonl` and `universe.csv`.
- **`corp_code` and `stock_code` load as `str`, always**, preserving leading zeros (e.g. `"00126380"`, `"005930"`). Never cast to `int`.
- **`doc_id` comes from the manifest** (`{doc_group}_{rcept_no}`, e.g. `exchange_20250120800389`). Never mint a new document identifier.
- **One manifest row = one document**, even when its `file_path` folder holds multiple XML files (`n_files > 1`). Never turn per-folder XML files into separate documents.
- **`file_format=pdf+html` (3 docs) is unsupported by the XML parser and must be recorded as such explicitly** — never silently dropped from a document listing.
- **No single regex/parser handles all XML.** `doc_group` (`major`/`periodic`/`holding` → DART schema, `exchange` → KIND xforms HTML) picks the *expected* parser; actual root-structure sniffing confirms or overrides it with a logged warning.
- **Chunk/evidence IDs are deterministic**, derived only from `doc_id` + the XML file's path relative to `file_path` + a section path + table-or-paragraph sequence + row/cell sequence. Re-parsing the same document must yield byte-identical IDs.
- **Corrections are never auto-linked.** `is_correction=true` is the only fact given for free; linking to an original is a best-effort candidate match producing one of `resolved`/`probable`/`ambiguous`/`unresolved`/`manually_resolved`, and only `resolved`/`manually_resolved` may ever be treated as "this is the current version."
- **No amount/date math happens outside Python.** Extraction returns raw text + a parsed value computed in Python; an LLM is never asked to compute or normalize a number.
- **Errors are logged, never swallowed.** Any unresolvable path, unparseable XML, or unmatched label is logged via `logging` (module logger, not `print`) and, where it affects a document's outcome, surfaces in that document's `ParsedDocument.warnings`.
- **Environment-specific finding (not in the original spec, discovered during research — see Task 1):** this corpus lives on a WSL-mounted filesystem where every Korean-character directory name under `raw/<doc_group>/` is stored **NFD**-normalized, while `manifest.jsonl`'s `file_path` strings are **NFC**. A direct `Path(file_path).exists()` silently returns `False` for every non-ASCII company folder. All filesystem access to `raw/` MUST go through `resolve_corpus_path()` (Task 1), never through a raw `Path` join.
- **Environment-specific finding (Task 6):** real DART-schema XML (`major`/`periodic`/`holding`) is not always well-formed — free-text narrative sections contain bare `&` (e.g. `R&D`) and bare `<` used as decorative brackets (e.g. `< TV 시장점유율 추이 >`). `DartDocumentParser` sanitizes both before calling `ElementTree`, and any file that still fails to parse after sanitization is recorded as a parser warning, never crashes the run.

---

## File Structure

```
dart_project/
├── pyproject.toml
├── config/
│   └── alias_exceptions.yaml       # corp-name alias overrides (현대차→현대자동차 etc.)
├── src/dart_corpus/
│   ├── __init__.py
│   ├── config.py                   # default_corpus_root()
│   ├── contract/
│   │   ├── __init__.py
│   │   ├── paths.py                 # resolve_corpus_path(), list_xml_files()  [Task 1]
│   │   ├── manifest.py              # DocumentRecord, ManifestLoader           [Task 2]
│   │   ├── universe.py              # CompanyRecord, UniverseLoader            [Task 2]
│   │   └── alias.py                 # CorpAliasIndex, AmbiguousAliasError      [Task 3]
│   ├── parsing/
│   │   ├── __init__.py
│   │   ├── ids.py                   # make_chunk_id(), make_evidence_id()     [Task 4]
│   │   ├── base.py                  # Chunk, Evidence, ParsedDocument, ParserWarning, BaseDocumentParser [Task 4]
│   │   ├── kind_parser.py           # KindXFormsParser                        [Task 5]
│   │   ├── dart_parser.py           # DartDocumentParser + XML sanitizer      [Task 6]
│   │   └── router.py                # ParserRouter                            [Task 7]
│   ├── facts/
│   │   ├── __init__.py
│   │   ├── labels.py                # LABEL_ALIASES                          [Task 8]
│   │   ├── extractors.py            # parse_amount_krw(), extract_facts()    [Task 8]
│   │   └── store.py                 # FactStore                              [Task 9]
│   └── corrections/
│       ├── __init__.py
│       ├── models.py                # LinkStatus, CorrectionLink             [Task 10]
│       └── resolver.py              # normalize_date(), CorrectionResolver   [Task 10]
├── scripts/
│   └── run_mvp_extraction.py        # end-to-end MVP runner                  [Task 9]
└── tests/
    ├── conftest.py                  # corpus_root fixture                    [Task 1]
    ├── contract/
    │   ├── test_paths.py
    │   ├── test_manifest.py
    │   ├── test_universe.py
    │   └── test_alias.py
    ├── parsing/
    │   ├── test_ids.py
    │   ├── test_kind_parser.py
    │   ├── test_dart_parser.py
    │   └── test_router.py
    ├── facts/
    │   └── test_extractors.py
    ├── corrections/
    │   └── test_resolver.py
    └── test_integration_mvp.py      # @pytest.mark.integration, real corpus [Task 11]
```

**Why this split:** `contract/` never imports from `parsing/`, `parsing/` never imports from `facts/` or `corrections/` — each layer depends only on the one below it, so any layer can be reviewed/tested in isolation. `facts/` and `corrections/` are the only modules that know about MVP-specific labels (`투자금액`, `계약금액`, `해지금액`); everything below them is generic across all 4,204 documents, which is what lets a later PR extend the Fact Store beyond MVP scope without touching the parser layer.

---

### Task 1: Corpus path resolution (WSL NFD/NFC fix) + pytest fixture

**Files:**
- Create: `src/dart_corpus/config.py`
- Create: `src/dart_corpus/contract/__init__.py` (empty)
- Create: `src/dart_corpus/contract/paths.py`
- Create: `pyproject.toml`
- Create: `tests/conftest.py`
- Test: `tests/contract/test_paths.py`

**Interfaces:**
- Produces: `default_corpus_root() -> Path`; `resolve_corpus_path(root: Path, relative_posix_path: str) -> Path`; `list_xml_files(doc_dir: Path) -> list[Path]`; `class PathResolutionError(FileNotFoundError)`; pytest fixture `corpus_root` (session-scoped, returns `default_corpus_root()`).

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "dart-corpus"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.0",
    "beautifulsoup4>=4.12",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "integration: exercises the real corpus on disk, slower than unit tests",
]

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: Create `src/dart_corpus/config.py`**

```python
from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def default_corpus_root() -> Path:
    """Root of the DART corpus (contains manifest.jsonl, universe.csv, raw/).

    Overridable via DART_CORPUS_ROOT for CI or alternate checkouts.
    """
    env = os.environ.get("DART_CORPUS_ROOT")
    if env:
        return Path(env)
    return _PROJECT_ROOT / "data" / "3.공시" / "corpus"
```

- [ ] **Step 3: Write the failing test for path resolution**

```python
# tests/contract/test_paths.py
import pytest

from dart_corpus.contract.paths import PathResolutionError, list_xml_files, resolve_corpus_path


def test_resolves_nfd_company_folder(corpus_root):
    # "raw/major/삼성전자" is stored NFC in manifest.jsonl but the actual
    # directory entry on this WSL mount is NFD-normalized; a naive
    # Path join would report this as missing.
    resolved = resolve_corpus_path(corpus_root, "raw/major/삼성전자")
    assert resolved.is_dir()
    assert resolved.name.count("삼") >= 1  # sanity: still the right folder


def test_resolves_full_document_path_and_lists_xml(corpus_root):
    doc_dir = resolve_corpus_path(
        corpus_root, "raw/exchange/HD현대일렉트릭/20250120800389"
    )
    xml_files = list_xml_files(doc_dir)
    assert [p.name for p in xml_files] == ["20250120800389.xml"]


def test_raises_on_missing_segment(corpus_root):
    with pytest.raises(PathResolutionError):
        resolve_corpus_path(corpus_root, "raw/major/이런회사는없음/00000000000000")
```

- [ ] **Step 4: Create `tests/conftest.py` fixture, run the test, verify it fails**

```python
# tests/conftest.py
import pytest

from dart_corpus.config import default_corpus_root


@pytest.fixture(scope="session")
def corpus_root():
    root = default_corpus_root()
    assert root.exists(), f"corpus root not found: {root}"
    return root
```

Run: `python -m pytest tests/contract/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dart_corpus.contract.paths'`

- [ ] **Step 5: Implement `src/dart_corpus/contract/paths.py`**

```python
from __future__ import annotations

import logging
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)


class PathResolutionError(FileNotFoundError):
    """A manifest-declared relative path could not be found on disk."""


def resolve_corpus_path(root: Path, relative_posix_path: str) -> Path:
    """Resolve a manifest `file_path` (always POSIX-separated, NFC Korean
    text) against the corpus root.

    Company-name directories under raw/<doc_group>/ are NFD-normalized on
    this WSL mount while manifest.jsonl stores NFC — a plain Path join
    silently fails to find them. This walks the path one segment at a time:
    if the direct join exists, use it (fast path, also correct for ASCII
    segments); otherwise scan the parent directory and match by
    NFC-normalized name.
    """
    current = Path(root)
    for segment in relative_posix_path.split("/"):
        if not segment:
            continue
        candidate = current / segment
        if candidate.exists():
            current = candidate
            continue
        target_nfc = unicodedata.normalize("NFC", segment)
        match = None
        for child in current.iterdir():
            if unicodedata.normalize("NFC", child.name) == target_nfc:
                match = child
                break
        if match is None:
            raise PathResolutionError(
                f"cannot resolve segment {segment!r} under {current} "
                f"(from relative path {relative_posix_path!r})"
            )
        logger.debug("resolved NFD segment %r -> %s", segment, match)
        current = match
    return current


def list_xml_files(doc_dir: Path) -> list[Path]:
    return sorted(p for p in doc_dir.iterdir() if p.suffix.lower() == ".xml")
```

- [ ] **Step 6: Run tests, verify pass**

Run: `python -m pytest tests/contract/test_paths.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/dart_corpus/config.py src/dart_corpus/contract/__init__.py \
        src/dart_corpus/contract/paths.py tests/conftest.py tests/contract/test_paths.py
git commit -m "feat: corpus path resolution tolerant of NFD company folders"
```

---

### Task 2: Contract loaders — `UniverseLoader` and `ManifestLoader`

**Files:**
- Create: `src/dart_corpus/contract/universe.py`
- Create: `src/dart_corpus/contract/manifest.py`
- Test: `tests/contract/test_universe.py`
- Test: `tests/contract/test_manifest.py`

**Interfaces:**
- Consumes: `default_corpus_root()` (Task 1, via `corpus_root` fixture).
- Produces: `@dataclass CompanyRecord` (fields: `corp_code, stock_code, corp_name, listed_name, corp_eng_name, market, industry, sector_no, sector, listing_date, fiscal_month, market_cap, n_periodic, n_major, n_exchange, n_holding, note`, all `str` except `sector_no, market_cap, n_periodic, n_major, n_exchange, n_holding: int`); `class UniverseLoader: def __init__(self, corpus_root: Path); def load(self) -> list[CompanyRecord]`. `@dataclass(frozen=True) DocumentRecord` (fields listed in Global Constraints' manifest field list, `corp_code/stock_code/rcept_no/rcept_dt: str`, `is_correction: bool`, `n_files: int`); `class ManifestLoader: SUPPORTED_FORMATS = {"xml"}; def __init__(self, corpus_root: Path); def load(self) -> list[DocumentRecord]; def unsupported(self, records) -> list[DocumentRecord]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/contract/test_universe.py
from dart_corpus.contract.universe import UniverseLoader


def test_loads_70_companies_with_string_codes(corpus_root):
    companies = UniverseLoader(corpus_root).load()
    assert len(companies) == 70
    samsung = next(c for c in companies if c.corp_name == "삼성전자")
    assert samsung.corp_code == "00126380"
    assert isinstance(samsung.corp_code, str)
    assert samsung.stock_code == "005930"
    assert samsung.sector == "반도체·전자부품"
```

```python
# tests/contract/test_manifest.py
from dart_corpus.contract.manifest import ManifestLoader


def test_loads_4204_documents_with_string_codes(corpus_root):
    docs = ManifestLoader(corpus_root).load()
    assert len(docs) == 4204
    samsung_quarter = next(
        d for d in docs if d.doc_id == "periodic_20230515002335"
    )
    assert samsung_quarter.corp_code == "00126380"
    assert isinstance(samsung_quarter.corp_code, str)
    assert samsung_quarter.file_path == (
        "raw/periodic/삼성전자/20230515002335_quarter_2023_03"
    )


def test_flags_pdf_html_as_unsupported_not_dropped(corpus_root):
    loader = ManifestLoader(corpus_root)
    docs = loader.load()
    unsupported = loader.unsupported(docs)
    assert len(unsupported) == 3
    assert all(d.file_format == "pdf+html" for d in unsupported)
    # still present in the full list, not silently removed
    assert all(d in docs for d in unsupported)


def test_mvp_scope_counts_match_readme(corpus_root):
    docs = ManifestLoader(corpus_root).load()
    exchange = [d for d in docs if d.doc_group == "exchange"]
    counts = {}
    for d in exchange:
        counts[d.doc_subtype] = counts.get(d.doc_subtype, 0) + 1
    assert counts["신규시설투자등"] == 43
    assert counts["단일판매공급계약체결"] == 1106
    assert counts["단일판매공급계약해지"] == 20
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/contract/test_universe.py tests/contract/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dart_corpus/contract/universe.py`**

```python
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
                        note=row["note"],
                    )
                )
        if len(records) != EXPECTED_COMPANY_COUNT:
            logger.warning(
                "universe.csv row count=%d, expected %d",
                len(records), EXPECTED_COMPANY_COUNT,
            )
        return records
```

- [ ] **Step 4: Implement `src/dart_corpus/contract/manifest.py`**

```python
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

EXPECTED_DOCUMENT_COUNT = 4204


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    corp_code: str
    corp_name: str
    listed_name: str
    stock_code: str
    industry: str
    sector: str
    doc_group: str
    doc_subtype: str
    report_nm: str
    rcept_no: str
    rcept_dt: str
    flr_nm: str
    is_correction: bool
    file_path: str
    file_format: str
    n_files: int
    base_year: int | None = None
    base_month: int | None = None


class ManifestLoader:
    SUPPORTED_FORMATS = {"xml"}

    def __init__(self, corpus_root: Path):
        self.corpus_root = Path(corpus_root)

    def load(self) -> list[DocumentRecord]:
        manifest_path = self.corpus_root / "manifest.jsonl"
        records: list[DocumentRecord] = []
        with open(manifest_path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                record = DocumentRecord(
                    doc_id=raw["doc_id"],
                    corp_code=str(raw["corp_code"]),
                    corp_name=raw["corp_name"],
                    listed_name=raw["listed_name"],
                    stock_code=str(raw["stock_code"]),
                    industry=raw["industry"],
                    sector=raw["sector"],
                    doc_group=raw["doc_group"],
                    doc_subtype=raw["doc_subtype"],
                    report_nm=raw["report_nm"],
                    rcept_no=raw["rcept_no"],
                    rcept_dt=raw["rcept_dt"],
                    flr_nm=raw.get("flr_nm", ""),
                    is_correction=bool(raw["is_correction"]),
                    file_path=raw["file_path"],
                    file_format=raw["file_format"],
                    n_files=int(raw["n_files"]),
                    base_year=raw.get("base_year"),
                    base_month=raw.get("base_month"),
                )
                if record.file_format not in self.SUPPORTED_FORMATS:
                    logger.warning(
                        "unsupported file_format=%s doc_id=%s (manifest line %d) "
                        "— flagged as unsupported, XML parser will not process it",
                        record.file_format, record.doc_id, lineno,
                    )
                records.append(record)
        if len(records) != EXPECTED_DOCUMENT_COUNT:
            logger.warning(
                "manifest.jsonl document count=%d, expected %d",
                len(records), EXPECTED_DOCUMENT_COUNT,
            )
        return records

    def unsupported(self, records: list[DocumentRecord]) -> list[DocumentRecord]:
        return [r for r in records if r.file_format not in self.SUPPORTED_FORMATS]
```

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/contract/test_universe.py tests/contract/test_manifest.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/dart_corpus/contract/universe.py src/dart_corpus/contract/manifest.py \
        tests/contract/test_universe.py tests/contract/test_manifest.py
git commit -m "feat: manifest and universe loaders as the document source of truth"
```

---

### Task 3: `CorpAliasIndex`

**Files:**
- Create: `config/alias_exceptions.yaml`
- Create: `src/dart_corpus/contract/alias.py`
- Test: `tests/contract/test_alias.py`

**Interfaces:**
- Consumes: `CompanyRecord` (Task 2).
- Produces: `class AmbiguousAliasError(Exception)`; `class CorpAliasIndex: def __init__(self, companies: list[CompanyRecord], exceptions_path: Path | None = None); def resolve(self, query: str) -> str` (returns the canonical `corp_name`, raises `KeyError` if unknown, raises `AmbiguousAliasError` if the query matches more than one company).

- [ ] **Step 1: Create `config/alias_exceptions.yaml`**

```yaml
# Exception aliases only — the base index already auto-generates keys from
# corp_name / listed_name / corp_eng_name / stock_code / corp_code.
현대차: 현대자동차
KT: 케이티
엔씨소프트: NC
JYP Ent.: JYP Ent
LIG넥스원: LIG디펜스앤에어로스페이스
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/contract/test_alias.py
import pytest

from dart_corpus.contract.alias import AmbiguousAliasError, CorpAliasIndex
from dart_corpus.contract.universe import CompanyRecord


def _company(**overrides) -> CompanyRecord:
    base = dict(
        corp_code="00000000", stock_code="000000", corp_name="테스트기업",
        listed_name="테스트", corp_eng_name="Test Co", market="KOSPI",
        industry="IT", sector_no=1, sector="테스트섹터", listing_date="2000-01-01",
        fiscal_month="12월", market_cap=0, n_periodic=0, n_major=0,
        n_exchange=0, n_holding=0, note="",
    )
    base.update(overrides)
    return CompanyRecord(**base)


def test_resolves_by_any_base_key():
    companies = [_company(corp_name="삼성전자", stock_code="005930", corp_code="00126380")]
    index = CorpAliasIndex(companies)
    assert index.resolve("삼성전자") == "삼성전자"
    assert index.resolve("005930") == "삼성전자"
    assert index.resolve("00126380") == "삼성전자"


def test_exception_alias_overrides_readme_examples(corpus_root):
    from dart_corpus.contract.universe import UniverseLoader

    companies = UniverseLoader(corpus_root).load()
    index = CorpAliasIndex(companies, exceptions_path="config/alias_exceptions.yaml")
    assert index.resolve("현대차") == "현대자동차"
    assert index.resolve("KT") == "케이티"
    assert index.resolve("엔씨소프트") == "NC"
    assert index.resolve("JYP Ent.") == "JYP Ent"


def test_ambiguous_query_raises_not_arbitrary_pick():
    companies = [
        _company(corp_name="A사", corp_eng_name="Shared Name Inc"),
        _company(corp_name="B사", corp_eng_name="Shared Name Inc"),
    ]
    index = CorpAliasIndex(companies)
    with pytest.raises(AmbiguousAliasError):
        index.resolve("Shared Name Inc")


def test_unknown_query_raises_keyerror():
    index = CorpAliasIndex([_company()])
    with pytest.raises(KeyError):
        index.resolve("존재하지않는기업")
```

- [ ] **Step 3: Run tests, verify failure**

Run: `python -m pytest tests/contract/test_alias.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement `src/dart_corpus/contract/alias.py`**

```python
from __future__ import annotations

from pathlib import Path

import yaml

from dart_corpus.contract.universe import CompanyRecord


class AmbiguousAliasError(Exception):
    def __init__(self, query: str, candidates: list[str]):
        super().__init__(
            f"alias {query!r} matches multiple companies: {sorted(candidates)}"
        )
        self.query = query
        self.candidates = candidates


class CorpAliasIndex:
    """Maps a free-form user query (name, ticker, DART code) to the
    canonical corp_name used as the raw/ folder and manifest join key.
    """

    def __init__(
        self,
        companies: list[CompanyRecord],
        exceptions_path: str | Path | None = None,
    ):
        self._index: dict[str, set[str]] = {}
        for company in companies:
            for key in (
                company.corp_name,
                company.listed_name,
                company.corp_eng_name,
                company.stock_code,
                company.corp_code,
            ):
                if key:
                    self._index.setdefault(key, set()).add(company.corp_name)

        if exceptions_path is not None and Path(exceptions_path).exists():
            with open(exceptions_path, encoding="utf-8") as f:
                exceptions = yaml.safe_load(f) or {}
            for alias, canonical_corp_name in exceptions.items():
                self._index[alias] = {canonical_corp_name}

    def resolve(self, query: str) -> str:
        candidates = self._index.get(query)
        if not candidates:
            raise KeyError(f"no company matches alias: {query!r}")
        if len(candidates) > 1:
            raise AmbiguousAliasError(query, sorted(candidates))
        return next(iter(candidates))
```

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/contract/test_alias.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add config/alias_exceptions.yaml src/dart_corpus/contract/alias.py tests/contract/test_alias.py
git commit -m "feat: company alias index with explicit ambiguity errors"
```

---

### Task 4: Reproducible chunk/evidence IDs + base parser types

**Files:**
- Create: `src/dart_corpus/parsing/__init__.py` (empty)
- Create: `src/dart_corpus/parsing/ids.py`
- Create: `src/dart_corpus/parsing/base.py`
- Test: `tests/parsing/test_ids.py`

**Interfaces:**
- Produces: `make_chunk_id(doc_id: str, rel_path: str, section_path: str, seq: int) -> str`; `make_evidence_id(chunk_id: str, row: int, col: int) -> str`; `class ChunkKind(str, Enum): TABLE = "table"; PARAGRAPH = "paragraph"`; `@dataclass(frozen=True) Evidence(evidence_id, chunk_id, row, col, label: str | None, value: str)`; `@dataclass Chunk(chunk_id, doc_id, rel_path, section_path, kind: ChunkKind, index: int, text: str, evidences: list[Evidence])`; `@dataclass ParserWarning(doc_id, rel_path, message)`; `@dataclass ParsedDocument(doc_id, chunks: list[Chunk], warnings: list[ParserWarning])`; `class BaseDocumentParser: name: str; def can_parse(self, doc: DocumentRecord, xml_path: Path) -> bool; def parse(self, doc: DocumentRecord, xml_path: Path) -> ParsedDocument`.

- [ ] **Step 1: Write the failing test**

```python
# tests/parsing/test_ids.py
from dart_corpus.parsing.ids import make_chunk_id, make_evidence_id


def test_chunk_id_is_reproducible():
    a = make_chunk_id("exchange_20250120800389", "20250120800389.xml", "table", 0)
    b = make_chunk_id("exchange_20250120800389", "20250120800389.xml", "table", 0)
    assert a == b


def test_chunk_id_changes_with_any_input():
    base = make_chunk_id("doc1", "f.xml", "table", 0)
    assert make_chunk_id("doc2", "f.xml", "table", 0) != base
    assert make_chunk_id("doc1", "g.xml", "table", 0) != base
    assert make_chunk_id("doc1", "f.xml", "table", 1) != base
    assert make_chunk_id("doc1", "f.xml", "paragraph", 0) != base


def test_evidence_id_is_reproducible_and_traceable():
    chunk_id = make_chunk_id("doc1", "f.xml", "table", 0)
    ev_a = make_evidence_id(chunk_id, row=2, col=1)
    ev_b = make_evidence_id(chunk_id, row=2, col=1)
    assert ev_a == ev_b
    assert ev_a.startswith(chunk_id)
    assert make_evidence_id(chunk_id, row=3, col=1) != ev_a
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/parsing/test_ids.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dart_corpus/parsing/ids.py`**

```python
from __future__ import annotations


def make_chunk_id(doc_id: str, rel_path: str, section_path: str, seq: int) -> str:
    """Deterministic, human-traceable chunk ID: doc_id + source file's
    path relative to file_path + section path + table-or-paragraph
    sequence number. Same document parsed twice yields the same ID.
    """
    return f"{doc_id}::{rel_path}::{section_path}::t{seq}"


def make_evidence_id(chunk_id: str, row: int, col: int) -> str:
    return f"{chunk_id}::r{row}c{col}"
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/parsing/test_ids.py -v`
Expected: 3 passed

- [ ] **Step 5: Implement `src/dart_corpus/parsing/base.py`** (no test — pure data/interface, exercised by Tasks 5–6)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dart_corpus.contract.manifest import DocumentRecord


class ChunkKind(str, Enum):
    TABLE = "table"
    PARAGRAPH = "paragraph"


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    chunk_id: str
    row: int
    col: int
    label: str | None
    value: str


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    rel_path: str
    section_path: str
    kind: ChunkKind
    index: int
    text: str
    evidences: list[Evidence] = field(default_factory=list)


@dataclass
class ParserWarning:
    doc_id: str
    rel_path: str
    message: str


@dataclass
class ParsedDocument:
    doc_id: str
    chunks: list[Chunk] = field(default_factory=list)
    warnings: list[ParserWarning] = field(default_factory=list)


class BaseDocumentParser:
    name: str = "base"

    def can_parse(self, doc: "DocumentRecord", xml_path: Path) -> bool:
        raise NotImplementedError

    def parse(self, doc: "DocumentRecord", xml_path: Path) -> ParsedDocument:
        raise NotImplementedError
```

- [ ] **Step 6: Commit**

```bash
git add src/dart_corpus/parsing/__init__.py src/dart_corpus/parsing/ids.py \
        src/dart_corpus/parsing/base.py tests/parsing/test_ids.py
git commit -m "feat: deterministic chunk/evidence IDs and base parser interface"
```

---

### Task 5: `KindXFormsParser` (거래소공시 HTML xforms)

**Files:**
- Create: `src/dart_corpus/parsing/kind_parser.py`
- Test: `tests/parsing/test_kind_parser.py`

**Interfaces:**
- Consumes: `BaseDocumentParser`, `Chunk`, `Evidence`, `ChunkKind`, `ParsedDocument`, `ParserWarning` (Task 4); `make_chunk_id`, `make_evidence_id` (Task 4); `DocumentRecord` (Task 2).
- Produces: `class KindXFormsParser(BaseDocumentParser): name = "kind_xforms"`.

**Ground truth used to write this parser** (verified against real files during research): `exchange` documents are HTML, not well-formed XML (`<html><head>...<meta ...>` unclosed, no XML declaration). Each `<table>` is one chunk. Rows are `<tr>` (nested inside `<tbody>`, so `table.find_all("tr")` — not `recursive=False` — must be used). Within a row, direct `<td>` children hold cell text in `<span class="xforms_input">` or plain `<span>`; the **last** `<td>` in a row is always the value, and the **second-to-last** is its label (verified on both a 2-cell row `[label, value]` and a 3-cell row `[group-label, label, value]`, e.g. `HD현대일렉트릭/20250120800389`: `<td>투자금액(원)</td><td colspan="2">211,800,000,000</td>`). A single-`<td>` row (e.g. a lone `-` divider) has no label.

- [ ] **Step 1: Write the failing test**

```python
# tests/parsing/test_kind_parser.py
from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.contract.paths import list_xml_files, resolve_corpus_path
from dart_corpus.parsing.kind_parser import KindXFormsParser


def _doc(**overrides) -> DocumentRecord:
    base = dict(
        doc_id="exchange_20250120800389", corp_code="00108524", corp_name="HD현대일렉트릭",
        listed_name="HD현대일렉트릭", stock_code="267260", industry="산업재",
        sector="전력기기", doc_group="exchange", doc_subtype="신규시설투자등",
        report_nm="신규시설투자등", rcept_no="20250120800389", rcept_dt="20250120",
        flr_nm="HD현대일렉트릭", is_correction=False,
        file_path="raw/exchange/HD현대일렉트릭/20250120800389", file_format="xml", n_files=1,
    )
    base.update(overrides)
    return DocumentRecord(**base)


def test_can_parse_true_for_xforms_html(corpus_root):
    doc = _doc()
    doc_dir = resolve_corpus_path(corpus_root, doc.file_path)
    xml_path = list_xml_files(doc_dir)[0]
    parser = KindXFormsParser()
    assert parser.can_parse(doc, xml_path) is True


def test_extracts_investment_amount_with_traceable_evidence(corpus_root):
    doc = _doc()
    doc_dir = resolve_corpus_path(corpus_root, doc.file_path)
    xml_path = list_xml_files(doc_dir)[0]
    parsed = KindXFormsParser().parse(doc, xml_path)

    assert parsed.doc_id == doc.doc_id
    assert parsed.warnings == []

    matches = [
        ev
        for chunk in parsed.chunks
        for ev in chunk.evidences
        if ev.label == "투자금액(원)"
    ]
    assert len(matches) == 1
    ev = matches[0]
    assert ev.value.strip() == "211,800,000,000"
    assert ev.chunk_id in ev.evidence_id
    assert xml_path.name == "20250120800389.xml"


def test_contract_amount_five_of_five(corpus_root):
    # PoC-verified fixtures: 5 단일판매공급계약체결 disclosures, all 5 extract.
    cases = [
        ("삼성전자", "20260106800025_placeholder", "HD현대일렉트릭", "20260106800025", "98,300,000,000"),
        ("HD현대일렉트릭", "20251222800814", "HD현대일렉트릭", "20251222800814", "181,200,000,000"),
        ("HD현대일렉트릭", "20250922800089", "HD현대일렉트릭", "20250922800089", "258,000,000,000"),
        ("HD현대일렉트릭", "20250731800031", "HD현대일렉트릭", "20250731800031", "140,400,000,000"),
        ("HD현대일렉트릭", "20240830800135", "HD현대일렉트릭", "20240830800135", "66,200,000,000"),
    ]
    parser = KindXFormsParser()
    ok = 0
    for _, _, corp, rcept, expected in cases:
        doc = _doc(
            doc_id=f"exchange_{rcept}", corp_name=corp, rcept_no=rcept,
            doc_subtype="단일판매공급계약체결", file_path=f"raw/exchange/{corp}/{rcept}",
        )
        doc_dir = resolve_corpus_path(corpus_root, doc.file_path)
        xml_path = list_xml_files(doc_dir)[0]
        parsed = parser.parse(doc, xml_path)
        values = [
            ev.value.strip()
            for chunk in parsed.chunks
            for ev in chunk.evidences
            if ev.label == "계약금액(원)"
        ]
        if values and values[0] == expected:
            ok += 1
    assert ok == 4  # first tuple is a deliberately broken fixture, see Step 3 note
```

- [ ] **Step 2: Fix the deliberate fixture typo, run test, verify failure**

The first tuple in `test_contract_amount_five_of_five` above has a placeholder company/rcept pair — replace it with the real fifth fixture before running:

```python
        ("삼성전자", "unused", "HD현대일렉트릭", "20260106800025", "98,300,000,000"),
```
and change the final assertion to `assert ok == 5`.

Run: `python -m pytest tests/parsing/test_kind_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dart_corpus/parsing/kind_parser.py`**

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, Tag

from dart_corpus.parsing.base import (
    BaseDocumentParser,
    Chunk,
    ChunkKind,
    Evidence,
    ParsedDocument,
    ParserWarning,
)
from dart_corpus.parsing.ids import make_chunk_id, make_evidence_id

if TYPE_CHECKING:
    from dart_corpus.contract.manifest import DocumentRecord

logger = logging.getLogger(__name__)


class KindXFormsParser(BaseDocumentParser):
    """Parses KIND(거래소) xforms-style HTML disclosures.

    These files are not well-formed XML — they are loose HTML fragments
    (unclosed <meta>, no XML declaration) authored by the KIND disclosure
    viewer. BeautifulSoup's stdlib html.parser backend tolerates this.
    """

    name = "kind_xforms"

    def can_parse(self, doc: "DocumentRecord", xml_path: Path) -> bool:
        text = xml_path.read_text(encoding="utf-8")
        return "xforms" in text and "<html" in text.lower()

    def parse(self, doc: "DocumentRecord", xml_path: Path) -> ParsedDocument:
        rel_path = xml_path.name
        text = xml_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(text, "html.parser")

        chunks: list[Chunk] = []
        warnings: list[ParserWarning] = []
        tables = soup.find_all("table")
        if not tables:
            warnings.append(
                ParserWarning(doc.doc_id, rel_path, "no <table> found in KIND document")
            )

        for table_index, table in enumerate(tables):
            section_path = f"table[{table_index}]"
            chunk_id = make_chunk_id(doc.doc_id, rel_path, section_path, table_index)
            evidences: list[Evidence] = []
            text_parts: list[str] = []

            rows = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]
            for row_index, row in enumerate(rows):
                cells = [td for td in row.find_all("td", recursive=False)]
                if not cells:
                    continue
                values = [_cell_text(td) for td in cells]
                text_parts.extend(values)
                if len(values) == 1:
                    evidences.append(
                        Evidence(
                            evidence_id=make_evidence_id(chunk_id, row_index, 0),
                            chunk_id=chunk_id,
                            row=row_index,
                            col=0,
                            label=None,
                            value=values[0],
                        )
                    )
                else:
                    label = values[-2]
                    value = values[-1]
                    col = len(values) - 1
                    evidences.append(
                        Evidence(
                            evidence_id=make_evidence_id(chunk_id, row_index, col),
                            chunk_id=chunk_id,
                            row=row_index,
                            col=col,
                            label=label,
                            value=value,
                        )
                    )

            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    rel_path=rel_path,
                    section_path=section_path,
                    kind=ChunkKind.TABLE,
                    index=table_index,
                    text=" | ".join(text_parts),
                    evidences=evidences,
                )
            )

        return ParsedDocument(doc_id=doc.doc_id, chunks=chunks, warnings=warnings)


def _cell_text(td: Tag) -> str:
    return td.get_text(strip=True)
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/parsing/test_kind_parser.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/dart_corpus/parsing/kind_parser.py tests/parsing/test_kind_parser.py
git commit -m "feat: KindXFormsParser for 거래소공시 label/value table extraction"
```

---

### Task 6: `DartDocumentParser` (DART `<DOCUMENT>` schema) + malformed-XML sanitizer

**Files:**
- Create: `src/dart_corpus/parsing/dart_parser.py`
- Test: `tests/parsing/test_dart_parser.py`

**Interfaces:**
- Consumes: same as Task 5.
- Produces: `class DartDocumentParser(BaseDocumentParser): name = "dart_document"`; `sanitize_dart_xml(text: str) -> str` (exported for the router's structure-sniffing fallback and for direct testing).

**Ground truth used to write this parser:** DART-schema files declare `<?xml version="1.0" encoding="utf-8"?><DOCUMENT ...>`. Row shape is `<TR><TD>label</TD><TE ACODE="...">value</TE></TR>` (2-cell) — same "last cell = value, second-to-last = value's label" rule as KIND holds here too, confirmed on `JYP Ent/20251219000396`: `<TD>양수금액(원)</TD><TE ACODE="AC_AMT">75,536,645,829</TE>`. Real filings are **not always well-formed XML**: verified failures include an unescaped `&` in narrative text (`R&D`, `삼성전자/20250311001085.xml` line 277) and a bare `<` used as a decorative bracket (`< TV 시장점유율 추이 >`, same file, line 6263). Both are fixed by escaping any `&` not already part of a valid entity, and any `<` not immediately followed by a letter, `/`, `!`, or `?`.

- [ ] **Step 1: Write the failing test**

```python
# tests/parsing/test_dart_parser.py
from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.contract.paths import list_xml_files, resolve_corpus_path
from dart_corpus.parsing.dart_parser import DartDocumentParser, sanitize_dart_xml


def _doc(**overrides) -> DocumentRecord:
    base = dict(
        doc_id="major_20251219000396", corp_code="00258689", corp_name="JYP Ent",
        listed_name="JYP Ent.", stock_code="035900", industry="커뮤니케이션서비스",
        sector="엔터테인먼트", doc_group="major", doc_subtype="주요사항보고서",
        report_nm="[기재정정]주요사항보고서(유형자산양수결정)", rcept_no="20251219000396",
        rcept_dt="20251219", flr_nm="JYP Ent.", is_correction=True,
        file_path="raw/major/JYP Ent/20251219000396", file_format="xml", n_files=1,
    )
    base.update(overrides)
    return DocumentRecord(**base)


def test_sanitizes_bare_ampersand_and_bare_lt():
    raw = "<P>R&D and < a bracket ></P>"
    fixed = sanitize_dart_xml(raw)
    assert "&amp;" in fixed
    assert "R&D" not in fixed  # the bare ampersand form is gone
    assert "&lt; a bracket" in fixed
    # already-valid entities are left alone
    assert sanitize_dart_xml("&amp;") == "&amp;"
    assert sanitize_dart_xml("&lt;TABLE&gt;") == "&lt;TABLE&gt;"


def test_can_parse_true_for_dart_document(corpus_root):
    doc = _doc()
    doc_dir = resolve_corpus_path(corpus_root, doc.file_path)
    xml_path = list_xml_files(doc_dir)[0]
    assert DartDocumentParser().can_parse(doc, xml_path) is True


def test_extracts_acquisition_amount_and_correction_submission_date(corpus_root):
    doc = _doc()
    doc_dir = resolve_corpus_path(corpus_root, doc.file_path)
    xml_path = list_xml_files(doc_dir)[0]
    parsed = DartDocumentParser().parse(doc, xml_path)

    labels_values = {
        ev.label: ev.value
        for chunk in parsed.chunks
        for ev in chunk.evidences
        if ev.label is not None
    }
    assert labels_values["양수금액(원)"].strip() == "75,536,645,829"
    assert "2023년 10월 24일" in labels_values["2. 정정대상 공시서류의 최초제출일 :"]


def test_handles_real_annual_report_with_malformed_entities(corpus_root):
    # 삼성전자 사업보고서 (2024.12) is known (from research) to contain a
    # bare "&" (R&D) and a bare "<" (decorative "< ... >" bracket) in free
    # text — this must not raise, and must not silently produce zero chunks.
    doc = _doc(
        doc_id="periodic_20250311001085", corp_code="00126380", corp_name="삼성전자",
        doc_group="periodic", doc_subtype="annual", is_correction=False,
        file_path="raw/periodic/삼성전자/20250311001085_annual_2024_12",
    )
    doc_dir = resolve_corpus_path(corpus_root, doc.file_path)
    xml_path = [p for p in list_xml_files(doc_dir) if p.stem == "20250311001085"][0]
    parsed = DartDocumentParser().parse(doc, xml_path)
    assert len(parsed.chunks) > 0
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/parsing/test_dart_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dart_corpus/parsing/dart_parser.py`**

```python
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

from dart_corpus.parsing.base import (
    BaseDocumentParser,
    Chunk,
    ChunkKind,
    Evidence,
    ParsedDocument,
    ParserWarning,
)
from dart_corpus.parsing.ids import make_chunk_id, make_evidence_id

if TYPE_CHECKING:
    from dart_corpus.contract.manifest import DocumentRecord

logger = logging.getLogger(__name__)

_BARE_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_BARE_LT = re.compile(r"<(?![A-Za-z/!?])")

_TABLE_TAGS = {"TABLE"}
_CELL_TAGS = {"TD", "TE", "TU", "TH"}


def sanitize_dart_xml(text: str) -> str:
    """Escape bare '&' and bare '<' found in real DART filings' free-text
    sections (e.g. "R&D", "< TV 시장점유율 추이 >") so ElementTree can parse
    documents that are not, in fact, well-formed XML. Already-valid
    entities and real tag openings are left untouched.
    """
    fixed = _BARE_AMP.sub("&amp;", text)
    fixed = _BARE_LT.sub("&lt;", fixed)
    return fixed


class DartDocumentParser(BaseDocumentParser):
    """Parses DART's own <DOCUMENT> XML schema (major/periodic/holding)."""

    name = "dart_document"

    def can_parse(self, doc: "DocumentRecord", xml_path: Path) -> bool:
        try:
            root = self._parse_root(xml_path)
        except ET.ParseError:
            return False
        return root.tag == "DOCUMENT"

    def parse(self, doc: "DocumentRecord", xml_path: Path) -> ParsedDocument:
        rel_path = xml_path.name
        warnings: list[ParserWarning] = []
        try:
            root = self._parse_root(xml_path)
        except ET.ParseError as exc:
            warnings.append(
                ParserWarning(
                    doc.doc_id, rel_path,
                    f"XML still not well-formed after sanitization: {exc}",
                )
            )
            return ParsedDocument(doc_id=doc.doc_id, chunks=[], warnings=warnings)

        chunks: list[Chunk] = []
        table_index = 0
        for table_elem, section_path in _walk_tables(root):
            chunk = _table_to_chunk(doc.doc_id, rel_path, section_path, table_index, table_elem)
            chunks.append(chunk)
            table_index += 1

        if table_index == 0:
            warnings.append(
                ParserWarning(doc.doc_id, rel_path, "no TABLE element found in DART document")
            )

        return ParsedDocument(doc_id=doc.doc_id, chunks=chunks, warnings=warnings)

    def _parse_root(self, xml_path: Path) -> ET.Element:
        raw = xml_path.read_text(encoding="utf-8")
        fixed = sanitize_dart_xml(raw)
        return ET.fromstring(fixed)


def _walk_tables(root: ET.Element):
    """Yield (table_element, section_path) for every TABLE in document
    order, with section_path built from ancestor SECTION-1/CORRECTION/
    LIBRARY tags and their TITLE text where present.
    """
    stack: list[tuple[ET.Element, str]] = [(root, root.tag)]
    seen = set()
    for elem in root.iter():
        if elem.tag not in _TABLE_TAGS:
            continue
        if id(elem) in seen:
            continue
        seen.add(id(elem))
        section_path = _section_path_for(root, elem)
        yield elem, section_path


def _section_path_for(root: ET.Element, target: ET.Element) -> str:
    path: list[str] = []

    def _find(node: ET.Element, trail: list[str]) -> list[str] | None:
        for child in node:
            new_trail = trail + [child.tag]
            if child is target:
                return trail
            if child.tag in {"SECTION-1", "SECTION-2", "CORRECTION", "LIBRARY", "TABLE-GROUP"}:
                found = _find(child, new_trail)
                if found is not None:
                    return found
            else:
                found = _find(child, new_trail)
                if found is not None:
                    return found
        return None

    found = _find(root, [])
    if found:
        path = found
    return "/".join(path) if path else root.tag


def _table_to_chunk(
    doc_id: str, rel_path: str, section_path: str, table_index: int, table_elem: ET.Element
) -> Chunk:
    chunk_id = make_chunk_id(doc_id, rel_path, section_path, table_index)
    evidences: list[Evidence] = []
    text_parts: list[str] = []

    rows = table_elem.findall(".//TR")
    for row_index, row in enumerate(rows):
        cells = [c for c in row if c.tag in _CELL_TAGS]
        if not cells:
            continue
        values = ["".join(c.itertext()).strip() for c in cells]
        text_parts.extend(values)
        if len(values) == 1:
            evidences.append(
                Evidence(
                    evidence_id=make_evidence_id(chunk_id, row_index, 0),
                    chunk_id=chunk_id, row=row_index, col=0,
                    label=None, value=values[0],
                )
            )
        else:
            label, value = values[-2], values[-1]
            col = len(values) - 1
            evidences.append(
                Evidence(
                    evidence_id=make_evidence_id(chunk_id, row_index, col),
                    chunk_id=chunk_id, row=row_index, col=col,
                    label=label, value=value,
                )
            )

    return Chunk(
        chunk_id=chunk_id, doc_id=doc_id, rel_path=rel_path, section_path=section_path,
        kind=ChunkKind.TABLE, index=table_index, text=" | ".join(text_parts), evidences=evidences,
    )
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/parsing/test_dart_parser.py -v`
Expected: 4 passed. **If `test_handles_real_annual_report_with_malformed_entities` still fails** with a `ParseError`-driven empty-chunks assertion, do not weaken the sanitizer blindly — read the reported line/column from the warning message (add a temporary `print(warnings)` if needed), inspect that exact line in the real file, and extend `_BARE_AMP`/`_BARE_LT` only for the newly observed pattern. This file is large (real annual report); research for this plan validated the fix through line 6263 but did not exhaustively scan every line.

- [ ] **Step 5: Commit**

```bash
git add src/dart_corpus/parsing/dart_parser.py tests/parsing/test_dart_parser.py
git commit -m "feat: DartDocumentParser with malformed-entity sanitizer for real filings"
```

---

### Task 7: `ParserRouter`

**Files:**
- Create: `src/dart_corpus/parsing/router.py`
- Test: `tests/parsing/test_router.py`

**Interfaces:**
- Consumes: `DartDocumentParser`, `KindXFormsParser` (Tasks 5–6); `ManifestLoader.unsupported` (Task 2); `resolve_corpus_path`, `list_xml_files` (Task 1).
- Produces: `@dataclass RoutedDocument(doc: DocumentRecord, parsed: list[ParsedDocument], router_warnings: list[str])`; `class UnsupportedDocumentError(Exception)`; `class ParserRouter: def __init__(self, corpus_root: Path, parsers: list[BaseDocumentParser] | None = None); def route(self, doc: DocumentRecord) -> RoutedDocument`.

- [ ] **Step 1: Write the failing test**

```python
# tests/parsing/test_router.py
import pytest

from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.parsing.router import ParserRouter, UnsupportedDocumentError


def _doc(**overrides) -> DocumentRecord:
    base = dict(
        doc_id="exchange_20250120800389", corp_code="00108524", corp_name="HD현대일렉트릭",
        listed_name="HD현대일렉트릭", stock_code="267260", industry="산업재",
        sector="전력기기", doc_group="exchange", doc_subtype="신규시설투자등",
        report_nm="신규시설투자등", rcept_no="20250120800389", rcept_dt="20250120",
        flr_nm="HD현대일렉트릭", is_correction=False,
        file_path="raw/exchange/HD현대일렉트릭/20250120800389", file_format="xml", n_files=1,
    )
    base.update(overrides)
    return DocumentRecord(**base)


def test_routes_exchange_doc_to_kind_parser(corpus_root):
    router = ParserRouter(corpus_root)
    routed = router.route(_doc())
    assert len(routed.parsed) == 1
    assert routed.router_warnings == []
    assert any(
        ev.label == "투자금액(원)"
        for chunk in routed.parsed[0].chunks
        for ev in chunk.evidences
    )


def test_routes_major_doc_to_dart_parser(corpus_root):
    doc = _doc(
        doc_id="major_20251219000396", doc_group="major", doc_subtype="주요사항보고서",
        corp_name="JYP Ent", rcept_no="20251219000396",
        file_path="raw/major/JYP Ent/20251219000396",
    )
    router = ParserRouter(corpus_root)
    routed = router.route(doc)
    assert len(routed.parsed) == 1
    assert any(
        ev.label == "양수금액(원)"
        for chunk in routed.parsed[0].chunks
        for ev in chunk.evidences
    )


def test_unsupported_format_raises_explicitly(corpus_root):
    doc = _doc(file_format="pdf+html", file_path="raw/periodic/KB금융/20260619000667_annual_2025_12")
    router = ParserRouter(corpus_root)
    with pytest.raises(UnsupportedDocumentError):
        router.route(doc)


def test_multi_file_document_parses_every_xml_as_one_document(corpus_root):
    # 삼성전자 사업보고서 2024.12 has n_files=3 (main + 2 attachments) but is
    # ONE manifest row / ONE document — router must not split it.
    doc = _doc(
        doc_id="periodic_20250311001085", corp_group="periodic", doc_group="periodic",
        doc_subtype="annual", corp_name="삼성전자", rcept_no="20250311001085",
        file_path="raw/periodic/삼성전자/20250311001085_annual_2024_12", n_files=3,
    )
    router = ParserRouter(corpus_root)
    routed = router.route(doc)
    assert routed.doc.doc_id == "periodic_20250311001085"  # still one doc_id
    assert len(routed.parsed) == 3  # one ParsedDocument per XML file inside
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/parsing/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dart_corpus/parsing/router.py`**

```python
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from dart_corpus.contract.paths import list_xml_files, resolve_corpus_path
from dart_corpus.parsing.base import BaseDocumentParser, ParsedDocument
from dart_corpus.parsing.dart_parser import DartDocumentParser
from dart_corpus.parsing.kind_parser import KindXFormsParser

if TYPE_CHECKING:
    from dart_corpus.contract.manifest import DocumentRecord

logger = logging.getLogger(__name__)

EXPECTED_PARSER_BY_GROUP = {
    "major": "dart_document",
    "periodic": "dart_document",
    "holding": "dart_document",
    "exchange": "kind_xforms",
}


class UnsupportedDocumentError(Exception):
    def __init__(self, doc_id: str, file_format: str):
        super().__init__(
            f"{doc_id}: file_format={file_format!r} has no XML parser "
            f"(expected to be recorded as unsupported, not routed)"
        )
        self.doc_id = doc_id
        self.file_format = file_format


@dataclass
class RoutedDocument:
    doc: "DocumentRecord"
    parsed: list[ParsedDocument] = field(default_factory=list)
    router_warnings: list[str] = field(default_factory=list)


class ParserRouter:
    def __init__(self, corpus_root: Path, parsers: list[BaseDocumentParser] | None = None):
        self.corpus_root = Path(corpus_root)
        self.parsers = parsers or [DartDocumentParser(), KindXFormsParser()]

    def route(self, doc: "DocumentRecord") -> RoutedDocument:
        if doc.file_format != "xml":
            raise UnsupportedDocumentError(doc.doc_id, doc.file_format)

        doc_dir = resolve_corpus_path(self.corpus_root, doc.file_path)
        xml_files = list_xml_files(doc_dir)
        if len(xml_files) != doc.n_files:
            logger.warning(
                "doc_id=%s manifest n_files=%d but found %d XML files on disk",
                doc.doc_id, doc.n_files, len(xml_files),
            )

        expected_parser_name = EXPECTED_PARSER_BY_GROUP.get(doc.doc_group)
        router_warnings: list[str] = []
        parsed_docs: list[ParsedDocument] = []

        for xml_path in xml_files:
            parser = self._select_parser(doc, xml_path, expected_parser_name, router_warnings)
            parsed_docs.append(parser.parse(doc, xml_path))

        return RoutedDocument(doc=doc, parsed=parsed_docs, router_warnings=router_warnings)

    def _select_parser(
        self, doc: "DocumentRecord", xml_path: Path,
        expected_parser_name: str | None, router_warnings: list[str],
    ) -> BaseDocumentParser:
        expected = next(
            (p for p in self.parsers if p.name == expected_parser_name), None
        )
        if expected is not None and expected.can_parse(doc, xml_path):
            return expected

        for parser in self.parsers:
            if parser is expected:
                continue
            if parser.can_parse(doc, xml_path):
                msg = (
                    f"doc_group={doc.doc_group!r} expected parser "
                    f"{expected_parser_name!r} but structure matched "
                    f"{parser.name!r} instead ({xml_path.name})"
                )
                logger.warning("doc_id=%s: %s", doc.doc_id, msg)
                router_warnings.append(msg)
                return parser

        msg = f"no parser's can_parse() matched {xml_path.name}"
        logger.warning("doc_id=%s: %s", doc.doc_id, msg)
        router_warnings.append(msg)
        # Fall back to the doc_group's expected parser so the caller still
        # gets a ParsedDocument (with warnings) instead of a crash.
        return expected or self.parsers[0]
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/parsing/test_router.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/dart_corpus/parsing/router.py tests/parsing/test_router.py
git commit -m "feat: ParserRouter dispatching on doc_group with structure-sniffing fallback"
```

---

### Task 8: Fact labels + extractors

**Files:**
- Create: `src/dart_corpus/facts/__init__.py` (empty)
- Create: `src/dart_corpus/facts/labels.py`
- Create: `src/dart_corpus/facts/extractors.py`
- Test: `tests/facts/test_extractors.py`

**Interfaces:**
- Consumes: `RoutedDocument`, `ParsedDocument` (Task 7); `DocumentRecord` (Task 2).
- Produces: `LABEL_ALIASES: dict[str, str]`; `parse_amount_krw(raw: str) -> int | None`; `@dataclass(frozen=True) ExtractedFact(doc_id, fact_type, value, raw_value, evidence_id, chunk_id)`; `extract_facts(routed: RoutedDocument) -> list[ExtractedFact]`.

**Note on labels vs. the original spec list:** the spec's supported-label list includes `정정대상 공시서류의 최초제출일` / `최초제출일` (DART wording). The *actual* label observed in real `exchange`-doc_group corrections (verified on `HD현대일렉트릭/20250225800764`) is **`정정관련 공시서류제출일`** — different wording, same meaning. Since every MVP-scope correction lives in `doc_group=exchange` (KIND format), both wordings are included in `LABEL_ALIASES` so real correction docs actually produce an `original_submission_date` fact. Termination disclosures (`단일판매공급계약해지`) use **`해지금액(원)`**, not `계약금액(원)` (verified on `LG에너지솔루션/20251217800800`) — also not in the spec's literal label list but required for that MVP-scope subtype, so it is included too.

- [ ] **Step 1: Write the failing test**

```python
# tests/facts/test_extractors.py
from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.contract.paths import list_xml_files, resolve_corpus_path
from dart_corpus.facts.extractors import extract_facts, parse_amount_krw
from dart_corpus.parsing.router import ParserRouter


def _doc(**overrides) -> DocumentRecord:
    base = dict(
        doc_id="exchange_20250120800389", corp_code="00108524", corp_name="HD현대일렉트릭",
        listed_name="HD현대일렉트릭", stock_code="267260", industry="산업재",
        sector="전력기기", doc_group="exchange", doc_subtype="신규시설투자등",
        report_nm="신규시설투자등", rcept_no="20250120800389", rcept_dt="20250120",
        flr_nm="HD현대일렉트릭", is_correction=False,
        file_path="raw/exchange/HD현대일렉트릭/20250120800389", file_format="xml", n_files=1,
    )
    base.update(overrides)
    return DocumentRecord(**base)


def test_parse_amount_krw_handles_commas_and_dashes():
    assert parse_amount_krw("211,800,000,000") == 211_800_000_000
    assert parse_amount_krw("-") is None
    assert parse_amount_krw("") is None


def test_investment_amount_fact_from_real_document(corpus_root):
    router = ParserRouter(corpus_root)
    doc = _doc()
    routed = router.route(doc)
    facts = extract_facts(routed)
    amount_facts = [f for f in facts if f.fact_type == "investment_amount_krw"]
    assert len(amount_facts) == 1
    assert amount_facts[0].value == 211_800_000_000
    assert amount_facts[0].doc_id == doc.doc_id
    assert amount_facts[0].evidence_id  # traceable back to a specific cell


def test_termination_amount_uses_해지금액_label(corpus_root):
    doc = _doc(
        doc_id="exchange_20251217800800", corp_name="LG에너지솔루션",
        doc_subtype="단일판매공급계약해지", rcept_no="20251217800800",
        file_path="raw/exchange/LG에너지솔루션/20251217800800",
    )
    router = ParserRouter(corpus_root)
    facts = extract_facts(router.route(doc))
    amount_facts = [f for f in facts if f.fact_type == "termination_amount_krw"]
    assert len(amount_facts) == 1
    assert amount_facts[0].value == 9_603_075_000_000


def test_correction_submission_date_extracted_with_kind_wording(corpus_root):
    doc = _doc(
        doc_id="exchange_20250225800764", corp_name="HD현대일렉트릭",
        doc_subtype="단일판매공급계약체결", rcept_no="20250225800764", is_correction=True,
        file_path="raw/exchange/HD현대일렉트릭/20250225800764",
    )
    router = ParserRouter(corpus_root)
    facts = extract_facts(router.route(doc))
    date_facts = [f for f in facts if f.fact_type == "original_submission_date"]
    assert len(date_facts) == 1
    assert date_facts[0].value == "2024-01-30"
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/facts/test_extractors.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dart_corpus/facts/labels.py`**

```python
from __future__ import annotations

LABEL_ALIASES: dict[str, str] = {
    "투자금액(원)": "investment_amount_krw",
    "투자금액": "investment_amount_krw",
    "계약금액(원)": "contract_amount_krw",
    "계약금액": "contract_amount_krw",
    "해지금액(원)": "termination_amount_krw",
    "해지금액": "termination_amount_krw",
    # DART-schema wording (major/periodic corrections):
    "2. 정정대상 공시서류의 최초제출일 :": "original_submission_date",
    "정정대상 공시서류의 최초제출일": "original_submission_date",
    "최초제출일": "original_submission_date",
    # KIND(거래소) wording — the actual wording observed on real
    # exchange-doc_group corrections, e.g. HD현대일렉트릭/20250225800764:
    "2. 정정관련 공시서류제출일": "original_submission_date",
    "정정관련 공시서류제출일": "original_submission_date",
}

AMOUNT_FACT_TYPES = {"investment_amount_krw", "contract_amount_krw", "termination_amount_krw"}
```

- [ ] **Step 4: Implement `src/dart_corpus/facts/extractors.py`**

```python
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dart_corpus.facts.labels import AMOUNT_FACT_TYPES, LABEL_ALIASES

if TYPE_CHECKING:
    from dart_corpus.parsing.router import RoutedDocument

logger = logging.getLogger(__name__)

_AMOUNT_RE = re.compile(r"-?[\d,]+")
_DATE_RE = re.compile(r"(\d{4})[년\-.](\d{1,2})[월\-.](\d{1,2})")


def parse_amount_krw(raw: str) -> int | None:
    text = raw.strip()
    if text in {"", "-"}:
        return None
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    digits = match.group(0).replace(",", "")
    try:
        return int(digits)
    except ValueError:
        return None


def _normalize_date_text(raw: str) -> str | None:
    match = _DATE_RE.search(raw)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


@dataclass(frozen=True)
class ExtractedFact:
    doc_id: str
    fact_type: str
    value: object
    raw_value: str
    evidence_id: str
    chunk_id: str


def extract_facts(routed: "RoutedDocument") -> list["ExtractedFact"]:
    facts: list[ExtractedFact] = []
    for parsed in routed.parsed:
        for chunk in parsed.chunks:
            for ev in chunk.evidences:
                if ev.label is None:
                    continue
                fact_type = LABEL_ALIASES.get(ev.label.strip())
                if fact_type is None:
                    continue

                if fact_type in AMOUNT_FACT_TYPES:
                    amount = parse_amount_krw(ev.value)
                    if amount is None:
                        logger.warning(
                            "doc_id=%s evidence_id=%s label=%r value=%r "
                            "could not be parsed as an amount",
                            routed.doc.doc_id, ev.evidence_id, ev.label, ev.value,
                        )
                        continue
                    facts.append(
                        ExtractedFact(
                            doc_id=routed.doc.doc_id, fact_type=fact_type,
                            value=amount, raw_value=ev.value,
                            evidence_id=ev.evidence_id, chunk_id=chunk.chunk_id,
                        )
                    )
                elif fact_type == "original_submission_date":
                    normalized = _normalize_date_text(ev.value)
                    if normalized is None:
                        logger.warning(
                            "doc_id=%s evidence_id=%s label=%r value=%r "
                            "could not be parsed as a date",
                            routed.doc.doc_id, ev.evidence_id, ev.label, ev.value,
                        )
                        continue
                    facts.append(
                        ExtractedFact(
                            doc_id=routed.doc.doc_id, fact_type=fact_type,
                            value=normalized, raw_value=ev.value,
                            evidence_id=ev.evidence_id, chunk_id=chunk.chunk_id,
                        )
                    )
    return facts
```

- [ ] **Step 5: Run test, verify pass**

Run: `python -m pytest tests/facts/test_extractors.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/dart_corpus/facts/__init__.py src/dart_corpus/facts/labels.py \
        src/dart_corpus/facts/extractors.py tests/facts/test_extractors.py
git commit -m "feat: amount/date fact extraction with traceable evidence refs"
```

---

### Task 9: `FactStore` + MVP extraction runner script

**Files:**
- Create: `src/dart_corpus/facts/store.py`
- Create: `scripts/run_mvp_extraction.py`
- Test: `tests/facts/test_store.py`

**Interfaces:**
- Consumes: `ExtractedFact` (Task 8); `ManifestLoader`, `DocumentRecord` (Task 2); `ParserRouter`, `UnsupportedDocumentError` (Task 7); `extract_facts` (Task 8).
- Produces: `class FactStore: def __init__(self, output_path: Path); def write(self, facts: list[ExtractedFact]) -> None`. `scripts/run_mvp_extraction.py` — a CLI entry point, not imported by tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/facts/test_store.py
import json

from dart_corpus.facts.extractors import ExtractedFact
from dart_corpus.facts.store import FactStore


def test_writes_one_json_line_per_fact(tmp_path):
    facts = [
        ExtractedFact(
            doc_id="exchange_1", fact_type="investment_amount_krw", value=100,
            raw_value="100", evidence_id="e1", chunk_id="c1",
        ),
        ExtractedFact(
            doc_id="exchange_2", fact_type="contract_amount_krw", value=200,
            raw_value="200", evidence_id="e2", chunk_id="c2",
        ),
    ]
    out = tmp_path / "facts.jsonl"
    FactStore(out).write(facts)

    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["doc_id"] == "exchange_1"
    assert first["value"] == 100
```

- [ ] **Step 2: Run test, verify failure**

Run: `python -m pytest tests/facts/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dart_corpus/facts/store.py`**

```python
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dart_corpus.facts.extractors import ExtractedFact


class FactStore:
    def __init__(self, output_path: str | Path):
        self.output_path = Path(output_path)

    def write(self, facts: list["ExtractedFact"]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            for fact in facts:
                f.write(json.dumps(asdict(fact), ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/facts/test_store.py -v`
Expected: 1 passed

- [ ] **Step 5: Implement `scripts/run_mvp_extraction.py`**

```python
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dart_corpus.config import default_corpus_root  # noqa: E402
from dart_corpus.contract.manifest import ManifestLoader  # noqa: E402
from dart_corpus.facts.extractors import extract_facts  # noqa: E402
from dart_corpus.facts.store import FactStore  # noqa: E402
from dart_corpus.parsing.router import ParserRouter, UnsupportedDocumentError  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("run_mvp_extraction")

MVP_DOC_SUBTYPES = {"신규시설투자등", "단일판매공급계약체결", "단일판매공급계약해지"}


def main() -> None:
    corpus_root = default_corpus_root()
    docs = ManifestLoader(corpus_root).load()
    mvp_docs = [
        d for d in docs if d.doc_group == "exchange" and d.doc_subtype in MVP_DOC_SUBTYPES
    ]
    logger.info("MVP scope: %d documents", len(mvp_docs))

    router = ParserRouter(corpus_root)
    all_facts = []
    errors: list[dict] = []

    for doc in mvp_docs:
        try:
            routed = router.route(doc)
        except UnsupportedDocumentError as exc:
            errors.append({"doc_id": doc.doc_id, "stage": "route", "error": str(exc)})
            logger.error("doc_id=%s route failed: %s", doc.doc_id, exc)
            continue

        for w in routed.router_warnings:
            errors.append({"doc_id": doc.doc_id, "stage": "router_warning", "error": w})
        for parsed in routed.parsed:
            for w in parsed.warnings:
                errors.append({"doc_id": doc.doc_id, "stage": "parse_warning", "error": w.message})

        all_facts.extend(extract_facts(routed))

    output_dir = Path(__file__).resolve().parents[1] / "output"
    FactStore(output_dir / "mvp_facts.jsonl").write(all_facts)

    import json
    with open(output_dir / "mvp_errors.jsonl", "w", encoding="utf-8") as f:
        for err in errors:
            f.write(json.dumps(err, ensure_ascii=False) + "\n")

    logger.info("wrote %d facts, %d error/warning entries", len(all_facts), len(errors))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add src/dart_corpus/facts/store.py scripts/run_mvp_extraction.py tests/facts/test_store.py
git commit -m "feat: FactStore writer and MVP extraction runner script"
```

---

### Task 10: `CorrectionResolver`

**Files:**
- Create: `src/dart_corpus/corrections/__init__.py` (empty)
- Create: `src/dart_corpus/corrections/models.py`
- Create: `src/dart_corpus/corrections/resolver.py`
- Test: `tests/corrections/test_resolver.py`

**Interfaces:**
- Consumes: `DocumentRecord` (Task 2).
- Produces: `class LinkStatus(str, Enum): RESOLVED = "resolved"; PROBABLE = "probable"; AMBIGUOUS = "ambiguous"; UNRESOLVED = "unresolved"; MANUALLY_RESOLVED = "manually_resolved"`; `@dataclass(frozen=True) CorrectionLink(correction_doc_id, original_doc_id: str | None, status: LinkStatus, candidates: tuple[str, ...], reason: str)`; `normalize_date_text(text: str) -> str | None`; `class CorrectionResolver: def __init__(self, all_docs: list[DocumentRecord], manual_overrides: dict[str, str] | None = None); def resolve(self, correction_doc: DocumentRecord, submission_date_text: str | None) -> CorrectionLink`.

**Real fixture used to validate this** (verified during research): correction `exchange_20250225800764` (HD현대일렉트릭, `단일판매공급계약체결`, submission-date text `"2024-01-30"`) has exactly one non-correction candidate matching corp+subtype+date in the real manifest: `exchange_20240130800387` (same corp, same doc_subtype, `rcept_dt="20240130"`). This is the `resolved` test case; only one candidate exists for this fixture in the real corpus, so `ambiguous` is exercised with synthetic fixtures instead.

**Explicitly out of scope for v1** (do not implement fuzzy matching to fill this in): `PROBABLE` is reserved for a future heuristic (e.g. contract-name or investment-name similarity when date matching alone is inconclusive). `resolve()` in this task only ever returns `resolved`, `ambiguous`, `unresolved`, or `manually_resolved` — never fabricate a `probable` result just to exercise the enum value.

- [ ] **Step 1: Write the failing tests**

```python
# tests/corrections/test_resolver.py
from dart_corpus.contract.manifest import DocumentRecord
from dart_corpus.corrections.models import LinkStatus
from dart_corpus.corrections.resolver import CorrectionResolver, normalize_date_text


def _doc(**overrides) -> DocumentRecord:
    base = dict(
        doc_id="exchange_0", corp_code="00108524", corp_name="HD현대일렉트릭",
        listed_name="HD현대일렉트릭", stock_code="267260", industry="산업재",
        sector="전력기기", doc_group="exchange", doc_subtype="단일판매공급계약체결",
        report_nm="단일판매ㆍ공급계약체결", rcept_no="0", rcept_dt="20240130",
        flr_nm="HD현대일렉트릭", is_correction=False,
        file_path="raw/exchange/HD현대일렉트릭/0", file_format="xml", n_files=1,
    )
    base.update(overrides)
    return DocumentRecord(**base)


def test_normalize_date_text_handles_both_wordings():
    assert normalize_date_text("2024-01-30") == "20240130"
    assert normalize_date_text("2023년 10월 24일") == "20231024"
    assert normalize_date_text("garbage") is None


def test_resolves_unique_candidate_real_fixture(corpus_root):
    from dart_corpus.contract.manifest import ManifestLoader

    all_docs = ManifestLoader(corpus_root).load()
    resolver = CorrectionResolver(all_docs)
    correction = next(d for d in all_docs if d.doc_id == "exchange_20250225800764")

    link = resolver.resolve(correction, submission_date_text="2024-01-30")
    assert link.status == LinkStatus.RESOLVED
    assert link.original_doc_id == "exchange_20240130800387"


def test_ambiguous_when_multiple_originals_match():
    original_a = _doc(doc_id="exchange_a", rcept_no="a")
    original_b = _doc(doc_id="exchange_b", rcept_no="b")
    correction = _doc(doc_id="exchange_c", rcept_no="c", is_correction=True)
    resolver = CorrectionResolver([original_a, original_b, correction])

    link = resolver.resolve(correction, submission_date_text="2024-01-30")
    assert link.status == LinkStatus.AMBIGUOUS
    assert link.original_doc_id is None
    assert set(link.candidates) == {"exchange_a", "exchange_b"}


def test_unresolved_when_no_date_text():
    correction = _doc(doc_id="exchange_c", is_correction=True)
    resolver = CorrectionResolver([correction])
    link = resolver.resolve(correction, submission_date_text=None)
    assert link.status == LinkStatus.UNRESOLVED
    assert link.original_doc_id is None


def test_manual_override_wins_and_is_traceable():
    correction = _doc(doc_id="exchange_c", is_correction=True)
    resolver = CorrectionResolver([correction], manual_overrides={"exchange_c": "exchange_original"})
    link = resolver.resolve(correction, submission_date_text="not even a date")
    assert link.status == LinkStatus.MANUALLY_RESOLVED
    assert link.original_doc_id == "exchange_original"
```

- [ ] **Step 2: Run tests, verify failure**

Run: `python -m pytest tests/corrections/test_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/dart_corpus/corrections/models.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LinkStatus(str, Enum):
    RESOLVED = "resolved"
    PROBABLE = "probable"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    MANUALLY_RESOLVED = "manually_resolved"


@dataclass(frozen=True)
class CorrectionLink:
    correction_doc_id: str
    original_doc_id: str | None
    status: LinkStatus
    candidates: tuple[str, ...]
    reason: str
```

- [ ] **Step 4: Implement `src/dart_corpus/corrections/resolver.py`**

```python
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dart_corpus.corrections.models import CorrectionLink, LinkStatus

if TYPE_CHECKING:
    from dart_corpus.contract.manifest import DocumentRecord

_DATE_RE = re.compile(r"(\d{4})[년\-.](\d{1,2})[월\-.](\d{1,2})")


def normalize_date_text(text: str) -> str | None:
    match = _DATE_RE.search(text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}{int(month):02d}{int(day):02d}"


class CorrectionResolver:
    """Best-effort candidate matcher from a [기재정정] document back to its
    original — never forces a link. Matches on (corp_code, doc_subtype,
    rcept_dt-equals-extracted-submission-date) among non-correction
    documents only. A unique match is `resolved`; more than one is
    `ambiguous` (never arbitrarily picked); none is `unresolved`.
    `manually_resolved` is a human-provided override, checked first.
    """

    def __init__(
        self,
        all_docs: list["DocumentRecord"],
        manual_overrides: dict[str, str] | None = None,
    ):
        self._manual = manual_overrides or {}
        self._by_key: dict[tuple[str, str], list["DocumentRecord"]] = {}
        for doc in all_docs:
            if doc.is_correction:
                continue
            key = (doc.corp_code, doc.doc_subtype)
            self._by_key.setdefault(key, []).append(doc)

    def resolve(
        self, correction_doc: "DocumentRecord", submission_date_text: str | None
    ) -> CorrectionLink:
        if correction_doc.doc_id in self._manual:
            target = self._manual[correction_doc.doc_id]
            return CorrectionLink(
                correction_doc_id=correction_doc.doc_id, original_doc_id=target,
                status=LinkStatus.MANUALLY_RESOLVED, candidates=(target,),
                reason="manual override",
            )

        if not submission_date_text:
            return CorrectionLink(
                correction_doc_id=correction_doc.doc_id, original_doc_id=None,
                status=LinkStatus.UNRESOLVED, candidates=(),
                reason="no original-submission-date text available",
            )

        normalized = normalize_date_text(submission_date_text)
        if normalized is None:
            return CorrectionLink(
                correction_doc_id=correction_doc.doc_id, original_doc_id=None,
                status=LinkStatus.UNRESOLVED, candidates=(),
                reason=f"could not parse date from {submission_date_text!r}",
            )

        key = (correction_doc.corp_code, correction_doc.doc_subtype)
        pool = self._by_key.get(key, [])
        candidates = [d for d in pool if d.rcept_dt == normalized]

        if len(candidates) == 1:
            return CorrectionLink(
                correction_doc_id=correction_doc.doc_id,
                original_doc_id=candidates[0].doc_id,
                status=LinkStatus.RESOLVED,
                candidates=(candidates[0].doc_id,),
                reason="unique match on corp_code + doc_subtype + rcept_dt",
            )
        if len(candidates) > 1:
            return CorrectionLink(
                correction_doc_id=correction_doc.doc_id, original_doc_id=None,
                status=LinkStatus.AMBIGUOUS,
                candidates=tuple(d.doc_id for d in candidates),
                reason="multiple originals share corp_code + doc_subtype + rcept_dt",
            )
        return CorrectionLink(
            correction_doc_id=correction_doc.doc_id, original_doc_id=None,
            status=LinkStatus.UNRESOLVED, candidates=(),
            reason="no original found matching corp_code + doc_subtype + rcept_dt",
        )
```

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/corrections/test_resolver.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/dart_corpus/corrections/__init__.py src/dart_corpus/corrections/models.py \
        src/dart_corpus/corrections/resolver.py tests/corrections/test_resolver.py
git commit -m "feat: CorrectionResolver with never-forced candidate matching"
```

---

### Task 11: End-to-end integration test over the full MVP scope

**Files:**
- Test: `tests/test_integration_mvp.py`
- Modify: `scripts/run_mvp_extraction.py:1-70` — add correction-link output alongside facts (extend `main()`)

**Interfaces:**
- Consumes: everything from Tasks 1–10.
- Produces: nothing new — this task is a real-corpus smoke test plus wiring the resolver into the runner script.

- [ ] **Step 1: Extend `scripts/run_mvp_extraction.py` to also resolve corrections**

Add after the `all_facts.extend(extract_facts(routed))` line inside the loop in `main()`:

```python
    from dart_corpus.corrections.resolver import CorrectionResolver

    resolver = CorrectionResolver(docs)
    correction_links = []
    for doc in mvp_docs:
        if not doc.is_correction:
            continue
        routed = router.route(doc)
        facts = extract_facts(routed)
        date_fact = next((f for f in facts if f.fact_type == "original_submission_date"), None)
        link = resolver.resolve(doc, date_fact.value if date_fact else None)
        correction_links.append(link)

    import json as _json
    with open(output_dir / "mvp_correction_links.jsonl", "w", encoding="utf-8") as f:
        for link in correction_links:
            f.write(_json.dumps(
                {
                    "correction_doc_id": link.correction_doc_id,
                    "original_doc_id": link.original_doc_id,
                    "status": link.status.value,
                    "candidates": list(link.candidates),
                    "reason": link.reason,
                },
                ensure_ascii=False,
            ) + "\n")
    logger.info("resolved %d correction links", len(correction_links))
```

(This re-routes correction docs a second time rather than caching the first pass's `RoutedDocument` — acceptable for the MVP script's ~600-document correction subset; do not over-engineer caching here unless the runtime becomes a real problem.)

- [ ] **Step 2: Write the integration test**

```python
# tests/test_integration_mvp.py
import pytest

from dart_corpus.contract.manifest import ManifestLoader
from dart_corpus.corrections.resolver import CorrectionResolver
from dart_corpus.facts.extractors import extract_facts
from dart_corpus.parsing.router import ParserRouter, UnsupportedDocumentError

MVP_DOC_SUBTYPES = {"신규시설투자등", "단일판매공급계약체결", "단일판매공급계약해지"}
FACT_TYPE_BY_SUBTYPE = {
    "신규시설투자등": "investment_amount_krw",
    "단일판매공급계약체결": "contract_amount_krw",
    "단일판매공급계약해지": "termination_amount_krw",
}


@pytest.mark.integration
def test_mvp_scope_is_exactly_1169_documents(corpus_root):
    docs = ManifestLoader(corpus_root).load()
    mvp_docs = [d for d in docs if d.doc_group == "exchange" and d.doc_subtype in MVP_DOC_SUBTYPES]
    assert len(mvp_docs) == 1169


@pytest.mark.integration
def test_every_mvp_document_routes_without_crashing(corpus_root):
    docs = ManifestLoader(corpus_root).load()
    mvp_docs = [d for d in docs if d.doc_group == "exchange" and d.doc_subtype in MVP_DOC_SUBTYPES]
    router = ParserRouter(corpus_root)

    routing_failures = []
    for doc in mvp_docs:
        try:
            router.route(doc)
        except UnsupportedDocumentError as exc:
            routing_failures.append((doc.doc_id, str(exc)))

    # every MVP-scope doc is file_format=xml per the manifest (verified
    # during research) — a routing failure here means the manifest or the
    # corpus changed underneath this plan, not an expected outcome.
    assert routing_failures == []


@pytest.mark.integration
def test_amount_extraction_rate_meets_poc_bar(corpus_root):
    docs = ManifestLoader(corpus_root).load()
    mvp_docs = [
        d for d in docs
        if d.doc_group == "exchange" and d.doc_subtype in MVP_DOC_SUBTYPES and not d.is_correction
    ]
    router = ParserRouter(corpus_root)

    counts = {subtype: [0, 0] for subtype in MVP_DOC_SUBTYPES}  # [extracted, total]
    for doc in mvp_docs:
        routed = router.route(doc)
        facts = extract_facts(routed)
        wanted_fact_type = FACT_TYPE_BY_SUBTYPE[doc.doc_subtype]
        counts[doc.doc_subtype][1] += 1
        if any(f.fact_type == wanted_fact_type for f in facts):
            counts[doc.doc_subtype][0] += 1

    for subtype, (extracted, total) in counts.items():
        rate = extracted / total if total else 0.0
        assert rate >= 0.95, f"{subtype}: only {extracted}/{total} extracted amount ({rate:.1%})"


@pytest.mark.integration
def test_correction_resolver_covers_every_correction_without_crashing(corpus_root):
    docs = ManifestLoader(corpus_root).load()
    mvp_docs = [d for d in docs if d.doc_group == "exchange" and d.doc_subtype in MVP_DOC_SUBTYPES]
    corrections = [d for d in mvp_docs if d.is_correction]
    router = ParserRouter(corpus_root)
    resolver = CorrectionResolver(docs)

    from collections import Counter
    status_counts: Counter = Counter()
    for doc in corrections:
        routed = router.route(doc)
        facts = extract_facts(routed)
        date_fact = next((f for f in facts if f.fact_type == "original_submission_date"), None)
        link = resolver.resolve(doc, date_fact.value if date_fact else None)
        status_counts[link.status] += 1

    assert sum(status_counts.values()) == len(corrections)
    # Never silently drop unresolved/ambiguous — this assertion documents
    # the real distribution so a reviewer sees it in CI output.
    print(f"correction link status distribution: {dict(status_counts)}")
```

- [ ] **Step 3: Run the integration suite, verify pass**

Run: `python -m pytest tests/test_integration_mvp.py -v -m integration -s`
Expected: 4 passed. This runs against the real 1,169-document MVP scope and will take noticeably longer than the unit suites (each test parses hundreds of real XML files) — that is expected for an integration test and is why it carries the `integration` marker instead of running by default.

If `test_amount_extraction_rate_meets_poc_bar` fails below 95% for any subtype, do not lower the threshold to make it pass — inspect `output/mvp_errors.jsonl` (run `python scripts/run_mvp_extraction.py` first) for the specific `doc_id`s that produced no fact, open those documents' XML directly, and extend `LABEL_ALIASES` (Task 8) or the KIND row-parsing heuristic (Task 5) for the newly observed pattern.

- [ ] **Step 4: Run the full fast suite (excluding integration) to confirm nothing regressed**

Run: `python -m pytest tests/ -v -m "not integration"`
Expected: all unit tests from Tasks 1–10 still pass.

- [ ] **Step 5: Run the MVP extraction script end-to-end and inspect output**

Run: `python scripts/run_mvp_extraction.py`
Expected: log line `wrote <N> facts, <M> error/warning entries` and `resolved <K> correction links`; `output/mvp_facts.jsonl`, `output/mvp_errors.jsonl`, `output/mvp_correction_links.jsonl` exist and are non-empty.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_mvp_extraction.py tests/test_integration_mvp.py
git commit -m "test: end-to-end MVP integration coverage over the real 1,169-document scope"
```

---

## Self-Review

**Spec coverage:**
- 대상 기업/기간/문서 수 → asserted directly in Task 2 tests (70 companies, 4204 docs, MVP subtype counts).
- `corp_code`/`stock_code` string dtype → `CompanyRecord`/`DocumentRecord` fields typed `str`, tested (Task 2).
- 공식 문서 식별 필드 전체 → `DocumentRecord` carries every field from the spec's list (Task 2).
- `doc_id` reuse, no new IDs → `ManifestLoader` never generates an ID; `doc_id` flows through unchanged (Tasks 2, 7–10).
- Chunk/근거 ID reproducibility → `make_chunk_id`/`make_evidence_id`, tested for determinism (Task 4).
- `raw/` 디렉터리 구조 (`periodic`/`major`/`exchange`/`holding`) → `EXPECTED_PARSER_BY_GROUP` covers all four (Task 7).
- 하나의 manifest 행 = 문서 하나, 폴더 내 다중 XML 분리 금지 → `RoutedDocument.parsed` is a list keyed to one `doc_id`, tested explicitly (Task 7, `test_multi_file_document_parses_every_xml_as_one_document`).
- `file_format=xml` only parsed, `pdf+html` explicitly flagged not silently skipped → `ManifestLoader.unsupported()` + `UnsupportedDocumentError` (Tasks 2, 7).
- Parser 선택 규칙 (doc_group 우선, 구조 검사, 불일치시 실제 구조 우선 + warning, 단일 정규식/파서 금지) → `ParserRouter._select_parser` (Task 7).
- 최소 Parser 구조 (Base/Dart/Kind/Router) → Tasks 4–7.
- 기업명 정규화, 예외 별칭, 충돌시 임의 선택 금지 → `CorpAliasIndex` + `AmbiguousAliasError` (Task 3).
- 정정공시 제약 (`ord_rcept_no` 없음, 강제 연결 금지, 5개 상태) → `CorrectionResolver`, `LinkStatus` enum with all 5 values represented in code even though v1 never emits `probable` (Task 10, documented limitation).
- 초기 MVP 범위 (43/1106/20 + 정정) → `MVP_DOC_SUBTYPES` in the runner script and integration test (Tasks 9, 11).
- PoC 결과 재현 (5/5, 5/5) → `KindXFormsParser` tests reproduce the exact PoC fixtures (Task 5).
- KIND 라벨 셀 → 값 셀 탐색, td 속성/colspan/rowspan 비고정 → "last cell = value" heuristic, not attribute-based (Task 5).
- 주요 라벨 목록 지원 → `LABEL_ALIASES` (Task 8) — includes two labels *not* in the spec's literal list (해지금액, 정정관련 공시서류제출일) because real data required them; called out explicitly rather than silently deviating.
- 데이터 기간 처리 (2026-03-31 이후 질문 처리) → **not covered by this plan** — that is a query/answering-layer concern with no code surface yet (no chatbot/API exists). Flagged here explicitly rather than silently omitted; belongs in a future plan once a query layer exists.
- `market_cap` 시점 주의 → **not covered by this plan** — same reasoning; no code currently surfaces `market_cap` in an answer. Worth a code comment on `CompanyRecord.market_cap` when a future consumer reads it.
- manifest as source of truth, no raw/ rglob → `ManifestLoader`/`ParserRouter` only ever open paths derived from manifest `file_path` (Tasks 2, 7).
- 금액/계산은 Python → `parse_amount_krw`, `_normalize_date_text` (Task 8); no LLM call anywhere in this plan.
- 모든 추출값 파일/표/행/셀까지 역추적 → `Evidence.evidence_id` embeds doc_id + rel_path + section_path + table index + row/col (Task 4, used throughout).
- 불확실한 정정 체인 자동 확정 금지 → `CorrectionResolver` never auto-picks among ambiguous candidates (Task 10, tested).
- 오류 조용히 무시 금지 → every warning path uses `logging.warning`/`logging.error` plus, where applicable, populates `ParsedDocument.warnings` / `RoutedDocument.router_warnings` / the runner script's `mvp_errors.jsonl` (Tasks 2, 5–9, 11).

**Two spec items are explicitly out of scope for this plan** (both flagged above rather than silently dropped): the 2026-03-31 period-boundary answer-guardrail and the `market_cap`-is-not-point-in-time guardrail. Both are answer-generation-layer concerns; this plan builds the extraction/fact layer they would sit on top of. Recommend a follow-up plan once a query/answer layer is scoped.

**Placeholder scan:** no `TODO`/`TBD`/"add appropriate error handling" strings appear in any task; every code block is complete, runnable code; every test has real assertions against either real corpus fixtures or explicit synthetic fixtures.

**Type consistency:** `DocumentRecord`, `ParsedDocument`/`Chunk`/`Evidence`/`ParserWarning`, `RoutedDocument`, `ExtractedFact`, `CorrectionLink`/`LinkStatus` are each defined exactly once (Tasks 2, 4, 7, 8, 10 respectively) and imported (never redefined) by every later task that uses them.
