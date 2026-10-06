"""Local DuckDB store holding tables loaded from CSV / Excel sources.

Writes use a short-lived read-write connection. Queries always use a fresh
connection opened ``read_only`` with external access disabled, so even a query that
slipped past validation could neither modify data nor read arbitrary files.
"""

import threading
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


class TabularStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def replace_table(self, name: str, df: pd.DataFrame, source_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, duckdb.connect(str(self.path)) as con:
            con.register("__ec_incoming", df)
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM __ec_incoming')
            con.unregister("__ec_incoming")

    def drop_tables(self, names: list[str]) -> None:
        if not self.path.exists():
            return
        with self._lock, duckdb.connect(str(self.path)) as con:
            for name in names:
                con.execute(f'DROP TABLE IF EXISTS "{name}"')

    def query(self, sql: str, max_rows: int) -> tuple[list[str], list[tuple[Any, ...]]]:
        if not self.path.exists():
            raise RuntimeError("no tabular sources have been ingested")
        with (
            self._lock,
            duckdb.connect(
                str(self.path),
                read_only=True,
                config={"enable_external_access": False, "lock_configuration": True},
            ) as con,
        ):
            cur = con.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows)
        return columns, rows
