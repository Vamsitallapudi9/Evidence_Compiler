"""Application container: wires stores, connectors, retrieval, SQL and the LLM together."""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from evidence_compiler.config import Settings, get_settings
from evidence_compiler.core.ids import random_id
from evidence_compiler.core.models import RunEvent, RunStatus, Source
from evidence_compiler.ingestion.base import IngestResult
from evidence_compiler.ingestion.huggingface import HuggingFaceConnector
from evidence_compiler.ingestion.postgres import PostgresConnector
from evidence_compiler.ingestion.registry import ConnectorRegistry
from evidence_compiler.ingestion.url import UrlIngestor, find_urls
from evidence_compiler.llm import LLMClient, make_llm
from evidence_compiler.llm.meter import LlmCall, MeteredLLM, RunCancelled
from evidence_compiler.pipeline.orchestrator import Pipeline, PipelineOptions
from evidence_compiler.retrieval.bm25 import BM25Retriever
from evidence_compiler.sql.duckdb_store import TabularStore
from evidence_compiler.sql.executor import SqlExecutor
from evidence_compiler.store.db import make_engine
from evidence_compiler.store.repositories import Repository

log = logging.getLogger(__name__)


class AppContext:
    def __init__(self, settings: Settings | None = None, llm: LLMClient | None = None):
        self.settings = settings or get_settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.repo = Repository(make_engine(self.settings.sqlite_path))
        self.tabular = TabularStore(self.settings.duckdb_path)
        self.registry = ConnectorRegistry(self.tabular)
        self.retriever = BM25Retriever()
        self.retriever.index(self.repo.all_evidence())
        self.executor = SqlExecutor(
            self.tabular,
            self.repo.secret,
            max_rows=self.settings.sql_max_rows,
            timeout_ms=self.settings.sql_timeout_ms,
        )
        self.urls = UrlIngestor(
            self.settings.uploads_dir,
            self.registry.tabular,
            max_bytes=self.settings.max_upload_mb * 1024 * 1024,
            allow_private=self.settings.allow_private_urls,
        )
        self._llm = llm
        self.runs = RunManager(self)

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = make_llm(self.settings)
        return self._llm

    def pipeline(
        self, options: PipelineOptions | None = None, llm: LLMClient | None = None
    ) -> Pipeline:
        return Pipeline(
            llm or self.llm, self.repo, self.retriever, self.executor, self.settings, options
        )

    # --- sources -----------------------------------------------------------------------

    def _store(self, result: IngestResult) -> Source:
        self.retriever.remove_source(result.source.id)
        self.repo.save_ingest(result)
        self.retriever.index(result.evidence)
        return result.source

    def ingest_file(self, path: Path, name: str | None = None) -> Source:
        connector = self.registry.for_path(path)
        return self._store(connector.ingest(path, name=name or path.name))

    def register_postgres(self, dsn: str, name: str, schema: str = "public") -> Source:
        return self._store(PostgresConnector().register(dsn, name=name, schema=schema))

    def ingest_url(self, url: str, name: str | None = None) -> Source:
        return self._store(self.urls.ingest(url, name))

    def register_huggingface(
        self,
        dataset: str,
        config: str | None = None,
        split: str | None = None,
        max_rows: int = 2000,
    ) -> Source:
        connector = HuggingFaceConnector(self.tabular, token=self.settings.hf_token)
        max_rows = max(1, min(max_rows, self.settings.hf_max_rows))
        return self._store(
            connector.register(dataset, config=config, split=split, max_rows=max_rows)
        )

    def delete_source(self, source_id: str) -> bool:
        source = self.repo.get_source(source_id)
        if source is None:
            return False
        if source.kind in ("csv", "xlsx", "huggingface"):
            self.tabular.drop_tables(source.metadata.get("tables", []))
        self.retriever.remove_source(source_id)
        return self.repo.delete_source(source_id)


@dataclass
class _LiveRun:
    """In-memory state of a run executing in this process."""

    meter: MeteredLLM
    started: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    events: list[RunEvent] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)  # LLM call snapshots, in order
    alive: bool = True


