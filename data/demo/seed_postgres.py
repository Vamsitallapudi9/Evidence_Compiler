"""Create the local demo database and a read-only role, then load seed.sql.

Usage: python data/demo/seed_postgres.py [ADMIN_DSN]
Default ADMIN_DSN is "dbname=postgres" (the local Homebrew superuser).
Creates database `ec_demo` and role `ec_reader` (SELECT-only), and prints the DSN to
register as a source.
"""

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

DB = "ec_demo"
ROLE = "ec_reader"
# Local demo credential for a read-only role on localhost. Not a secret; override it with
# EC_DEMO_PG_PASSWORD (and set EC_PG_DSN to match) if your Postgres is reachable by others.
ROLE_PASSWORD = os.getenv("EC_DEMO_PG_PASSWORD", "ec_reader_local_only")
SEED = Path(__file__).parent / "generated" / "seed.sql"


def main() -> None:
    admin_dsn = sys.argv[1] if len(sys.argv) > 1 else "dbname=postgres"
    if not SEED.exists():
        sys.exit("seed.sql not found - run data/demo/generate.py first")
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB)))
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone():
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(ROLE), sql.Literal(ROLE_PASSWORD)
                )
            )
    db_dsn = psycopg.conninfo.make_conninfo(admin_dsn, dbname=DB)
    with psycopg.connect(db_dsn) as conn:
        conn.execute(SEED.read_text())
        conn.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM PUBLIC"))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE)))
        conn.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        conn.execute(
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(
                sql.Identifier(ROLE)
            )
        )
    print(f"seeded {DB}; read-only DSN:")
    print(f"postgresql://{ROLE}:{ROLE_PASSWORD}@localhost:5432/{DB}")


if __name__ == "__main__":
    main()
