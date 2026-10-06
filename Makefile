PY      := backend/.venv/bin/python
PG_BIN  ?= /opt/homebrew/opt/postgresql@17/bin
export PYTHONPATH := backend/src

.PHONY: setup demo-data db-seed load-demo dev api web test lint eval eval-fake check-llm

setup:            ## install backend (editable) and frontend dependencies
	test -d backend/.venv || python3 -m venv backend/.venv
	$(PY) -m pip install -q -e "backend[dev]"
	cd frontend && npm install

demo-data:        ## generate the Halcyon Instruments demo corpus + ground truth
	$(PY) data/demo/generate.py

db-seed: demo-data  ## create ec_demo database + read-only ec_reader role in local Postgres
	$(PY) data/demo/seed_postgres.py

load-demo:        ## ingest the demo corpus into a running API (make api first)
	$(PY) data/demo/load_demo.py

api:              ## FastAPI on :8000
	$(PY) -m uvicorn evidence_compiler.api.main:app --reload --port 8000 --app-dir backend/src

web:              ## Vite dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

dev:              ## API + web together
	$(MAKE) -j2 api web

test:             ## backend + frontend tests
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm test

lint:
	backend/.venv/bin/ruff check backend eval data/demo
	cd frontend && npm run lint

check-llm:        ## verify API key, model ID and structured output (costs < 1 cent)
	$(PY) -m evidence_compiler.llm.check

eval:             ## run the A/B/C benchmark (needs an API key; responses cached)
	$(PY) -m eval.run

eval-fake:        ## smoke-test the benchmark harness without an LLM
	$(PY) -m eval.run --fake
