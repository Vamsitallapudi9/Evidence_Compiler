import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from evidence_compiler.app import AppContext
from evidence_compiler.config import Settings

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "data" / "demo" / "generated"
DEMO_PG_DSN = os.getenv(
    "EC_TEST_PG_DSN", "postgresql://ec_reader:ec_reader_local_only@localhost:5432/ec_demo"
)


@pytest.fixture(scope="session")
def demo_dir() -> Path:
    if not (DEMO / "ground_truth.json").exists():
        subprocess.run([sys.executable, str(REPO / "data/demo/generate.py")], check=True)
    return DEMO


def pg_available() -> bool:
    try:
        with psycopg.connect(DEMO_PG_DSN, connect_timeout=2) as conn:
            conn.execute("SELECT 1 FROM contract_events LIMIT 1")
        return True
    except psycopg.Error:
        return False


requires_pg = pytest.mark.skipif(not pg_available(), reason="demo Postgres not available")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return replace(Settings(), data_dir=tmp_path / "var", llm_cache=False)


@pytest.fixture
def ctx(settings: Settings, demo_dir: Path) -> AppContext:
    c = AppContext(settings)
    for name in [
        "q1_fy2026_report.pdf",
        "q2_fy2026_report.pdf",
        "regional_sales.csv",
        "customer_segments.xlsx",
    ]:
        c.ingest_file(demo_dir / name)
    return c
