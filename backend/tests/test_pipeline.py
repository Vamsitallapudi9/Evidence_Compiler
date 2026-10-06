from evidence_compiler.core.invariants import GraphValidator
from evidence_compiler.core.models import ClaimStatus, ClaimType
from evidence_compiler.pipeline.compiler import MARKER_RE, postcheck, split_sentences
from evidence_compiler.pipeline.orchestrator import Pipeline, PipelineOptions
from tests.fake_scenario import make_fake


def run(ctx, options=None):
    fake = make_fake()
    pipe = Pipeline(fake, ctx.repo, ctx.retriever, ctx.executor, ctx.settings, options)
    events = []
    answer = pipe.run("Why did Q2 revenue decline?", run_id="run_test", emit=events.append)
    return answer, events, fake


def by_text(answer, prefix):
    return next(c for c in answer.claims if c.text.startswith(prefix))


def test_end_to_end_claim_statuses(ctx):
    answer, events, _ = run(ctx)

    headline = by_text(answer, "Q2 revenue declined 8.4%")
    assert (headline.type, headline.status) == (ClaimType.PRIMARY, ClaimStatus.SUPPORTED)
    assert headline.links[0].quote_span is not None

    europe = by_text(answer, "Europe accounted")
    assert (europe.type, europe.status) == (ClaimType.DERIVED, ClaimStatus.SUPPORTED)
    calc = answer.calculations[europe.calculation_id]
    assert round(float(calc.result)) == 71

    enterprise = by_text(answer, "Enterprise revenue fell")
    assert enterprise.status == ClaimStatus.SUPPORTED and enterprise.type == ClaimType.DERIVED

    interp = by_text(answer, "Europe appears")
    assert interp.type == ClaimType.INTERPRETATION and interp.status == ClaimStatus.SUPPORTED

    fabricated = by_text(answer, "Revenue declined because")
    assert fabricated.status == ClaimStatus.REJECTED
    assert "ev_doesnotexist" in fabricated.reason

    wrong = by_text(answer, "Q2 revenue declined 12%")
    assert wrong.status == ClaimStatus.UNSUPPORTED
    assert any(c.name == "numbers_backed" and not c.passed for c in wrong.checks)

    healthcare = by_text(answer, "Healthcare customers")
    assert healthcare.origin == "hypothesis" and healthcare.status == ClaimStatus.UNSUPPORTED

    stages = {e.stage for e in events}
    assert {"plan", "retrieve", "sql", "claims", "verify", "compile", "done"} <= stages


def test_answer_text_only_contains_marked_supported_sentences(ctx):
    answer, _, _ = run(ctx)
    supported = {c.id for c in answer.claims if c.status in ("supported", "partial")}
    hypothesis = {c.id for c in answer.claims if c.origin == "hypothesis"}
    for sentence in split_sentences(answer.text):
        ids = set(MARKER_RE.findall(sentence))
        assert ids and ids <= supported | hypothesis, sentence
    assert "50% worse" not in answer.text
    removed = [w for w in answer.warnings if "Removed sentence" in w]
    assert len(removed) == 1 and "50% worse" in removed[0]  # LLM prose kept, stray dropped
    rejected = {c.id for c in answer.claims if c.status in ("rejected", "unsupported")} - hypothesis
    assert not rejected & set(MARKER_RE.findall(answer.text))


def test_every_supported_claim_has_valid_provenance(ctx):
    answer, _, _ = run(ctx)
    sources = {s.id: s for s in ctx.repo.list_sources()}
    validator = GraphValidator(answer.evidence, sources)
    for claim in answer.claims:
        if claim.status == ClaimStatus.SUPPORTED:
            assert validator.claim_violations(claim) == [], claim.text


def test_graph_links_claims_to_sources(ctx):
    answer, _, _ = run(ctx)
    kinds = {n.kind for n in answer.graph.nodes}
    assert kinds == {"question", "claim", "evidence", "calculation", "source"}
    relations = {e.relation for e in answer.graph.edges}
    assert {"calculated_from", "from_source", "supports"} <= relations


def test_unsafe_sql_is_rejected_and_repaired(ctx):
    answer, events, fake = run(ctx)
    assert any(e.stage == "sql" and "Rejected query" in e.message for e in events)
    assert any(c.task == "sql_repair" for c in fake.calls)


def test_verifier_sees_only_cited_evidence(ctx):
    _, _, fake = run(ctx)
    verify_calls = [c for c in fake.calls if c.task == "verify"]
    claims_call = next(c for c in fake.calls if c.task == "claims")
    assert verify_calls
    for call in verify_calls:
        assert call.prompt.count("<evidence ") < claims_call.prompt.count("<evidence ")


