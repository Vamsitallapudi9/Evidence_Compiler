# ADR 0007: Meter every model call and make liveness observable

**Status:** accepted

**Context.** A run can take minutes and dozens of model calls. Without feedback, a
slow-but-working run looks the same as a dead one. In practice, a server restart
silently orphaned runs that showed "running" forever.

**Decision.** Wrap the model client per run (`MeteredLLM`). Record every call's start
and end, with tokens and duration, and stream them along with periodic heartbeats. Give
each call a timeout. Allow cancellation at step boundaries. On startup, mark runs left
unfinished by a previous process as interrupted.

**Consequences.** The UI can tell "working", "slow", "stuck", "not running" and "lost
connection" apart, and show token usage live. Cancelling doesn't abort an in-flight
HTTP call; it stops before the next one.
