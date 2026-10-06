"""Upload the demo corpus (and the demo Postgres) to a running API."""

import os
import sys
from pathlib import Path

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
DEMO = Path(__file__).parent / "generated"
DSN = os.getenv("EC_PG_DSN", "postgresql://ec_reader:ec_reader_local_only@localhost:5432/ec_demo")

with httpx.Client(base_url=API, timeout=60) as client:
    for name in [
        "q1_fy2026_report.pdf",
        "q2_fy2026_report.pdf",
        "regional_sales.csv",
        "customer_segments.xlsx",
    ]:
        with open(DEMO / name, "rb") as f:
            r = client.post("/api/sources", files={"file": (name, f)})
        print(name, r.status_code, r.json().get("evidence_count", r.text))
    r = client.post("/api/sources/postgres", json={"name": "crm", "dsn": DSN})
    print("postgres crm", r.status_code, r.json().get("tables", r.text))
