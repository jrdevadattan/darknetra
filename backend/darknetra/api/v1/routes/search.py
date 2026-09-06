from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.api.v1.schemas.search import SearchQuery, SearchResult
from darknetra.authz.deps import require_case
from darknetra.authz.permissions import Permission
from darknetra.db import get_session
from darknetra.rag.search import search

router = APIRouter(tags=["search"])


@router.post("/cases/{case_id}/search", response_model=SearchResult)
async def query_evidence(
    case_id: UUID,
    body: SearchQuery,
    access=Depends(require_case(Permission.EVIDENCE_VIEW)),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await search(db, case_id, body, actor=access[0])
