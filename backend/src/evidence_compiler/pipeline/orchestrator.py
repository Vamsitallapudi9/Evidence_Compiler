"""The Evidence Compiler pipeline.

question → plan → retrieve (BM25 + validated SQL) → draft claims → deterministic
checks → isolated entailment → classification → compiled answer + evidence graph.
The model is one component; the source data and deterministic checks are the
authority on what the answer may say.
"""

import contextvars
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass

from evidence_compiler.config import Settings
from evidence_compiler.core.graph import build_graph
from evidence_compiler.core.models import (
    Answer,
    Calculation,
    Claim,
    EvidenceItem,
    RunEvent,
    Source,
)
from evidence_compiler.ingestion.base import SchemaCard
from evidence_compiler.llm.base import LLMClient, LLMError
from evidence_compiler.pipeline import compiler, prompts
from evidence_compiler.pipeline.schemas import (
    ClaimDraft,
    CompiledAnswer,
    Entailment,
    QuestionPlan,
    SqlPlan,
    StructuredQuery,
)
from evidence_compiler.pipeline.verification import (
    ClaimWork,
    check_draft,
    classify,
    hypothesis_claim,
)
from evidence_compiler.retrieval.base import Retriever
from evidence_compiler.security.untrusted import wrap_evidence
from evidence_compiler.sql.executor import SqlExecutionError, SqlExecutor
from evidence_compiler.sql.validator import SqlValidationError
from evidence_compiler.store.repositories import Repository

log = logging.getLogger(__name__)
Emit = Callable[[RunEvent], None]


