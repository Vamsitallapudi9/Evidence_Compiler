# Security policy

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Use GitHub's private
reporting instead: **Security → Report a vulnerability** on this repository. Include
steps to reproduce, the impact you expect, and any proof of concept. You can expect an
acknowledgement within 7 days.

## Supported versions

Only the latest commit on `main` is supported. This is a pre-1.0 research project with no
backported fixes.

## Scope

Evidence Compiler is designed as a **single-user tool running on your own machine**. It
has no authentication, by design; running it on a shared network is out of scope. The
full threat model, mitigations and known non-goals are in
[docs/security.md](docs/security.md). In-scope examples:

- getting model output stored as evidence, or bypassing the provenance checks
- SQL that gets past validation and modifies data or reads files
- SSRF past the link-fetch guard (other than DNS rebinding, a documented limitation)
- leaking API keys or DSNs through the API or the UI
- code execution through crafted uploads or fetched content
