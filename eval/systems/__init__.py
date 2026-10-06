"""Systems under evaluation. Each returns a SystemOutput for a question."""

from dataclasses import dataclass, field


@dataclass
class Citation:
    sentence: str
    evidence_texts: list[str]
    source_names: list[str]


@dataclass
class SystemOutput:
    system: str
    question_id: str
    answer: str  # plain prose, markers stripped
    citations: list[Citation] = field(default_factory=list)
    abstained: bool = False
    seconds: float = 0.0
    llm_calls: int = 0
    internal: dict = field(default_factory=dict)  # system-specific diagnostics
    error: str | None = None