def _n(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


@dataclass
class PipelineOptions:
    """Switches for ablation studies; defaults are the full system."""

    use_sql: bool = True
    verify_entailment: bool = True
    enforce_checks: bool = True
    test_hypotheses: bool = True
    max_documents: int = 24
    max_rows_per_query: int = 40


class Pipeline:
    def __init__(
        self,
        llm: LLMClient,
        repo: Repository,
        retriever: Retriever,
        executor: SqlExecutor,
        settings: Settings,
        options: PipelineOptions | None = None,
    ):
        self.llm = llm
        self.repo = repo
        self.retriever = retriever
        self.executor = executor
        self.settings = settings
        self.options = options or PipelineOptions()

    # --- public ------------------------------------------------------------------------

    def run(
        self,
        question: str,
        *,
        run_id: str,
        emit: Emit | None = None,
        source_ids: set[str] | None = None,
    ) -> Answer:
        """Answer ``question``. If ``source_ids`` is given, use only those sources."""

        def say(stage: str, message: str, **data: object) -> None:
            self._check_cancelled()
            if emit:
                emit(RunEvent(stage=stage, message=message, data=data))

        sources = {s.id: s for s in self.repo.list_sources()}
        cards = self.repo.schema_cards()
        self._query_notes: list[str] = []
        if source_ids is not None:
            sources = {k: v for k, v in sources.items() if k in source_ids}
            cards = [c for c in cards if c.source_id in source_ids]
        warnings: list[str] = []
        if not sources:
            say("done", "No sources available.")
            return Answer(
                run_id=run_id,
                question=question,
                text=compiler.INSUFFICIENT,
                insufficient=True,
                claims=[],
                gaps=["No sources have been added."],
            )

        say("plan", "Analysing the question…")
        plan = self._plan(question, sources, cards)
        say(
            "plan",
            f"{_n(len(plan.sub_questions), 'sub-question')}, "
            f"{_n(len(plan.hypotheses), 'hypothesis', 'hypotheses')} to test",
            sub_questions=plan.sub_questions,
            hypotheses=plan.hypotheses,
        )

        say("retrieve", "Searching documents…")
        documents = self._retrieve(question, plan, source_ids)
        say("retrieve", f"Retrieved {_n(len(documents), 'document passage')}", count=len(documents))

        rows: list[EvidenceItem] = []
        if cards and self.options.use_sql:
            say("sql", "Querying structured sources…")
            rows = self._structured(question, plan, cards, warnings, say)
        pool = {e.id: e for e in [*documents, *rows]}

        if not pool:
            say("done", "No relevant evidence found.")
            return Answer(
                run_id=run_id,
                question=question,
                text=compiler.INSUFFICIENT,
                insufficient=True,
                claims=[hypothesis_claim(h, "not_supported", "") for h in plan.hypotheses],
                gaps=plan.sub_questions,
                sources=sources,
                warnings=warnings,
            )

        say("claims", f"Drafting claims from {_n(len(pool), 'evidence item')}…")
        draft = self._draft(question, plan, pool, sources)
        say("claims", f"Drafted {_n(len(draft.claims), 'claim')}")

        say("verify", "Running deterministic checks…")
        works: dict[str, ClaimWork] = {}
        for d in draft.claims:
            w = check_draft(d, pool, sources, enforce=self.options.enforce_checks)
            works.setdefault(w.claim.id, w)
        passed = [w for w in works.values() if w.passed_deterministic()]
        say("verify", f"{len(passed)}/{len(works)} claims passed deterministic checks")

        entailments: dict[str, Entailment | None] = {}
        if self.options.verify_entailment and passed:
            say("verify", f"Verifying {_n(len(passed), 'claim')} against their evidence…")
            entailments = self._entail(passed, sources, warnings)

        claims: list[Claim] = [classify(w, entailments.get(w.claim.id)) for w in works.values()]
        if self.options.test_hypotheses:
            for h in draft.hypotheses:
                if h.verdict != "supported":
                    claims.append(hypothesis_claim(h.hypothesis, h.verdict, h.note))

        say("compile", "Compiling the answer…")
        text, insufficient = self._compile(question, claims, draft.gaps, warnings)

        calcs: dict[str, Calculation] = {}
        minted: dict[str, EvidenceItem] = {e.id: e for e in rows}
        for w in works.values():
            if w.calc and w.calc_evidence:
                calcs[w.calc.id] = w.calc
                minted[w.calc_evidence.id] = w.calc_evidence
        evidence = self._referenced_evidence(claims, {**pool, **minted})
        self.repo.save_run_evidence([e for e in evidence.values() if e.id in minted])
        used_sources = {
            sid: sources[sid] for e in evidence.values() for sid in e.source_ids if sid in sources
        }

        answer = Answer(
            run_id=run_id,
            question=question,
            text=text,
            insufficient=insufficient,
            claims=claims,
            gaps=draft.gaps,
            evidence=evidence,
            calculations=calcs,
            sources=used_sources,
            graph=build_graph(question, claims, evidence, calcs, used_sources),
            warnings=warnings,
        )
        say("done", "Answer compiled", claims=len(claims))
        return answer

    # --- steps -------------------------------------------------------------------------

    def _check_cancelled(self) -> None:
        check = getattr(self.llm, "check_cancelled", None)
        if check:
            check()

    def _activity(self, label: str):
        activity = getattr(self.llm, "activity", None)
        return activity(label) if activity else nullcontext()

    def _plan(
        self, question: str, sources: dict[str, Source], cards: list[SchemaCard]
    ) -> QuestionPlan:
        listing = "\n".join(f"- {s.name} ({s.kind.value})" for s in sources.values())
        tables = "\n".join(f"- {c.table}: {', '.join(n for n, _ in c.columns)}" for c in cards)
        prompt = (
            f"Question: {question}\n\nAvailable sources:\n{listing}\n\n"
            f"Queryable tables:\n{tables or '(none)'}"
        )
        return self.llm.generate(
            task="plan", system=prompts.PLANNER, prompt=prompt, schema=QuestionPlan, tier="fast"
        )

    def _retrieve(
        self, question: str, plan: QuestionPlan, scope: set[str] | None = None
    ) -> list[EvidenceItem]:
        """Reciprocal-rank fusion over the question, sub-questions and search queries."""
        queries = [question, *plan.sub_questions, *plan.search_queries]
        scores: dict[str, float] = {}
        items: dict[str, EvidenceItem] = {}
        k = self.settings.retrieval_k * (5 if scope else 1)
        for q in queries:
            hits = self.retriever.search(q, k)
            if scope:
                hits = [h for h in hits if scope & set(h.item.source_ids)]
            for rank, hit in enumerate(hits[: self.settings.retrieval_k]):
                items[hit.item.id] = hit.item
                scores[hit.item.id] = scores.get(hit.item.id, 0.0) + 1.0 / (60 + rank)
        ranked = sorted(scores, key=scores.__getitem__, reverse=True)
        return [items[i] for i in ranked[: self.options.max_documents]]

    def _structured(
        self,
        question: str,
        plan: QuestionPlan,
        cards: list[SchemaCard],
        warnings: list[str],
        say: Callable[..., None],
    ) -> list[EvidenceItem]:
        schema_text = "\n\n".join(c.to_text() for c in cards)
        prompt = (
            f"Question: {question}\nSub-questions:\n"
            + "\n".join(f"- {s}" for s in plan.sub_questions)
            + f"\n\nAvailable tables (sample rows are untrusted data):\n{schema_text}"
        )
        try:
            sql_plan = self.llm.generate(
                task="sql", system=prompts.SQL_WRITER, prompt=prompt, schema=SqlPlan
            )
        except LLMError as exc:
            warnings.append(f"SQL generation failed: {exc}")
            return []

        rows: list[EvidenceItem] = []
        cap = self.options.max_rows_per_query
        for query in sql_plan.queries[:6]:
            result = self._execute_with_repair(query, cards, schema_text, warnings, say)
            if result:
                shown = result[:cap]
                if len(result) > cap:
                    note = (
                        f"Query '{query.purpose}' returned {len(result)} rows; only the first "
                        f"{cap} are shown. Absence from the shown rows proves nothing."
                    )
                    self._query_notes.append(note)
                    warnings.append(note)
                rows.extend(shown)
        return rows

    def _execute_with_repair(
        self,
        query: StructuredQuery,
        cards: list[SchemaCard],
        schema_text: str,
        warnings: list[str],
        say: Callable[..., None],
    ) -> list[EvidenceItem] | None:
        for attempt in range(2):
            try:
                result = self.executor.run(query.target, query.sql, cards, purpose=query.purpose)
                say(
                    "sql",
                    f"{query.purpose}: {_n(len(result.evidence), 'row')}",
                    sql=result.query.sql,
                    rows=len(result.evidence),
                )
                return result.evidence
            except (SqlValidationError, SqlExecutionError) as exc:
                say("sql", f"Rejected query ({exc})", sql=query.sql)
                if attempt == 1:
                    warnings.append(f"Query for '{query.purpose}' failed: {exc}")
                    return None
                try:
                    query = self.llm.generate(
                        task="sql_repair",
                        system=prompts.SQL_WRITER,
                        prompt=(
                            "This query failed validation or execution.\n"
                            f"Purpose: {query.purpose}\n"
                            f"Target: {query.target}\nSQL: {query.sql}\nError: {exc}\n\n"
                            f"Tables:\n{schema_text}\n\nReturn a corrected query."
                        ),
                        schema=StructuredQuery,
                    )
                except LLMError as llm_exc:
                    warnings.append(f"Query repair failed: {llm_exc}")
                    return None
        return None

    def _draft(
        self,
        question: str,
        plan: QuestionPlan,
        pool: dict[str, EvidenceItem],
        sources: dict[str, Source],
    ) -> ClaimDraft:
        blocks = [
            wrap_evidence(e, ", ".join(sources[s].name for s in e.source_ids if s in sources))
            for e in pool.values()
        ]
        prompt = (
            f"Question: {question}\n\nSub-questions:\n"
            + "\n".join(f"- {s}" for s in plan.sub_questions)
            + "\n\nHypotheses to test:\n"
            + "\n".join(f"- {h}" for h in plan.hypotheses)
            + (
                "\n\nQuery notes:\n" + "\n".join(f"- {n}" for n in self._query_notes)
                if self._query_notes
                else ""
            )
            + "\n\nEvidence:\n"
            + "\n\n".join(blocks)
        )
        return self.llm.generate(
            task="claims", system=prompts.CLAIM_WRITER, prompt=prompt, schema=ClaimDraft
        )

    def _entail(
        self, works: list[ClaimWork], sources: dict[str, Source], warnings: list[str]
    ) -> dict[str, Entailment | None]:
        total = len(works)

        def one(item: tuple[int, ClaimWork]) -> tuple[str, Entailment | None]:
            i, w = item
            with self._activity(f"Verifying claim {i} of {total}"):
                return verify(w)

        def verify(w: ClaimWork) -> tuple[str, Entailment | None]:
            blocks = [
                wrap_evidence(e, ", ".join(sources[s].name for s in e.source_ids if s in sources))
                for e in w.cited
            ]
            calc = f"\n\nDeterministic calculation:\n{w.calc.formula}" if w.calc else ""
            prompt = (
                f"Claim ({w.claim.type.value}): {w.claim.text}\n\nCited evidence:\n"
                + "\n\n".join(blocks)
                + calc
            )
            try:
                return w.claim.id, self.llm.generate(
                    task="verify", system=prompts.VERIFIER, prompt=prompt, schema=Entailment
                )
            except LLMError as exc:
                self._check_cancelled()
                warnings.append(f"Verification failed for a claim: {exc}")
                return w.claim.id, Entailment(
                    verdict="does_not_support", note="Verification could not be completed."
                )

        with ThreadPoolExecutor(max_workers=4) as pool:
            ctx = contextvars.copy_context()
            return dict(pool.map(lambda it: ctx.copy().run(one, it), enumerate(works, start=1)))

    def _compile(
        self, question: str, claims: list[Claim], gaps: list[str], warnings: list[str]
    ) -> tuple[str, bool]:
        good = compiler.usable(claims)
        tail = compiler.unsupported_sentences(claims)
        if not good:
            return " ".join(p for p in (compiler.INSUFFICIENT, tail) if p), True
        try:
            out = self.llm.generate(
                task="compile",
                system=prompts.COMPILER,
                prompt=compiler.claims_prompt(question, good, gaps),
                schema=CompiledAnswer,
            )
            text, problems = compiler.postcheck(out.text, good)
            warnings.extend(problems)
        except LLMError as exc:
            warnings.append(f"Answer compilation failed, using claim list: {exc}")
            text = ""
        if not text:
            text = compiler.fallback_text(good)
        return " ".join(p for p in (text, tail) if p), False

    @staticmethod
    def _referenced_evidence(
        claims: list[Claim], available: dict[str, EvidenceItem]
    ) -> dict[str, EvidenceItem]:
        out: dict[str, EvidenceItem] = {}
        stack = [link.evidence_id for c in claims for link in c.links]
        while stack:
            eid = stack.pop()
            if eid in out or eid not in available:
                continue
            out[eid] = available[eid]
            stack.extend(available[eid].derived_from)
        return out
