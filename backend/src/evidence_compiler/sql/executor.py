"""Read-only execution of validated SQL; result rows become evidence.

A row read directly from a table is PRIMARY evidence. A row produced by aggregation
(SUM, GROUP BY, …) is DERIVED evidence whose provenance is the query itself plus the
source tables it read. Either way the exact SQL is preserved in the location.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import sql as pgsql

from evidence_compiler.core.ids import content_id
from evidence_compiler.core.models import (
    Creator,
    EvidenceItem,
    EvidenceOrigin,
    QueryLocation,
    utcnow,
)
from evidence_compiler.core.numbers import json_number
from evidence_compiler.ingestion.base import SchemaCard
from evidence_compiler.sql.duckdb_store import TabularStore
from evidence_compiler.sql.validator import SqlValidationError, ValidatedQuery, validate_sql


class SqlExecutionError(RuntimeError):
    pass


@dataclass
class QueryResult:
    target: str
    query: ValidatedQuery
    columns: list[str]
    evidence: list[EvidenceItem]


def infer_unit(column: str) -> str | None:
    c = column.lower()
    if re.search(r"(_usd|usd_|revenue|amount|sales|price|cost|arr|mrr)", c):
        return "USD"
    if re.search(r"(_pct|percent|_share|_rate)$", c):
        return "%"
    return None


def _scalar(v: Any) -> Any:
    if v is None or isinstance(v, bool | int | float | str):
        return v
    if isinstance(v, Decimal):
        return json_number(v)
    if isinstance(v, datetime | date):
        return v.isoformat()
    return str(v)


class SqlExecutor:
    def __init__(
        self,
        tabular: TabularStore,
        secret_lookup: Callable[[str], str | None],
        *,
        max_rows: int = 200,
        timeout_ms: int = 5000,
    ):
        self.tabular = tabular
        self.secret_lookup = secret_lookup
        self.max_rows = max_rows
        self.timeout_ms = timeout_ms

    def run(self, target: str, sql: str, cards: list[SchemaCard], purpose: str = "") -> QueryResult:
        cards = [c for c in cards if c.target == target]
        if not cards:
            raise SqlValidationError(f"unknown query target '{target}'")
        engine = cards[0].engine
        table_sources = {c.table.lower(): c.source_id for c in cards}
        schemas = {c.schema for c in cards if c.schema}
        validated = validate_sql(
            sql,
            dialect="duckdb" if engine == "duckdb" else "postgres",
            allowed_tables=set(table_sources),
            max_rows=self.max_rows,
            allowed_schemas=schemas,
        )
        try:
            if engine == "duckdb":
                columns, rows = self.tabular.query(validated.sql, self.max_rows)
            else:
                columns, rows = self._run_postgres(target, validated.sql, cards[0].schema)
        except Exception as exc:  # driver errors vary widely between duckdb and psycopg
            raise SqlExecutionError(f"query failed: {exc}") from exc

        executed_at = utcnow()
        source_ids = sorted({table_sources[t] for t in validated.tables})
        origin = EvidenceOrigin.DERIVED if validated.is_aggregate else EvidenceOrigin.PRIMARY
        units = {c: u for c in columns if (u := infer_unit(c))}
        evidence: list[EvidenceItem] = []
        for i, row in enumerate(rows):
            fields = {c: _scalar(v) for c, v in zip(columns, row, strict=True)}
            text = f"[{', '.join(validated.tables)}] " + "; ".join(
                f"{k} = {v}" for k, v in fields.items()
            )
            loc = QueryLocation(
                engine=engine,
                sql=validated.sql,
                tables=validated.tables,
                executed_at=executed_at,
                row_count=len(rows),
                row_index=i,
            )
            evidence.append(
                EvidenceItem(
                    id=content_id("ev", "sql", target, validated.sql, i, fields),
                    source_ids=source_ids,
                    origin=origin,
                    creator=Creator.SQL,
                    text=text,
                    fields=fields,
                    location=loc,
                    metadata={"units": units, "target": target, "purpose": purpose},
                )
            )
        return QueryResult(target=target, query=validated, columns=columns, evidence=evidence)

    def _run_postgres(
        self, source_id: str, sql: str, schema: str | None
    ) -> tuple[list[str], list[tuple]]:
        dsn = self.secret_lookup(source_id)
        if not dsn:
            raise SqlExecutionError(f"no connection configured for source {source_id}")
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(
                    pgsql.SQL("SET LOCAL statement_timeout = {}").format(
                        pgsql.Literal(f"{self.timeout_ms}ms")
                    )
                )
                if schema:
                    cur.execute(
                        pgsql.SQL("SET LOCAL search_path = {}").format(pgsql.Identifier(schema))
                    )
                cur.execute(sql)
                columns = [d.name for d in cur.description or []]
                rows = cur.fetchmany(self.max_rows)
            conn.rollback()
        return columns, rows
