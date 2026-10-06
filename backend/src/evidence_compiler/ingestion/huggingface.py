"""Hugging Face dataset connector (via the public datasets-server API; no heavy deps).

Rows are loaded into the local DuckDB store as a table (queried with validated SQL).
Long free-text columns are additionally indexed as PRIMARY passage evidence, one item
per row, so questions about the content can be answered with verbatim quotes.
"""

import json
import re

import httpx
import pandas as pd

from evidence_compiler.core.ids import content_id
from evidence_compiler.core.models import (
    Creator,
    EvidenceItem,
    EvidenceOrigin,
    Source,
    SourceKind,
    TableLocation,
)
from evidence_compiler.ingestion.base import IngestionError, IngestResult, SchemaCard
from evidence_compiler.ingestion.fetch import FetchError
from evidence_compiler.ingestion.tabular import table_name
from evidence_compiler.security.untrusted import scan_for_injection
from evidence_compiler.sql.duckdb_store import TabularStore

SERVER = "https://datasets-server.huggingface.co"
HUB = "https://huggingface.co/api/datasets"
PAGE = 100
TEXT_MIN_MEAN_CHARS = 120
MAX_PASSAGE_CHARS = 6000

_NAME_RE = re.compile(r"^[\w.\-]+(/[\w.\-]+)?$")


def normalize_name(dataset: str) -> str:
    d = dataset.strip()
    m = re.match(r"https?://huggingface\.co/datasets/([\w.\-]+(?:/[\w.\-]+)?)", d)
    if m:
        d = m.group(1)
    if not _NAME_RE.match(d):
        raise FetchError(f"'{dataset}' is not a valid Hugging Face dataset name", 400)
    return d


