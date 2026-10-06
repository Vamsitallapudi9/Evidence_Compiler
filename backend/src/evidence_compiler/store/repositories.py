"""Repository layer over the SQLite store; the rest of the app depends only on this."""

import json
from dataclasses import asdict

from sqlalchemy import Engine
from sqlmodel import Session, col, delete, select

from evidence_compiler.core.models import Answer, EvidenceItem, RunEvent, RunStatus, Source
from evidence_compiler.ingestion.base import IngestResult, SchemaCard
from evidence_compiler.store.db import EvidenceRow, RunRow, SourceRow


class Repository:
    def __init__(self, engine: Engine):
        self.engine = engine

    # --- sources -----------------------------------------------------------------------

    def save_ingest(self, result: IngestResult) -> None:
        with Session(self.engine) as s:
            s.exec(delete(EvidenceRow).where(col(EvidenceRow.source_id) == result.source.id))
            existing = s.get(SourceRow, result.source.id)
            if existing:
                s.delete(existing)
                s.flush()
            s.add(
                SourceRow(
                    id=result.source.id,
                    kind=result.source.kind.value,
                    name=result.source.name,
                    data=result.source.model_dump_json(),
                    schema_cards=json.dumps([asdict(c) for c in result.schema_cards], default=str),
                    pages=json.dumps({str(k): v for k, v in result.pages.items()}),
                    secret=result.secret,
                )
            )
            for item in result.evidence:
                s.add(
                    EvidenceRow(id=item.id, source_id=result.source.id, data=item.model_dump_json())
                )
            s.commit()

    def list_sources(self) -> list[Source]:
        with Session(self.engine) as s:
            rows = s.exec(select(SourceRow).order_by(col(SourceRow.created_at))).all()
            return [Source.model_validate_json(r.data) for r in rows]

    def get_source(self, source_id: str) -> Source | None:
        with Session(self.engine) as s:
            row = s.get(SourceRow, source_id)
            return Source.model_validate_json(row.data) if row else None

    def delete_source(self, source_id: str) -> bool:
        with Session(self.engine) as s:
            row = s.get(SourceRow, source_id)
            if row is None:
                return False
            s.exec(delete(EvidenceRow).where(col(EvidenceRow.source_id) == source_id))
            s.delete(row)
            s.commit()
            return True

    def schema_cards(self) -> list[SchemaCard]:
        with Session(self.engine) as s:
            cards: list[SchemaCard] = []
            for row in s.exec(select(SourceRow)).all():
                for raw in json.loads(row.schema_cards):
                    raw["columns"] = [tuple(c) for c in raw["columns"]]
                    cards.append(SchemaCard(**raw))
            return cards

    def page_text(self, source_id: str, page: int) -> tuple[str, int] | None:
        with Session(self.engine) as s:
            row = s.get(SourceRow, source_id)
            if row is None:
                return None
            pages = json.loads(row.pages)
            text = pages.get(str(page))
            return (text, len(pages)) if text is not None else None

    def secret(self, source_id: str) -> str | None:
        with Session(self.engine) as s:
            row = s.get(SourceRow, source_id)
            return row.secret if row else None

    def evidence_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with Session(self.engine) as s:
            stmt = select(EvidenceRow.source_id).where(col(EvidenceRow.run_minted).is_(False))
            for sid in s.exec(stmt).all():
                counts[sid] = counts.get(sid, 0) + 1
        return counts

    def flagged_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.all_evidence():
            if item.security_flags:
                for sid in item.source_ids:
                    counts[sid] = counts.get(sid, 0) + 1
        return counts

    # --- evidence ----------------------------------------------------------------------

    def all_evidence(self) -> list[EvidenceItem]:
        """Evidence produced by connectors at ingestion time (the retrieval corpus)."""
        with Session(self.engine) as s:
            stmt = select(EvidenceRow).where(col(EvidenceRow.run_minted).is_(False))
            return [EvidenceItem.model_validate_json(r.data) for r in s.exec(stmt)]

    def get_evidence(self, evidence_id: str) -> EvidenceItem | None:
        with Session(self.engine) as s:
            row = s.get(EvidenceRow, evidence_id)
            return EvidenceItem.model_validate_json(row.data) if row else None

    def save_run_evidence(self, items: list[EvidenceItem]) -> None:
        """Persist evidence minted during a run (SQL rows, calculations) for later lookup."""
        with Session(self.engine) as s:
            for item in items:
                if s.get(EvidenceRow, item.id) is None:
                    s.add(
                        EvidenceRow(
                            id=item.id,
                            source_id=item.source_ids[0] if item.source_ids else "",
                            data=item.model_dump_json(),
                            run_minted=True,
                        )
                    )
            s.commit()

    # --- runs --------------------------------------------------------------------------

    def create_run(self, run_id: str, question: str) -> None:
        with Session(self.engine) as s:
            s.add(RunRow(id=run_id, question=question, status=RunStatus.PENDING.value))
            s.commit()

    def update_run(
        self,
        run_id: str,
        *,
        status: RunStatus | None = None,
        events: list[RunEvent] | None = None,
        answer: Answer | None = None,
        error: str | None = None,
        usage: dict | None = None,
    ) -> None:
        with Session(self.engine) as s:
            row = s.get(RunRow, run_id)
            if row is None:
                return
            if status is not None:
                row.status = status.value
            if events is not None:
                row.events = json.dumps([e.model_dump(mode="json") for e in events])
            if answer is not None:
                row.answer = answer.model_dump_json()
            if error is not None:
                row.error = error
            if usage is not None:
                row.usage = json.dumps(usage, default=str)
            s.add(row)
            s.commit()

    def get_run(self, run_id: str) -> RunRow | None:
        with Session(self.engine) as s:
            return s.get(RunRow, run_id)

    def interrupt_unfinished_runs(self) -> int:
        """Mark runs left pending/running by a previous server process as failed."""
        with Session(self.engine) as s:
            stmt = select(RunRow).where(
                col(RunRow.status).in_([RunStatus.PENDING.value, RunStatus.RUNNING.value])
            )
            rows = list(s.exec(stmt).all())
            for row in rows:
                row.status = RunStatus.FAILED.value
                row.error = (
                    "Interrupted: the server restarted while this run was in progress. "
                    "Run it again."
                )
                s.add(row)
            s.commit()
            return len(rows)

    def list_runs(self, limit: int = 50) -> list[RunRow]:
        with Session(self.engine) as s:
            stmt = select(RunRow).order_by(col(RunRow.created_at).desc()).limit(limit)
            return list(s.exec(stmt).all())
