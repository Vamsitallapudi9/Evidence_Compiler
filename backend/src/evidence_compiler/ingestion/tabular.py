"""CSV / Excel connector.

Tables are loaded into the local DuckDB store and described by schema cards. Their
rows become evidence only when a validated query reads them, so every number cited
from a table carries the exact SQL that produced it.
"""

import re
from pathlib import Path

import pandas as pd

from evidence_compiler.core.ids import content_id, file_hash
from evidence_compiler.core.models import Source, SourceKind
from evidence_compiler.ingestion.base import IngestionError, IngestResult, SchemaCard
from evidence_compiler.sql.duckdb_store import TabularStore


def table_name(*parts: str) -> str:
    name = "_".join(re.sub(r"[^0-9a-zA-Z]+", "_", p).strip("_").lower() for p in parts if p)
    if not name or not name[0].isalpha():
        name = f"t_{name}"
    return name[:63]


def _jsonable(v: object) -> object:
    if pd.isna(v):  # type: ignore[arg-type]
        return None
    if hasattr(v, "item"):
        return v.item()  # numpy scalar → python
    return v if isinstance(v, int | float | str | bool) else str(v)


class TabularConnector:
    def __init__(self, store: TabularStore):
        self.store = store

    def ingest(self, path: Path, *, name: str) -> IngestResult:
        data = path.read_bytes()
        suffix = path.suffix.lower()
        kind = SourceKind.CSV if suffix == ".csv" else SourceKind.XLSX
        try:
            if kind == SourceKind.CSV:
                frames = {"": pd.read_csv(path)}
            else:
                frames = pd.read_excel(path, sheet_name=None)
        except Exception as exc:  # pandas raises many parser-specific errors
            raise IngestionError(f"could not parse {suffix} file: {exc}") from exc

        source_id = content_id("src", kind.value, file_hash(data))
        source = Source(
            id=source_id, kind=kind, name=name, uri=str(path), content_hash=file_hash(data)
        )
        result = IngestResult(source=source)
        stem = Path(name).stem
        tables: list[str] = []
        for sheet, df in frames.items():
            if df.empty:
                continue
            df = df.rename(columns=lambda c: table_name(str(c)))
            tname = table_name(stem) if len(frames) == 1 else table_name(stem, str(sheet))
            self.store.replace_table(tname, df, source_id)
            tables.append(tname)
            result.schema_cards.append(
                SchemaCard(
                    source_id=source_id,
                    target="tabular",
                    engine="duckdb",
                    table=tname,
                    columns=[(c, str(t)) for c, t in df.dtypes.items()],
                    row_count=len(df),
                    sample_rows=[
                        {k: _jsonable(v) for k, v in row.items()}
                        for row in df.head(3).to_dict(orient="records")
                    ],
                    origin=name if not sheet else f"sheet '{sheet}' of {name}",
                )
            )
        if not tables:
            raise IngestionError("file contains no non-empty tables")
        source.metadata["tables"] = tables
        return result
