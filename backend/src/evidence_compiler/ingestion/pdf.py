"""PDF connector: one primary evidence item per paragraph and per table row.

The connector builds a *canonical page text* (paragraphs joined by blank lines) and
records every evidence item's character span within it, so the UI can highlight the
exact passage a claim relies on.
"""

from pathlib import Path

import pdfplumber

from evidence_compiler.core.ids import content_id, file_hash
from evidence_compiler.core.models import (
    Creator,
    EvidenceItem,
    EvidenceOrigin,
    PdfLocation,
    Source,
    SourceKind,
)
from evidence_compiler.core.numbers import json_number, to_decimal
from evidence_compiler.ingestion.base import IngestionError, IngestResult
from evidence_compiler.security.untrusted import scan_for_injection


def _inside(line: dict, bbox: tuple[float, float, float, float]) -> bool:
    x0, top, x1, bottom = bbox
    mid = (line["top"] + line["bottom"]) / 2
    return top - 1 <= mid <= bottom + 1 and line["x1"] >= x0 and line["x0"] <= x1


def _paragraphs(lines: list[dict]) -> list[str]:
    paras: list[list[str]] = []
    prev_bottom: float | None = None
    for line in lines:
        height = max(line["bottom"] - line["top"], 1.0)
        if prev_bottom is None or line["top"] - prev_bottom > 0.6 * height:
            paras.append([])
        paras[-1].append(line["text"].strip())
        prev_bottom = line["bottom"]
    return [" ".join(p).strip() for p in paras if " ".join(p).strip()]


class _PageText:
    """Accumulates the canonical page text, returning each part's character span."""

    def __init__(self) -> None:
        self.text = ""

    def add(self, part: str) -> tuple[int, int]:
        if self.text:
            self.text += "\n\n"
        start = len(self.text)
        self.text += part
        return start, len(self.text)


def _clean_cell(cell: object) -> str:
    return " ".join(str(cell).split()) if cell is not None else ""


class PdfConnector:
    def ingest(self, path: Path, *, name: str) -> IngestResult:
        data = path.read_bytes()
        source_id = content_id("src", "pdf", file_hash(data))
        source = Source(
            id=source_id,
            kind=SourceKind.PDF,
            name=name,
            uri=str(path),
            content_hash=file_hash(data),
        )
        result = IngestResult(source=source)
        try:
            pdf = pdfplumber.open(path)
        except Exception as exc:  # pdfplumber raises several unrelated types
            raise IngestionError(f"could not open PDF: {exc}") from exc

        with pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                tables = page.find_tables()
                bboxes = [t.bbox for t in tables]
                lines = [
                    ln
                    for ln in page.extract_text_lines()
                    if not any(_inside(ln, b) for b in bboxes)
                ]
                page_text = _PageText()
                add = page_text.add

                for para in _paragraphs(lines):
                    start, end = add(para)
                    result.evidence.append(
                        self._item(
                            source_id,
                            para,
                            PdfLocation(page=page_no, char_start=start, char_end=end),
                        )
                    )

                for t_idx, table in enumerate(tables):
                    rows = [[_clean_cell(c) for c in row] for row in table.extract() if row]
                    if len(rows) < 2:
                        continue
                    header = [h or f"col{i}" for i, h in enumerate(rows[0])]
                    for r_idx, row in enumerate(rows[1:]):
                        if not any(row):
                            continue
                        text = " | ".join(f"{h}: {v}" for h, v in zip(header, row, strict=False))
                        fields: dict[str, object] = {}
                        for h, v in zip(header, row, strict=False):
                            num = to_decimal(v)
                            fields[h] = json_number(num) if num is not None else v
                        start, end = add(text)
                        result.evidence.append(
                            self._item(
                                source_id,
                                text,
                                PdfLocation(
                                    page=page_no,
                                    char_start=start,
                                    char_end=end,
                                    table_index=t_idx,
                                    row_index=r_idx,
                                ),
                                fields=fields,
                            )
                        )
                result.pages[page_no] = page_text.text
            source.metadata["page_count"] = len(pdf.pages)

        if not result.evidence:
            raise IngestionError("no extractable text (scanned PDFs need OCR, not supported yet)")
        return result

    @staticmethod
    def _item(
        source_id: str, text: str, loc: PdfLocation, fields: dict | None = None
    ) -> EvidenceItem:
        return EvidenceItem(
            id=content_id("ev", source_id, loc.model_dump(), text),
            source_ids=[source_id],
            origin=EvidenceOrigin.PRIMARY,
            creator=Creator.CONNECTOR,
            text=text,
            fields=fields or {},
            location=loc,
            security_flags=scan_for_injection(text),
            metadata={"connector": "pdf"},
        )
