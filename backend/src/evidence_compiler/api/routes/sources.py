import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from evidence_compiler.api.deps import get_ctx
from evidence_compiler.app import AppContext
from evidence_compiler.core.models import Source, SourceKind
from evidence_compiler.ingestion.base import IngestionError
from evidence_compiler.ingestion.fetch import FetchError
from evidence_compiler.ingestion.registry import ALLOWED_SUFFIXES

router = APIRouter(tags=["sources"])


class SourceOut(BaseModel):
    id: str
    kind: SourceKind
    name: str
    ingested_at: datetime
    evidence_count: int
    tables: list[str]
    flagged_count: int
    page_count: int | None = None
    url: str | None = None
    license: str | None = None
    fetched_at: str | None = None


class UrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    name: str | None = None


class HuggingFaceIn(BaseModel):
    dataset: str = Field(min_length=1, max_length=200)
    config: str | None = None
    split: str | None = None
    max_rows: int = Field(default=2000, ge=1, le=100_000)


class PostgresIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    dsn: str
    db_schema: str = Field(default="public", alias="schema")


class PageOut(BaseModel):
    page: int
    text: str
    page_count: int


def _out(ctx: AppContext, s: Source, counts: dict, flagged: dict) -> SourceOut:
    return SourceOut(
        id=s.id,
        kind=s.kind,
        name=s.name,
        ingested_at=s.ingested_at,
        evidence_count=counts.get(s.id, 0),
        tables=s.metadata.get("tables", []),
        flagged_count=flagged.get(s.id, 0),
        page_count=s.metadata.get("page_count"),
        url=s.metadata.get("url"),
        license=s.metadata.get("license"),
        fetched_at=s.metadata.get("fetched_at"),
    )


@router.get("/sources", response_model=list[SourceOut])
def list_sources(ctx: AppContext = Depends(get_ctx)) -> list[SourceOut]:
    counts, flagged = ctx.repo.evidence_counts(), ctx.repo.flagged_counts()
    return [_out(ctx, s, counts, flagged) for s in ctx.repo.list_sources()]


@router.post("/sources", response_model=SourceOut, status_code=201)
async def upload_source(file: UploadFile, ctx: AppContext = Depends(get_ctx)) -> SourceOut:
    name = Path(file.filename or "upload").name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            400, f"Unsupported file type '{suffix}'. Allowed: pdf, csv, xlsx, docx, txt, md."
        )
    limit = ctx.settings.max_upload_mb * 1024 * 1024
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(1024 * 1024):  # bounded read: never buffer past the limit
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"File exceeds {ctx.settings.max_upload_mb} MB limit.")
        chunks.append(chunk)
    data = b"".join(chunks)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    path = ctx.settings.uploads_dir / safe
    path.write_bytes(data)
    try:
        source = ctx.ingest_file(path, name=name)
    except IngestionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _out(ctx, source, ctx.repo.evidence_counts(), ctx.repo.flagged_counts())


@router.post("/sources/postgres", response_model=SourceOut, status_code=201)
def add_postgres(body: PostgresIn, ctx: AppContext = Depends(get_ctx)) -> SourceOut:
    try:
        source = ctx.register_postgres(body.dsn, body.name, body.db_schema)
    except IngestionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _out(ctx, source, ctx.repo.evidence_counts(), ctx.repo.flagged_counts())


@router.post("/sources/url", response_model=SourceOut, status_code=201)
def add_url(body: UrlIn, ctx: AppContext = Depends(get_ctx)) -> SourceOut:
    try:
        source = ctx.ingest_url(body.url, body.name)
    except FetchError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except IngestionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _out(ctx, source, ctx.repo.evidence_counts(), ctx.repo.flagged_counts())


@router.post("/sources/huggingface", response_model=SourceOut, status_code=201)
def add_huggingface(body: HuggingFaceIn, ctx: AppContext = Depends(get_ctx)) -> SourceOut:
    try:
        source = ctx.register_huggingface(
            body.dataset, body.config or None, body.split or None, body.max_rows
        )
    except FetchError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except IngestionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _out(ctx, source, ctx.repo.evidence_counts(), ctx.repo.flagged_counts())


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    if not ctx.delete_source(source_id):
        raise HTTPException(404, "Source not found")
    return Response(status_code=204)


@router.get("/sources/{source_id}/pages/{page}", response_model=PageOut)
def get_page(source_id: str, page: int, ctx: AppContext = Depends(get_ctx)) -> PageOut:
    found = ctx.repo.page_text(source_id, page)
    if found is None:
        raise HTTPException(404, "Page not found")
    text, count = found
    return PageOut(page=page, text=text, page_count=count)
