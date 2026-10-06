"""Connector interface. Connectors are the only producers of PRIMARY evidence."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from evidence_compiler.core.models import EvidenceItem, Source


class IngestionError(ValueError):
    pass


MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


def check_zip_container(data: bytes) -> None:
    """Refuse zip bombs before parsing .xlsx / .docx (both are zip archives)."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            total = sum(i.file_size for i in zf.infolist())
    except zipfile.BadZipFile as exc:
        raise IngestionError("file is not a valid Office document (bad zip container)") from exc
    if total > MAX_UNCOMPRESSED_BYTES or (data and total / len(data) > MAX_COMPRESSION_RATIO):
        raise IngestionError("document expands to an unsafe size when decompressed")


@dataclass
class SchemaCard:
    """A description of a queryable table, used for retrieval and SQL generation."""

    source_id: str
    target: str  # "tabular" (DuckDB) or a postgres source id
    engine: Literal["duckdb", "postgres"]
    table: str
    columns: list[tuple[str, str]]
    row_count: int
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    schema: str | None = None  # postgres schema
    origin: str = ""  # e.g. "regional_sales.csv" or "sheet 'Segments' of customers.xlsx"

    def to_text(self) -> str:
        cols = ", ".join(f"{n} {t}" for n, t in self.columns)
        lines = [
            f"TABLE {self.table} (target={self.target}, engine={self.engine}, "
            f"rows={self.row_count}, from {self.origin})",
            f"  columns: {cols}",
        ]
        for row in self.sample_rows[:3]:
            lines.append("  sample: " + ", ".join(f"{k}={v}" for k, v in row.items()))
        return "\n".join(lines)


@dataclass
class IngestResult:
    source: Source
    evidence: list[EvidenceItem] = field(default_factory=list)
    schema_cards: list[SchemaCard] = field(default_factory=list)
    pages: dict[int, str] = field(default_factory=dict)  # canonical page text (PDF)
    secret: str | None = None  # e.g. a DSN; stored separately, never returned by the API


class Connector(Protocol):
    def ingest(self, path: Path, *, name: str) -> IngestResult: ...
