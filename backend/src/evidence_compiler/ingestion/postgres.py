"""PostgreSQL connector: registers a database as a queryable source.

Nothing is copied. The connector introspects the schema to build schema cards;
evidence is produced only by validated, read-only queries at question time.
"""

import re

import psycopg
from psycopg import sql as pgsql

from evidence_compiler.core.ids import content_id
from evidence_compiler.core.models import Source, SourceKind
from evidence_compiler.ingestion.base import IngestionError, IngestResult, SchemaCard


def redact_dsn(dsn: str) -> str:
    dsn = re.sub(r"(://[^:/@]+:)[^@]+@", r"\1***@", dsn)
    return re.sub(r"(password\s*=\s*)\S+", r"\1***", dsn, flags=re.IGNORECASE)


class PostgresConnector:
    def register(self, dsn: str, *, name: str, schema: str = "public") -> IngestResult:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise IngestionError("invalid schema name")
        try:
            conn = psycopg.connect(dsn, connect_timeout=5, autocommit=False)
        except psycopg.Error as exc:
            raise IngestionError(f"could not connect: {exc}") from exc
        source_id = content_id("src", "postgres", redact_dsn(dsn), schema)
        source = Source(
            id=source_id,
            kind=SourceKind.POSTGRES,
            name=name,
            uri=redact_dsn(dsn),
            content_hash=source_id,
            metadata={"schema": schema},
        )
        result = IngestResult(source=source, secret=dsn)
        with conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_name, column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = %s ORDER BY table_name, ordinal_position",
                    (schema,),
                )
                columns: dict[str, list[tuple[str, str]]] = {}
                for tname, cname, dtype in cur.fetchall():
                    columns.setdefault(tname, []).append((cname, dtype))
                for tname, cols in columns.items():
                    ident = pgsql.Identifier(schema, tname)
                    cur.execute(pgsql.SQL("SELECT count(*) FROM {}").format(ident))
                    (count,) = cur.fetchone()
                    cur.execute(pgsql.SQL("SELECT * FROM {} LIMIT 3").format(ident))
                    names = [d.name for d in cur.description]
                    samples = [
                        {
                            n: (
                                v
                                if isinstance(v, int | float | str | bool) or v is None
                                else str(v)
                            )
                            for n, v in zip(names, row, strict=True)
                        }
                        for row in cur.fetchall()
                    ]
                    result.schema_cards.append(
                        SchemaCard(
                            source_id=source_id,
                            target=source_id,
                            engine="postgres",
                            table=tname,
                            columns=cols,
                            row_count=count,
                            sample_rows=samples,
                            schema=schema,
                            origin=f"postgres {schema} ({name})",
                        )
                    )
        if not result.schema_cards:
            raise IngestionError(f"schema '{schema}' has no tables")
        source.metadata["tables"] = [c.table for c in result.schema_cards]
        return result
