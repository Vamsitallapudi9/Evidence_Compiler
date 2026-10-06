# Data sources

| Source | How to add | Becomes |
|---|---|---|
| PDF | Upload or link | One **primary** evidence item per paragraph and per table row, with page and character span |
| Word (`.docx`), text, Markdown | Upload or link | Paragraph evidence; each top-level heading starts a section |
| Web page | Link | Paragraph evidence from the page's main text (scripts, navigation and footers removed) |
| CSV, Excel | Upload or link | A table in local DuckDB, queried with validated SQL; result rows become evidence |
| PostgreSQL | DSN in the sidebar | Queried read-only at question time; nothing is copied |
| Hugging Face dataset | Name or URL in the sidebar | A DuckDB table, plus passage evidence for long text columns |

## Links

Paste a link in the sidebar, or directly into a question ("What does https://… say
about X?"). Links in a question are fetched first, and the answer then uses **only**
those sources.

- **Fetched server-side:** you never download anything. The snapshot is stored and its
  content hash becomes the source ID, so citations stay valid even if the page later
  changes. The URL and fetch time are recorded on the source.
- **Share links are rewritten to direct downloads:**
  - Google Docs → `.docx` export
  - Google Sheets → CSV
  - Google Drive files
  - GitHub `blob` URLs → raw
  - arXiv abstract pages → PDF
- **Only public `http(s)` links work.** Private, loopback, link-local and LAN
  addresses are refused on every redirect (see [security.md](security.md)). Sign-in
  pages, and pages that need JavaScript to render, can't be read.

## Hugging Face datasets

Enter `owner/name` (or paste the dataset URL), and optionally a config, a split and a
row cap (default 2,000).

- **Fetching:** rows come from the public datasets-server API. Gated or private
  datasets need `HF_TOKEN`.
- **Sampling:** if the split is larger than the cap, rows are sampled **evenly across
  the split** rather than taken from the top. Many datasets are sorted; the first
  1,000 rows of `stanfordnlp/imdb` are all negative reviews.
- **Row numbers:** `row_idx` keeps each row's original number, so evidence points at
  the real dataset row.
- **Class labels** gain a readable `<column>_name` column (e.g. `label_name = pos`).
- **Text columns:** columns averaging 120+ characters are also indexed as passages,
  one per row, that can be searched and quoted.
- **Licence:** the dataset card's licence is shown on the source. Respect it.

## Limits

| Limit | Value |
|---|---|
| Upload / download size | `EC_MAX_UPLOAD_MB` (25 MB) |
| Decompressed size of `.xlsx` / `.docx` | 300 MB, compression ratio ≤ 200 (zip-bomb guard) |
| Rows returned per SQL query | `EC_SQL_MAX_ROWS` (200); the model sees up to 40 per query and is told when results are cut off |
| Links fetched per question | 5 |
| Scanned (image-only) PDFs | Not supported (no OCR) |
