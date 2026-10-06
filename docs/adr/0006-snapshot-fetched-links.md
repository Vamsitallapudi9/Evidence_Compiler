# ADR 0006: Fetched links are snapshotted and become ordinary sources

**Status:** accepted

**Context.** Users want to ask about a web page or a shared document without
downloading it. But evidence must stay stable: a citation to a page that later changes
would silently stop being true.

**Decision.** The server fetches the link (with SSRF guards), stores the bytes, and
ingests them through the normal connector for that content type. The source ID is the
content hash, and the URL and fetch time are recorded. Links pasted into a question are
fetched first, and that run answers only from them.

**Consequences.** Citations keep pointing at exactly what was read. Re-fetching a
changed page creates a new source rather than mutating the old one. Pages that render
with JavaScript, or need a sign-in, aren't supported.
