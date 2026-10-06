"""SQLite persistence for application state (sources, evidence, runs).

Rows store the canonical Pydantic models as JSON. This store is the system's own
bookkeeping; it is not a data source the pipeline answers questions from.
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Field, SQLModel, create_engine

from evidence_compiler.core.models import utcnow


class SourceRow(SQLModel, table=True):
    __tablename__ = "sources"
    id: str = Field(primary_key=True)
    kind: str
    name: str
    data: str  # Source JSON
    schema_cards: str = "[]"
    pages: str = "{}"
    secret: str | None = None  # connection string; never serialized to API responses
    created_at: datetime = Field(default_factory=utcnow)


class EvidenceRow(SQLModel, table=True):
    __tablename__ = "evidence"
    id: str = Field(primary_key=True)
    source_id: str = Field(index=True)
    data: str
    run_minted: bool = False  # minted at question time (SQL rows, calculations)


class RunRow(SQLModel, table=True):
    __tablename__ = "runs"
    id: str = Field(primary_key=True)
    question: str
    status: str
    error: str | None = None
    events: str = "[]"
    answer: str | None = None
    usage: str | None = None  # JSON: token totals + model-call log
    created_at: datetime = Field(default_factory=utcnow, index=True)


def make_engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    _migrate(engine)
    return engine


def _migrate(engine: Engine) -> None:
    """Add columns introduced after a database was created (SQLite has no auto-migrate)."""
    from sqlalchemy import inspect, text

    added = {"runs": {"usage": "TEXT"}}
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in added.items():
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
