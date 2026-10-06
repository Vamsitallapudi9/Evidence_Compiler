"""Run the benchmark: Systems A (RAG), B (RAG + citations), C (Evidence Compiler).

    python -m eval.run                       # all systems, all questions
    python -m eval.run --systems C --questions q10,q14
    python -m eval.run --fake                # plumbing smoke test, no API calls

Results are written to eval/results/<timestamp>.json and .md. Nothing in the report
is hand-written: every number comes from this run.
"""

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "src"))

from evidence_compiler.app import AppContext  # noqa: E402
from evidence_compiler.config import Settings  # noqa: E402
from evidence_compiler.llm import make_llm  # noqa: E402
from evidence_compiler.llm.cache import CachingLLM  # noqa: E402

from eval.judge import Judge, build_reference  # noqa: E402
from eval.metrics import QuestionScore, aggregate, score_deterministic  # noqa: E402
from eval.report import write_report  # noqa: E402
from eval.systems import SystemOutput  # noqa: E402
from eval.systems.compiler import CompilerSystem  # noqa: E402
from eval.systems.rag import RagSystem, build_corpus  # noqa: E402

DEMO = REPO / "data" / "demo" / "generated"
DEFAULT_PG = "postgresql://ec_reader:ec_reader_local_only@localhost:5432/ec_demo"


class CountingLLM:
    def __init__(self, inner):
        self.inner, self.name, self.calls = inner, inner.name, 0

    def model_for(self, tier):
        return getattr(self.inner, "model_for", lambda t: t)(tier)

    def generate(self, **kw):
        self.calls += 1
        return self.inner.generate(**kw)


def setup(work: Path, llm, pg_dsn: str | None) -> AppContext:
    settings = replace(Settings(), data_dir=work, llm_cache=False)
    ctx = AppContext(settings, llm=llm)
    for name in [
        "q1_fy2026_report.pdf",
        "q2_fy2026_report.pdf",
        "regional_sales.csv",
        "customer_segments.xlsx",
    ]:
        ctx.ingest_file(DEMO / name)
    if pg_dsn:
        ctx.register_postgres(pg_dsn, "crm")
    return ctx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", default="A,B,C")
    ap.add_argument("--questions", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--pg-dsn", default=os.getenv("EC_PG_DSN", DEFAULT_PG))
    ap.add_argument("--no-pg", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--fake", action="store_true", help="smoke-test the harness without an LLM")
    args = ap.parse_args()

    if not (DEMO / "ground_truth.json").exists():
        sys.exit("demo data missing: run `make demo-data` first")
    questions = yaml.safe_load((REPO / "eval" / "questions.yaml").read_text())
    if args.questions:
        wanted = set(args.questions.split(","))
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]

    settings = Settings()
    if args.fake:
        from eval.fake import make_eval_fake

        base = make_eval_fake()
    else:
        base = make_llm(replace(settings, llm_cache=False))
        if not args.no_cache:
            base = CachingLLM(base, REPO / "eval" / ".cache", namespace="eval-v1")
    llm = CountingLLM(base)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    work = REPO / "eval" / ".work" / stamp
    pg = None if args.no_pg else args.pg_dsn
    try:
        ctx = setup(work, llm, pg)
    except Exception as exc:  # most likely Postgres is not running
        if pg:
            print(f"warning: Postgres unavailable ({exc}); continuing without the crm source")
            ctx, pg = setup(work / "nopg", llm, None), None
        else:
            raise
    pdf_pages = {
        s.name: {
            n: ctx.repo.page_text(s.id, n)[0] for n in range(1, s.metadata.get("page_count", 0) + 1)
        }
        for s in ctx.repo.list_sources()
        if s.kind == "pdf"
    }
    judge = Judge(llm, build_reference(DEMO, pdf_pages))
    chunks = build_corpus(ctx.repo, DEMO, pg)

    systems = {
        "A": RagSystem(llm, chunks, cite=False),
        "B": RagSystem(llm, chunks, cite=True),
        "C": CompilerSystem(ctx),
    }
    selected = [systems[s] for s in args.systems.split(",") if s in systems]
    scores: list[QuestionScore] = []
    outputs: list[dict] = []
    for q in questions:
        for system in selected:
            print(f"[{system.name}] {q['id']}: {q['question']}")
            before = llm.calls
            try:
                out = system.answer(q["id"], q["question"])
            except Exception as exc:
                traceback.print_exc()
                out = SystemOutput(
                    system=system.name, question_id=q["id"], answer="", error=str(exc)
                )
            out.llm_calls = llm.calls - before
            s = score_deterministic(q, out)
            try:
                s.atomic_claims = judge.decompose(q["question"], out.answer)
                s.verdicts = judge.judge_claims(s.atomic_claims)
                for c in out.citations:
                    s.cited_sentences += 1
                    s.citations_correct += judge.citation_supports(c.sentence, c.evidence_texts)
            except Exception as exc:
                traceback.print_exc()
                s.error = (s.error or "") + f" judge: {exc}"
            scores.append(s)
            outputs.append({"output": asdict(out), "score": asdict(s)})

    summary = {
        name: aggregate([s for s in scores if s.system == name])
        for name in [sy.name for sy in selected]
    }
    meta = {
        "timestamp": stamp,
        "fake": args.fake,
        "strong_model": settings.strong_model,
        "fast_model": settings.fast_model,
        "questions": [q["id"] for q in questions],
        "postgres": bool(pg),
        "total_llm_calls": llm.calls,
    }
    results_dir = REPO / "eval" / "results"
    results_dir.mkdir(exist_ok=True)
    path = results_dir / f"{stamp}{'-fake' if args.fake else ''}.json"
    path.write_text(
        json.dumps({"meta": meta, "summary": summary, "items": outputs}, indent=2, default=str)
    )
    md = write_report(path, meta, summary, scores, questions)
    print(f"\nwrote {path}\nwrote {md}")
    for name, agg in summary.items():
        print(f"{name}: {json.dumps(agg)}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"done in {time.time() - t0:.1f}s")