def test_minted_evidence_is_persisted(ctx):
    answer, _, _ = run(ctx)
    europe = by_text(answer, "Europe accounted")
    calc = answer.calculations[europe.calculation_id]
    assert ctx.repo.get_evidence(calc.output_evidence_id) is not None


def test_ablation_without_enforcement_lets_bad_claims_through(ctx):
    answer, _, _ = run(ctx, PipelineOptions(enforce_checks=False, verify_entailment=False))
    wrong = by_text(answer, "Q2 revenue declined 12%")
    assert wrong.status == ClaimStatus.SUPPORTED  # shows what the checks are protecting


def test_postcheck_drops_unknown_markers_and_stray_numbers():
    from evidence_compiler.core.models import Claim

    c = Claim(id="clm_a", text="Revenue fell 8.4%.", type="primary", status="supported")
    text, warnings = postcheck(
        "Revenue fell 8.4% [c:clm_a]. It fell 9% [c:clm_a]. Hi [c:zzz].", [c]
    )
    assert text == "Revenue fell 8.4% [c:clm_a]."
    assert len(warnings) == 2


def test_no_sources_gives_insufficient_answer(settings):
    from evidence_compiler.app import AppContext

    empty = AppContext(settings, llm=make_fake())
    answer = empty.pipeline().run("Anything?", run_id="r")
    assert answer.insufficient and answer.text == "Insufficient evidence available."


def test_postcheck_accepts_markers_after_punctuation():
    from evidence_compiler.core.models import Claim

    a = Claim(id="clm_a", text="Revenue fell 8.4%.", type="primary", status="supported")
    b = Claim(id="clm_b", text="Europe drove 71%.", type="derived", status="supported")
    text, warnings = postcheck("Revenue fell 8.4%. [c:clm_a] Europe drove 71%.[c:clm_b]", [a, b])
    assert text == "Revenue fell 8.4% [c:clm_a]. Europe drove 71% [c:clm_b]."
    assert warnings == []


def test_markers_numbered_prefixless_and_lists_are_canonicalized():
    from evidence_compiler.core.models import Claim

    a = Claim(id="clm_aa11", text="Revenue was $114.0 million.", type="primary", status="supported")
    b = Claim(id="clm_bb22", text="It fell 8.4%.", type="primary", status="supported")
    text, warnings = postcheck(
        "Revenue was $114.0 million [c:1]. It fell 8.4% [c:aa11, c:2]. Also 8.4% [c:2,1].", [a, b]
    )
    assert warnings == []
    assert text == (
        "Revenue was $114.0 million [c:clm_aa11]. It fell 8.4% [c:clm_aa11] [c:clm_bb22]. "
        "Also 8.4% [c:clm_bb22] [c:clm_aa11]."
    )


def test_truncated_query_results_are_flagged_to_the_model(ctx):
    answer, _, fake = run(ctx, PipelineOptions(max_rows_per_query=2))
    claims_prompt = next(c for c in fake.calls if c.task == "claims").prompt
    assert (
        "Query notes:" in claims_prompt
        and "Absence from the shown rows proves nothing" in claims_prompt
    )
    assert any("only the first 2" in w for w in answer.warnings)


def test_claim_type_is_reclassified_from_evidence(ctx):
    """A model calling an SQL-aggregate fact 'primary' is relabelled, not rejected."""
    from evidence_compiler.pipeline.schemas import DraftCitation, DraftClaim
    from evidence_compiler.pipeline.verification import check_draft, classify

    result = ctx.executor.run(
        "tabular",
        "SELECT region, SUM(revenue_usd) AS revenue_usd FROM regional_sales "
        "WHERE quarter = '2026-Q2' GROUP BY region",
        ctx.repo.schema_cards(),
    )
    europe = next(e for e in result.evidence if e.fields["region"] == "Europe")
    pool = {e.id: e for e in result.evidence}
    sources = {s.id: s for s in ctx.repo.list_sources()}
    work = check_draft(
        DraftClaim(
            text="Europe Q2 revenue was $34.2 million.",
            claim_type="primary",
            citations=[DraftCitation(evidence_id=europe.id)],
        ),
        pool,
        sources,
    )
    claim = classify(work, None)
    assert claim.status == ClaimStatus.SUPPORTED and claim.type == ClaimType.DERIVED
    assert any(c.name == "type_from_evidence" for c in claim.checks)