class HuggingFaceConnector:
    def __init__(
        self,
        store: TabularStore,
        *,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.store = store
        headers = {"User-Agent": "EvidenceCompiler/0.1"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(headers=headers, timeout=60, transport=transport)

    def _get(self, url: str, params: dict | None = None) -> dict:
        try:
            r = self.client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise FetchError(f"could not reach Hugging Face: {exc}", 502) from exc
        if r.status_code in (401, 403):
            raise FetchError(
                "this dataset is gated or private: accept its terms on huggingface.co and "
                "set HF_TOKEN in .env",
                403,
            )
        if r.status_code == 404:
            raise FetchError("dataset, config or split not found on Hugging Face", 404)
        if r.status_code >= 400:
            detail = (
                r.json().get("error", r.text[:200])
                if r.headers.get("content-type", "").startswith("application/json")
                else r.text[:200]
            )
            raise FetchError(f"Hugging Face error {r.status_code}: {detail}", 502)
        return r.json()

    def register(
        self,
        dataset: str,
        *,
        config: str | None = None,
        split: str | None = None,
        max_rows: int = 2000,
    ) -> IngestResult:
        name = normalize_name(dataset)
        info = self._get(f"{HUB}/{name}")
        license_ = (info.get("cardData") or {}).get("license")
        if isinstance(license_, list):
            license_ = ", ".join(license_)

        splits = self._get(f"{SERVER}/splits", {"dataset": name}).get("splits", [])
        if not splits:
            raise IngestionError("the dataset viewer has no splits for this dataset")
        candidates = [s for s in splits if config in (None, s["config"])]
        if split:
            candidates = [s for s in candidates if s["split"] == split]
        if not candidates:
            options = ", ".join(f"{s['config']}/{s['split']}" for s in splits[:20])
            raise FetchError(f"config/split not found; available: {options}", 404)
        chosen = next((s for s in candidates if s["split"] == "train"), candidates[0])
        config, split = chosen["config"], chosen["split"]

        def page_at(offset: int, length: int) -> dict:
            return self._get(
                f"{SERVER}/rows",
                {
                    "dataset": name,
                    "config": config,
                    "split": split,
                    "offset": offset,
                    "length": length,
                },
            )

        # Datasets are often sorted (e.g. by label), so a large split is sampled with
        # evenly spaced pages across the whole split rather than taking the first rows.
        first = page_at(0, min(PAGE, max_rows))
        features: list[dict] = first.get("features", [])
        total = first.get("num_rows_total")
        indexed: dict[int, dict] = {r["row_idx"]: r["row"] for r in first.get("rows", [])}
        target = min(max_rows, total or max_rows)

        def fill_sequentially() -> None:
            offset = 0
            while len(indexed) < target:
                while offset in indexed:
                    offset += 1
                length = min(PAGE, target - len(indexed))
                batch = page_at(offset, length).get("rows", [])
                if not batch:
                    return
                indexed.update({r["row_idx"]: r["row"] for r in batch})
                offset += length

        if total and total > max_rows:
            pages = -(-max_rows // PAGE)  # ceil
            step = total / pages
            for i in range(1, pages):
                if len(indexed) >= target:
                    break
                n = min(PAGE, target - len(indexed))
                off = min(round(i * step), total - n)
                indexed.update({r["row_idx"]: r["row"] for r in page_at(off, n).get("rows", [])})
            fill_sequentially()  # top up if spaced pages overlapped
            sampling = "spread"
        else:
            fill_sequentially()
            sampling = "all" if total and len(indexed) >= total else "head"
        rows = [{"row_idx": i, **indexed[i]} for i in sorted(indexed)][:max_rows]
        if not rows:
            raise IngestionError("the dataset returned no rows")

        df = self._frame(rows, features)
        tname = table_name("hf", name.split("/")[-1], split)
        source_id = content_id("src", "huggingface", name, config, split, len(rows))
        source = Source(
            id=source_id,
            kind=SourceKind.HUGGINGFACE,
            name=f"{name} ({config}/{split})" if config != "default" else f"{name} ({split})",
            uri=f"https://huggingface.co/datasets/{name}",
            content_hash=source_id,
            metadata={
                "url": f"https://huggingface.co/datasets/{name}",
                "dataset": name,
                "config": config,
                "split": split,
                "rows_loaded": len(rows),
                "sampling": sampling,
                "rows_total": total,
                "license": license_,
                "tables": [tname],
            },
        )
        self.store.replace_table(tname, df, source_id)
        result = IngestResult(source=source)
        result.schema_cards.append(
            SchemaCard(
                source_id=source_id,
                target="tabular",
                engine="duckdb",
                table=tname,
                columns=[(c, str(t)) for c, t in df.dtypes.items()],
                row_count=len(df),
                sample_rows=[
                    {k: (str(v)[:200] if isinstance(v, str) else v) for k, v in r.items()}
                    for r in df.head(3).to_dict(orient="records")
                ],
                origin=f"Hugging Face {name} ({config}/{split}, {len(df)} of {total or '?'} rows, "
                f"{sampling} sample; row_idx = dataset row number)",
            )
        )
        text_cols = [
            c
            for c in df.columns
            if (pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object)
            and df[c].dropna().astype(str).str.len().mean() >= TEXT_MIN_MEAN_CHARS
        ]
        other = [c for c in df.columns if c not in text_cols and c != "row_idx"]
        for _, row in df.iterrows():
            i = row["row_idx"]  # the dataset's own row number, for traceability
            for col in text_cols:
                value = row[col]
                if not isinstance(value, str) or not value.strip():
                    continue
                text = " ".join(value.split())[:MAX_PASSAGE_CHARS]
                fields = {c: _scalar(row[c]) for c in other}
                loc = TableLocation(table=tname, row_index=int(i), columns=[col])
                result.evidence.append(
                    EvidenceItem(
                        id=content_id("ev", source_id, loc.model_dump(), text),
                        source_ids=[source_id],
                        origin=EvidenceOrigin.PRIMARY,
                        creator=Creator.CONNECTOR,
                        text=text,
                        fields=fields,
                        location=loc,
                        security_flags=scan_for_injection(text),
                        metadata={"connector": "huggingface", "passage": True, "column": col},
                    )
                )
        source.metadata["text_columns"] = text_cols
        return result

    @staticmethod
    def _frame(rows: list[dict], features: list[dict]) -> pd.DataFrame:
        df = pd.DataFrame(rows)
        for feat in features:
            col, ftype = feat["name"], feat.get("type", {})
            if col not in df.columns:
                continue
            if ftype.get("_type") == "ClassLabel" and ftype.get("names"):
                names = ftype["names"]
                df[f"{col}_name"] = df[col].map(
                    lambda v, n=names: n[v] if isinstance(v, int) and 0 <= v < len(n) else None
                )
            if df[col].map(lambda v: isinstance(v, dict | list)).any():
                df[col] = df[col].map(
                    lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, dict | list) else v
                )
        df.columns = [table_name(str(c)) for c in df.columns]
        return df


def _scalar(v: object) -> object:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v if isinstance(v, int | float | str | bool) else str(v)
