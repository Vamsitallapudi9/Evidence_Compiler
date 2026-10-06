import psycopg
import pytest

from evidence_compiler.core.models import Creator, EvidenceOrigin
from evidence_compiler.sql.validator import SqlValidationError, validate_sql
from tests.conftest import DEMO_PG_DSN, requires_pg

ALLOWED = {"regional_sales"}


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE regional_sales",
        "UPDATE regional_sales SET revenue_usd = 0",
        "DELETE FROM regional_sales",
        "INSERT INTO regional_sales VALUES (1)",
        "SELECT 1 FROM regional_sales; DROP TABLE regional_sales",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM regional_sales WHERE region = '' OR pg_sleep(10) IS NULL",
        "SELECT * INTO copy_t FROM regional_sales",
        "SELECT * FROM other_table",
        "SELECT * FROM main.regional_sales",
        "COPY regional_sales TO '/tmp/out.csv'",
        "ATTACH '/tmp/x.db' AS x",
        "PRAGMA database_list",
        "SELECT getenv('HOME') FROM regional_sales",
    ],
)
def test_validator_rejects_unsafe_sql(sql):
    with pytest.raises(SqlValidationError):
        validate_sql(sql, dialect="duckdb", allowed_tables=ALLOWED, max_rows=10)


def test_validator_accepts_ctes_and_enforces_limit():
    q = validate_sql(
        "WITH t AS (SELECT region, SUM(revenue_usd) AS r FROM regional_sales GROUP BY region) "
        "SELECT * FROM t LIMIT 5000",
        dialect="duckdb",
        allowed_tables=ALLOWED,
        max_rows=50,
    )
    assert q.sql.endswith("LIMIT 50") and q.is_aggregate and q.tables == ["regional_sales"]


def test_duckdb_query_mints_derived_evidence_for_aggregates(ctx):
    cards = ctx.repo.schema_cards()
    result = ctx.executor.run(
        "tabular",
        "SELECT region, SUM(CASE WHEN quarter='2026-Q2' THEN revenue_usd END) - "
        "SUM(CASE WHEN quarter='2026-Q1' THEN revenue_usd END) AS revenue_change_usd "
        "FROM regional_sales GROUP BY region ORDER BY region",
        cards,
    )
    europe = next(e for e in result.evidence if e.fields["region"] == "Europe")
    assert europe.fields["revenue_change_usd"] == -7_400_000
    assert europe.origin == EvidenceOrigin.DERIVED and europe.creator == Creator.SQL
    assert europe.location.kind == "query" and "GROUP BY" in europe.location.sql


def test_duckdb_row_lookup_is_primary(ctx):
    result = ctx.executor.run(
        "tabular", "SELECT * FROM regional_sales WHERE region = 'LATAM'", ctx.repo.schema_cards()
    )
    assert result.evidence and all(e.origin == EvidenceOrigin.PRIMARY for e in result.evidence)


def test_duckdb_connection_is_read_only_even_if_validation_is_bypassed(ctx):
    with pytest.raises(Exception, match="(?i)read.only|cannot"):
        ctx.tabular.query("CREATE TABLE evil AS SELECT 1", 10)
    with pytest.raises(Exception):  # noqa: B017 - any refusal is fine
        ctx.tabular.query("SELECT * FROM read_csv('/etc/hosts')", 10)


@requires_pg
def test_postgres_source_query_and_read_only_role(ctx):
    src = ctx.register_postgres(DEMO_PG_DSN, "crm")
    result = ctx.executor.run(
        src.id,
        "SELECT c.region, COUNT(*) AS churned FROM contract_events e JOIN customers c "
        "ON c.customer_id = e.customer_id WHERE e.event_type = 'churn' AND e.quarter = '2026-Q2' "
        "GROUP BY c.region ORDER BY churned DESC",
        ctx.repo.schema_cards(),
    )
    top = result.evidence[0]
    assert top.fields["region"] == "Europe" and top.fields["churned"] == 11
    assert top.source_ids == [src.id]
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):  # defence in depth
        ctx.executor._run_postgres(src.id, "DELETE FROM contract_events", "public")
    with pytest.raises(SqlValidationError):
        ctx.executor.run(src.id, "DELETE FROM contract_events", ctx.repo.schema_cards())
