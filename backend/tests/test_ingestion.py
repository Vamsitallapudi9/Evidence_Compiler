from evidence_compiler.core.models import Creator, EvidenceOrigin, SourceKind


def test_pdf_evidence_offsets_index_canonical_page_text(ctx):
    pdf = next(s for s in ctx.repo.list_sources() if s.name == "q2_fy2026_report.pdf")
    items = [e for e in ctx.repo.all_evidence() if pdf.id in e.source_ids]
    assert items and all(e.origin == EvidenceOrigin.PRIMARY for e in items)
    assert all(e.creator == Creator.CONNECTOR for e in items)
    for e in items:
        page_text, _ = ctx.repo.page_text(pdf.id, e.location.page)
        assert page_text[e.location.char_start : e.location.char_end] == e.text


def test_pdf_tables_become_structured_rows(ctx):
    rows = [e for e in ctx.repo.all_evidence() if e.location.kind == "pdf" and e.fields]
    europe = next(e for e in rows if e.fields.get("Region") == "Europe" and "Q2 FY2026" in e.fields)
    assert europe.fields["Q2 FY2026"] == 34_200_000


def test_prompt_injection_is_flagged(ctx):
    flagged = [e for e in ctx.repo.all_evidence() if e.security_flags]
    assert any("ignore all previous instructions" in e.text for e in flagged)


def test_tabular_sources_produce_schema_cards(ctx):
    cards = {c.table: c for c in ctx.repo.schema_cards()}
    assert {"regional_sales", "customer_segments_segments", "customer_segments_industries"} <= set(
        cards
    )
    assert ("revenue_usd", "int64") in cards["regional_sales"].columns
    kinds = {s.kind for s in ctx.repo.list_sources()}
    assert {SourceKind.PDF, SourceKind.CSV, SourceKind.XLSX} <= kinds


def test_reingesting_is_idempotent(ctx, demo_dir):
    before = len(ctx.repo.all_evidence())
    ctx.ingest_file(demo_dir / "q2_fy2026_report.pdf")
    assert len(ctx.repo.all_evidence()) == before


def test_bm25_finds_relevant_passage(ctx):
    hits = ctx.retriever.search("total revenue second quarter decrease", 3)
    assert any("8.4%" in h.item.text for h in hits)
