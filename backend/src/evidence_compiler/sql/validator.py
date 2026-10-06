"""Validation of model-generated SQL.

Model-written SQL is treated as untrusted input. A query is accepted only if it is a
single read-only SELECT over allow-listed tables that calls no dangerous functions;
a row LIMIT is always enforced.
"""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


class SqlValidationError(ValueError):
    pass


_FORBIDDEN_NODE_NAMES = [
    "Insert",
    "Update",
    "Delete",
    "Drop",
    "Create",
    "Alter",
    "Command",
    "Into",
    "Merge",
    "Copy",
    "Transaction",
    "Commit",
    "Rollback",
    "Set",
    "Pragma",
    "Use",
    "Grant",
    "Lock",
    "Attach",
    "Detach",
    "Install",
    "Load",
    "Export",
    "Analyze",
    "Truncate",
    "TruncateTable",
]
_FORBIDDEN_NODES = tuple(
    t for t in (getattr(exp, n, None) for n in _FORBIDDEN_NODE_NAMES) if isinstance(t, type)
)
_FORBIDDEN_FUNC_PREFIXES = (
    "read_",
    "pg_",
    "lo_",
    "dblink",
    "copy",
    "glob",
    "getenv",
    "current_setting",
    "set_config",
    "query",
    "sniff_",
    "load",
    "install",
    "system",
    "file",
    "http",
    "txid_",
    "nextval",
    "setval",
)


@dataclass(frozen=True)
class ValidatedQuery:
    sql: str
    tables: list[str]
    is_aggregate: bool


def _func_name(f: exp.Func) -> str:
    if isinstance(f, exp.Anonymous):
        return str(f.name).lower()
    return f.sql_name().lower()


def validate_sql(
    sql: str,
    *,
    dialect: str,
    allowed_tables: set[str],
    max_rows: int,
    allowed_schemas: set[str] | None = None,
) -> ValidatedQuery:
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except ParseError as exc:
        raise SqlValidationError(f"could not parse SQL: {exc}") from exc
    if len(statements) != 1:
        raise SqlValidationError(f"expected exactly one statement, got {len(statements)}")
    stmt = statements[0]
    if not isinstance(stmt, exp.Query):
        raise SqlValidationError(f"only SELECT queries are allowed (got {stmt.key.upper()})")

    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise SqlValidationError(f"forbidden SQL construct: {node.key.upper()}")
        if isinstance(node, exp.Func):
            name = _func_name(node)
            if name.startswith(_FORBIDDEN_FUNC_PREFIXES):
                raise SqlValidationError(f"function not allowed: {name}")

    allowed = {t.lower() for t in allowed_tables}
    schemas = {s.lower() for s in (allowed_schemas or set())}
    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    tables: list[str] = []
    for table in stmt.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise SqlValidationError("table functions are not allowed")
        name = table.name.lower()
        if name in cte_names and not table.db:
            continue
        if table.catalog:
            raise SqlValidationError(f"cross-database reference not allowed: {table.sql()}")
        if table.db and table.db.lower() not in schemas:
            raise SqlValidationError(f"schema not allowed: {table.db}")
        if name not in allowed:
            raise SqlValidationError(
                f"unknown table '{table.name}' (allowed: {', '.join(sorted(allowed))})"
            )
        if name not in tables:
            tables.append(name)
    if not tables:
        raise SqlValidationError("query must read from at least one table")

    is_aggregate = any(True for _ in stmt.find_all(exp.AggFunc)) or any(
        s.args.get("group") is not None for s in stmt.find_all(exp.Select)
    )

    if isinstance(stmt, exp.Select):
        limit = stmt.args.get("limit")
        current = None
        if limit is not None and isinstance(limit.expression, exp.Literal):
            try:
                current = int(limit.expression.this)
            except ValueError:
                current = None
        if current is None or current > max_rows:
            stmt = stmt.limit(max_rows)
    else:
        stmt = exp.select("*").from_(stmt.subquery("q")).limit(max_rows)

    return ValidatedQuery(sql=stmt.sql(dialect=dialect), tables=tables, is_aggregate=is_aggregate)
