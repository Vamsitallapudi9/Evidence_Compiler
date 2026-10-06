from fastapi import APIRouter, Depends, HTTPException

from evidence_compiler.api.deps import get_ctx
from evidence_compiler.app import AppContext
from evidence_compiler.core.models import EvidenceItem

router = APIRouter(tags=["evidence"])


@router.get("/evidence/{evidence_id}", response_model=EvidenceItem)
def get_evidence(evidence_id: str, ctx: AppContext = Depends(get_ctx)) -> EvidenceItem:
    item = ctx.repo.get_evidence(evidence_id)
    if item is None:
        raise HTTPException(404, "Evidence not found")
    return item
