"""Maps file types to connectors. New connectors register here without core changes."""

from pathlib import Path

from evidence_compiler.ingestion.base import Connector, IngestionError
from evidence_compiler.ingestion.documents import DocxConnector, TextConnector
from evidence_compiler.ingestion.pdf import PdfConnector
from evidence_compiler.ingestion.tabular import TabularConnector
from evidence_compiler.sql.duckdb_store import TabularStore

ALLOWED_SUFFIXES = {".pdf", ".csv", ".xlsx", ".docx", ".txt", ".md"}


class ConnectorRegistry:
    def __init__(self, store: TabularStore):
        tabular = TabularConnector(store)
        self.tabular = tabular
        self._by_suffix: dict[str, Connector] = {
            ".pdf": PdfConnector(),
            ".csv": tabular,
            ".xlsx": tabular,
            ".docx": DocxConnector(),
            ".txt": TextConnector(),
            ".md": TextConnector(),
        }

    def register(self, suffix: str, connector: Connector) -> None:
        self._by_suffix[suffix.lower()] = connector

    def for_path(self, path: Path) -> Connector:
        try:
            return self._by_suffix[path.suffix.lower()]
        except KeyError:
            raise IngestionError(f"unsupported file type: {path.suffix or '(none)'}") from None
