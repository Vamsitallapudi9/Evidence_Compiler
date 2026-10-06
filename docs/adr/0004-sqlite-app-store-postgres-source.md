# ADR 0004: SQLite for app state; Postgres only as a data source

**Status:** accepted

**Decision.** Application state (sources, evidence, runs) lives in a local SQLite file
through a repository layer. CSV and Excel tables are loaded into a local DuckDB file.
PostgreSQL is registered as a *source* and queried read-only at question time.

**Consequences.** Everything runs locally with no infrastructure. Being a data source
and being the system's own store are kept apart. A multi-user deployment would swap
the repository implementation.
