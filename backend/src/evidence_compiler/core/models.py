"""Core domain model: sources, evidence, calculations, claims, answers.

Evidence is a first-class object. Two rules shape this module:

* Only connectors and the SQL executor create PRIMARY evidence; only the calculation
  engine and the SQL executor create DERIVED evidence. There is deliberately no
  ``Creator`` value for the LLM, so model output can never be stored as evidence.
* Claims never carry facts of their own: they *reference* evidence by ID.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


class SourceKind(StrEnum):
    PDF = "pdf"
    CSV = "csv"
    XLSX = "xlsx"
    POSTGRES = "postgres"
    WEB = "web"
    DOCX = "docx"
    TEXT = "text"
    HUGGINGFACE = "huggingface"


class Source(BaseModel):
    id: str
    kind: SourceKind
    name: str
    uri: str
    content_hash: str
    ingested_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Locations -------------------------------------------------------------------------


class PdfLocation(BaseModel):
    kind: Literal["pdf"] = "pdf"
    page: int  # 1-indexed
    char_start: int  # offsets into the canonical page text served by the API
    char_end: int
    table_index: int | None = None
    row_index: int | None = None


class TextLocation(BaseModel):
    """A span in a text document (web page, Word doc, text file); ``page`` is a section."""

    kind: Literal["text"] = "text"
    page: int = 1
    char_start: int
    char_end: int


class TableLocation(BaseModel):
    kind: Literal["table"] = "table"
    table: str
    sheet: str | None = None
    row_index: int
    columns: list[str] = Field(default_factory=list)


class QueryLocation(BaseModel):
    kind: Literal["query"] = "query"
    engine: Literal["duckdb", "postgres"]
    sql: str
    tables: list[str]
    executed_at: datetime = Field(default_factory=utcnow)
    row_count: int
    row_index: int


class CalcLocation(BaseModel):
    kind: Literal["calc"] = "calc"
    calculation_id: str


Location = Annotated[
    PdfLocation | TextLocation | TableLocation | QueryLocation | CalcLocation,
    Field(discriminator="kind"),
]


# --- Evidence --------------------------------------------------------------------------


class EvidenceOrigin(StrEnum):
    PRIMARY = "primary"
    DERIVED = "derived"


class Creator(StrEnum):
    """Who minted an evidence item. Intentionally has no LLM member."""

    CONNECTOR = "connector"
    SQL = "sql"
    CALC = "calc"


Scalar = bool | int | float | str | None


class EvidenceItem(BaseModel):
    id: str
    source_ids: list[str]
    origin: EvidenceOrigin
    creator: Creator
    text: str
    fields: dict[str, Scalar] = Field(default_factory=dict)
    location: Location
    derived_from: list[str] = Field(default_factory=list)
    calculation_id: str | None = None
    security_flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Calculations ----------------------------------------------------------------------


class CalcOp(StrEnum):
    DIFFERENCE = "difference"
    PCT_CHANGE = "pct_change"
    RATIO = "ratio"
    SHARE_OF_TOTAL = "share_of_total"
    SUM = "sum"
    MEAN = "mean"


class ResolvedInput(BaseModel):
    name: str
    evidence_id: str
    field: str | None = None
    quote: str | None = None
    value: Decimal
    unit: str | None = None


class Calculation(BaseModel):
    id: str
    op: CalcOp
    inputs: list[ResolvedInput]
    result: Decimal
    unit: str | None = None
    formula: str
    output_evidence_id: str


# --- Claims ----------------------------------------------------------------------------


class ClaimType(StrEnum):
    PRIMARY = "primary"
    DERIVED = "derived"
    INTERPRETATION = "interpretation"
    UNSUPPORTED = "unsupported"


class ClaimStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    REJECTED = "rejected"  # failed an integrity check, e.g. a fabricated evidence ID


class Relation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    CALCULATED_FROM = "calculated_from"
    INFERRED_FROM = "inferred_from"
    DEPENDS_ON = "depends_on"
    SUPERSEDES = "supersedes"


class EvidenceLink(BaseModel):
    evidence_id: str
    relation: Relation
    quote: str | None = None
    quote_span: tuple[int, int] | None = None  # offsets into the evidence text


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class Claim(BaseModel):
    id: str
    text: str
    type: ClaimType
    status: ClaimStatus
    links: list[EvidenceLink] = Field(default_factory=list)
    calculation_id: str | None = None
    checks: list[CheckResult] = Field(default_factory=list)
    entailment: Literal["supports", "partial", "does_not_support"] | None = None
    entailment_note: str | None = None  # model-written; displayed as such, never evidence
    reason: str = ""
    origin: Literal["answer", "hypothesis"] = "answer"


# --- Graph & answer --------------------------------------------------------------------


class GraphNode(BaseModel):
    id: str
    kind: Literal["question", "claim", "evidence", "calculation", "source"]
    label: str
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str


class EvidenceGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class Answer(BaseModel):
    run_id: str
    question: str
    text: str  # prose with [c:<claim_id>] markers
    insufficient: bool = False
    claims: list[Claim]
    gaps: list[str] = Field(default_factory=list)
    evidence: dict[str, EvidenceItem] = Field(default_factory=dict)
    calculations: dict[str, Calculation] = Field(default_factory=dict)
    sources: dict[str, Source] = Field(default_factory=dict)
    graph: EvidenceGraph = Field(default_factory=EvidenceGraph)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunEvent(BaseModel):
    stage: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)