class RunManager:
    """Runs pipelines in background threads; tracks progress, model usage and liveness."""

    def __init__(self, ctx: AppContext, workers: int = 2):
        self.ctx = ctx
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="run")
        self._live: dict[str, _LiveRun] = {}
        self._lock = threading.Lock()
        interrupted = ctx.repo.interrupt_unfinished_runs()
        if interrupted:
            log.warning(
                "marked %d run(s) from a previous server process as interrupted", interrupted
            )

    # --- lifecycle ---------------------------------------------------------------------

    def start(self, question: str) -> str:
        run_id = random_id("run")
        self.ctx.repo.create_run(run_id, question)
        meter = MeteredLLM(
            self.ctx.llm, self.ctx.settings, on_call=lambda c: self._on_call(run_id, c)
        )
        with self._lock:
            self._live[run_id] = _LiveRun(meter=meter)
        self._pool.submit(self._work, run_id, question)
        return run_id

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            live = self._live.get(run_id)
        if live is None or not live.alive:
            return False
        live.meter.cancel.set()
        self._emit(run_id, RunEvent(stage="cancel", message="Cancelling after the current step…"))
        return True

    def _work(self, run_id: str, question: str) -> None:
        repo = self.ctx.repo
        live = self._live[run_id]
        repo.update_run(run_id, status=RunStatus.RUNNING)
        try:
            scope = self._fetch_links(run_id, question)
            live.meter.check_cancelled()
            answer = self.ctx.pipeline(llm=live.meter).run(
                question, run_id=run_id, emit=lambda e: self._emit(run_id, e), source_ids=scope
            )
            repo.update_run(
                run_id,
                status=RunStatus.DONE,
                answer=answer,
                events=self.events(run_id),
                usage=live.meter.summary(include_log=True),
            )
        except RunCancelled as exc:
            self._emit(run_id, RunEvent(stage="cancel", message="Run cancelled."))
            repo.update_run(
                run_id,
                status=RunStatus.CANCELLED,
                error=str(exc),
                events=self.events(run_id),
                usage=live.meter.summary(include_log=True),
            )
        except Exception as exc:  # surface any failure to the user rather than hang
            log.exception("run %s failed", run_id)
            self._emit(run_id, RunEvent(stage="error", message=str(exc)))
            repo.update_run(
                run_id,
                status=RunStatus.FAILED,
                error=str(exc),
                events=self.events(run_id),
                usage=live.meter.summary(include_log=True),
            )
        finally:
            live.alive = False

    # --- live updates ------------------------------------------------------------------

    def _emit(self, run_id: str, event: RunEvent) -> None:
        with self._lock:
            live = self._live.get(run_id)
            if live is not None:
                live.events.append(event)
                live.last_activity = time.monotonic()

    def _on_call(self, run_id: str, call: LlmCall) -> None:
        with self._lock:
            live = self._live.get(run_id)
            if live is None:
                return
            live.calls.append(call.public())
            live.last_activity = time.monotonic()
        if call.status != "running":  # persist totals so they survive a crash
            self.ctx.repo.update_run(run_id, usage=live.meter.summary(include_log=True))

    def call_snapshots(self, run_id: str) -> list[dict]:
        with self._lock:
            live = self._live.get(run_id)
            return list(live.calls) if live else []

    def heartbeat(self, run_id: str) -> dict | None:
        row = self.ctx.repo.get_run(run_id)
        if row is None:
            return None
        with self._lock:
            live = self._live.get(run_id)
        now = time.monotonic()
        if live is None:
            usage = json.loads(row.usage) if row.usage else None
            if usage:
                usage.pop("calls_log", None)
            return {
                "run_id": run_id,
                "status": row.status,
                "alive": False,
                "elapsed_s": None,
                "last_activity_s": None,
                "current": None,
                "usage": usage,
            }
        current_call = live.meter.current()
        current = (
            current_call.label
            if current_call
            else (live.events[-1].message if live.events else "Starting…")
        )
        return {
            "run_id": run_id,
            "status": row.status,
            "alive": live.alive,
            "elapsed_s": round(now - live.started, 1),
            "last_activity_s": round(now - live.last_activity, 1),
            "current": current,
            "usage": live.meter.summary(),
        }

    def usage(self, run_id: str) -> dict | None:
        with self._lock:
            live = self._live.get(run_id)
        if live is not None and live.alive:
            return live.meter.summary(include_log=True)
        row = self.ctx.repo.get_run(run_id)
        return json.loads(row.usage) if row and row.usage else None

    def alive(self, run_id: str) -> bool:
        with self._lock:
            live = self._live.get(run_id)
        return bool(live and live.alive)

    def _fetch_links(self, run_id: str, question: str) -> set[str] | None:
        """Fetch links pasted into the question; the run then answers only from them."""
        urls = find_urls(question)
        if not urls:
            return None
        scope: set[str] = set()
        for url in urls[:5]:
            self._emit(run_id, RunEvent(stage="fetch", message=f"Fetching {url}…"))
            try:
                src = self.ctx.ingest_url(url)
            except Exception as exc:  # report per-link failures, keep going
                self._emit(run_id, RunEvent(stage="fetch", message=f"Could not use {url}: {exc}"))
                continue
            scope.add(src.id)
            self._emit(
                run_id,
                RunEvent(
                    stage="fetch",
                    message=f"Fetched {src.name}",
                    data={"source_id": src.id, "url": url},
                ),
            )
        if not scope:
            raise RuntimeError("None of the links in the question could be fetched.")
        return scope

    def events(self, run_id: str) -> list[RunEvent]:
        with self._lock:
            if run_id in self._live:
                return list(self._live[run_id].events)
        row = self.ctx.repo.get_run(run_id)
        if row is None:
            return []
        return [RunEvent.model_validate(e) for e in json.loads(row.events)]

    def status(self, run_id: str) -> RunStatus | None:
        row = self.ctx.repo.get_run(run_id)
        return RunStatus(row.status) if row else None
