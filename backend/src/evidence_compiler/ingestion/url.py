"""Ingest a source from a link: fetch a snapshot, then route to the right connector."""

import re
from pathlib import Path

from evidence_compiler.core.ids import file_hash
from evidence_compiler.core.models import utcnow
from evidence_compiler.ingestion.base import IngestionError, IngestResult
from evidence_compiler.ingestion.documents import ingest_docx, ingest_html, ingest_text
from evidence_compiler.ingestion.fetch import Fetched, FetchError, fetch
from evidence_compiler.ingestion.pdf import PdfConnector
from evidence_compiler.ingestion.tabular import TabularConnector

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def find_urls(text: str) -> list[str]:
    return list(dict.fromkeys(u.rstrip(".,;:!?") for u in URL_RE.findall(text)))


def _kind(f: Fetched) -> str:
    ct, name, data = f.content_type, f.filename.lower(), f.data[:1024]
    if ct == "application/pdf" or data.startswith(b"%PDF") or name.endswith(".pdf"):
        return "pdf"
    if ct == _DOCX or name.endswith(".docx"):
        return "docx"
    if ct == _XLSX or name.endswith(".xlsx"):
        return "xlsx"
    if ct in ("text/csv", "application/csv") or name.endswith(".csv"):
        return "csv"
    if ct in ("text/html", "application/xhtml+xml") or b"<html" in data.lower():
        return "html"
    if ct.startswith("text/") or name.endswith((".txt", ".md")):
        return "text"
    raise FetchError(f"unsupported content type '{ct or 'unknown'}'", 415)


def _display_name(f: Fetched, fallback_ext: str) -> str:
    name = re.sub(r"[^\w.\- ]+", "_", f.filename)[:120] or "link"
    if "." not in name:
        name = f"{name}.{fallback_ext}"
    return name


class UrlIngestor:
    def __init__(
        self,
        uploads_dir: Path,
        tabular: TabularConnector,
        *,
        max_bytes: int,
        allow_private: bool = False,
        transport=None,
    ):
        self.uploads_dir = uploads_dir
        self.tabular = tabular
        self.max_bytes = max_bytes
        self.allow_private = allow_private
        self.transport = transport

    def ingest(self, url: str, name: str | None = None) -> IngestResult:
        f = fetch(
            url,
            max_bytes=self.max_bytes,
            allow_private=self.allow_private,
            transport=self.transport,
        )
        kind = _kind(f)
        meta = {
            "url": f.url,
            "final_url": f.final_url,
            "fetched_at": utcnow().isoformat(),
            "content_type": f.content_type,
        }
        if kind == "html":
            result = ingest_html(f.data, name=name, url=f.url, metadata=meta)
        elif kind == "docx":
            result = ingest_docx(
                f.data, name=name or _display_name(f, "docx"), uri=f.url, metadata=meta
            )
        elif kind == "text":
            result = ingest_text(
                f.data, name=name or _display_name(f, "txt"), uri=f.url, metadata=meta
            )
        else:
            # Binary formats reuse the file connectors on a stored snapshot.
            fname = name or _display_name(f, kind)
            if not fname.lower().endswith(f".{kind}"):
                fname = f"{fname}.{kind}"
            snap = self.uploads_dir / f"link_{file_hash(f.data)[:12]}_{Path(fname).name}"
            snap.write_bytes(f.data)
            if kind == "pdf":
                result = PdfConnector().ingest(snap, name=fname)
            else:
                result = self.tabular.ingest(snap, name=fname)
            result.source.metadata.update(meta)
            result.source.uri = f.url
        if not result.evidence and not result.schema_cards:
            raise IngestionError("nothing could be extracted from the link")
        return result
