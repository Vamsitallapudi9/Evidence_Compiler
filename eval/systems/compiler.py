"""System C: the Evidence Compiler pipeline, adapted to the evaluation interface."""

import time

from evidence_compiler.app import AppContext
from evidence_compiler.core.invariants import GraphValidator
from evidence_compiler.core.models import ClaimStatus
from evidence_compiler.pipeline.compiler import MARKER_RE, split_sentences
from evidence_compiler.pipeline.orchestrator import PipelineOptions

from eval.systems import Citation, SystemOutput
from eval.systems.rag import ABSTAIN_RE


class CompilerSystem:
    name = "C"

    def __init__(self, ctx: AppContext, options: PipelineOptions | None = None):
        self.ctx = ctx
        self.options = options

    def answer(self, qid: str, question: str) -> SystemOutput:
        start = time.time()
        ans = self.ctx.pipeline(self.options).run(question, run_id=f"eval_{qid}")
        names = {s.id: s.name for s in self.ctx.repo.list_sources()}
        by_id = {c.id: c for c in ans.claims}
        out = SystemOutput(system=self.name, question_id=qid, answer="")
        plain: list[str] = []
        for sentence in split_sentences(ans.text):
            ids = [i for i in MARKER_RE.findall(sentence) if i in by_id]
            text = MARKER_RE.sub("", sentence).replace(" .", ".").strip()
            plain.append(text)
            usable = [by_id[i] for i in ids if by_id[i].status != ClaimStatus.UNSUPPORTED]
            if not usable:
                continue
            ev = [
                ans.evidence[link.evidence_id]
                for c in usable
                for link in c.links
                if link.evidence_id in ans.evidence
            ]
            out.citations.append(
                Citation(
                    sentence=text,
                    evidence_texts=[e.text for e in ev],
                    source_names=sorted({names.get(s, s) for e in ev for s in e.source_ids}),
                )
            )
        out.answer = " ".join(plain)
        out.abstained = ans.insufficient or bool(ABSTAIN_RE.search(out.answer))
        supported = [c for c in ans.claims if c.status == ClaimStatus.SUPPORTED]
        validator = GraphValidator(ans.evidence, {s.id: s for s in self.ctx.repo.list_sources()})
        out.internal = {
            "claims": len(ans.claims),
            "supported": len(supported),
            "rejected": sum(c.status == ClaimStatus.REJECTED for c in ans.claims),
            "unsupported": sum(c.status == ClaimStatus.UNSUPPORTED for c in ans.claims),
            "provenance_valid": sum(not validator.claim_violations(c) for c in supported),
            "calculations": len(ans.calculations),
            "warnings": ans.warnings,
        }
        out.seconds = time.time() - start
        return out
