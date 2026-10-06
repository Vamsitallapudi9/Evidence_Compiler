"""Per-run metering of model calls: live token totals, in-flight calls, cancellation.

The pipeline talks to a ``MeteredLLM`` that wraps the real client. Every call is
recorded (start and end) and reported through a callback, which the run manager turns
into live UI updates. Cancellation is checked before each call.
"""

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field

from evidence_compiler.config import Settings
from evidence_compiler.core.ids import random_id
from evidence_compiler.core.models import utcnow
from evidence_compiler.llm.base import LLMClient, LLMError, T, Tier, generate_with_usage

TASK_LABELS = {
    "plan": "Planning the question",
    "sql": "Writing SQL queries",
    "sql_repair": "Repairing a rejected SQL query",
    "claims": "Drafting claims from the evidence",
    "verify": "Verifying a claim",
    "compile": "Writing the final answer",
}


class RunCancelled(Exception):
    pass


@dataclass
class LlmCall:
    id: str
    task: str
    label: str
    model: str
    status: str  # running | ok | error | cached
    started_at: str
    seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_input_tokens: int | None = None
    error: str | None = None
    _t0: float = field(default=0.0, repr=False)

    def public(self) -> dict:
        d = asdict(self)
        d.pop("_t0")
        return d


class MeteredLLM:
    def __init__(
        self,
        inner: LLMClient,
        settings: Settings,
        *,
        on_call: Callable[[LlmCall], None] | None = None,
        cancel: threading.Event | None = None,
    ):
        self.inner = inner
        self.name = inner.name
        self.settings = settings
        self.on_call = on_call
        self.cancel = cancel or threading.Event()
        self.calls: list[LlmCall] = []
        self._lock = threading.Lock()
        self._local = threading.local()

    def model_for(self, tier: Tier) -> str:
        return getattr(self.inner, "model_for", lambda t: t)(tier)

    @contextmanager
    def activity(self, label: str) -> Iterator[None]:
        """Label calls made inside this block (per thread), e.g. 'Verifying claim 3 of 20'."""
        prev = getattr(self._local, "label", None)
        self._local.label = label
        try:
            yield
        finally:
            self._local.label = prev

    def check_cancelled(self) -> None:
        if self.cancel.is_set():
            raise RunCancelled("Run cancelled by user")

    def generate(
        self, *, task: str, system: str, prompt: str, schema: type[T], tier: Tier = "strong"
    ) -> T:
        self.check_cancelled()
        call = LlmCall(
            id=random_id("call"),
            task=task,
            label=getattr(self._local, "label", None) or TASK_LABELS.get(task, task),
            model=self.model_for(tier),
            status="running",
            started_at=utcnow().isoformat(),
            _t0=time.monotonic(),
        )
        with self._lock:
            self.calls.append(call)
        self._report(call)
        try:
            result, usage = generate_with_usage(
                self.inner, task=task, system=system, prompt=prompt, schema=schema, tier=tier
            )
        except LLMError as exc:
            call.status, call.error = "error", str(exc)
            call.seconds = round(time.monotonic() - call._t0, 2)
            self._report(call)
            raise
        call.seconds = round(time.monotonic() - call._t0, 2)
        if usage is not None:
            call.model = usage.model or call.model
            call.status = "cached" if usage.cached else "ok"
            call.input_tokens = usage.input_tokens
            call.output_tokens = usage.output_tokens
            call.reasoning_tokens = usage.reasoning_tokens
            call.cached_input_tokens = usage.cached_input_tokens
        else:
            call.status = "ok"
        self._report(call)
        return result

    def _report(self, call: LlmCall) -> None:
        if self.on_call:
            self.on_call(call)

    def summary(self, *, include_log: bool = False) -> dict:
        with self._lock:
            calls = list(self.calls)
        done = [c for c in calls if c.status != "running"]
        models = sorted({c.model for c in calls}) or sorted(
            {self.model_for("strong"), self.model_for("fast")}
        )
        tin = sum(c.input_tokens or 0 for c in calls)
        tout = sum(c.output_tokens or 0 for c in calls)
        s = self.settings
        cost = None
        if s.price_input_per_m is not None and s.price_output_per_m is not None:
            cost = round(tin / 1e6 * s.price_input_per_m + tout / 1e6 * s.price_output_per_m, 4)
        out = {
            "provider": s.llm_provider,
            "model": " + ".join(models),
            "calls": len(calls),  # every call started (incl. in-flight / failed / cached)
            "in_flight": len(calls) - len(done),
            "failed_calls": sum(c.status == "error" for c in calls),
            "cache_hits": sum(c.status == "cached" for c in calls),
            "input_tokens": tin,
            "output_tokens": tout,
            "reasoning_tokens": sum(c.reasoning_tokens or 0 for c in calls),
            "cached_input_tokens": sum(c.cached_input_tokens or 0 for c in calls),
            "est_cost_usd": cost,
        }
        if include_log:
            out["calls_log"] = [c.public() for c in calls]
        return out

    def current(self) -> LlmCall | None:
        with self._lock:
            running = [c for c in self.calls if c.status == "running"]
        return running[-1] if running else None
