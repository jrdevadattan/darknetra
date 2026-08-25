from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound
from darknetra_api.dependencies.auth import DbSession, get_current_auth_context
from darknetra_api.schemas.evidence import (
    SensitiveValueRevealRequest,
    SensitiveValueRevealResponse,
)
from darknetra_api.security.csrf import verify_csrf_token
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.services.auth import AuthContext
from darknetra_api.services.evidence import (
    EVIDENCE_RESOURCE_TYPE,
    EvidenceSensitiveRevealPolicy,
    EvidenceSensitiveValueProvider,
    canonical_sensitive_field_name,
)
from darknetra_api.services.sensitive_values import (
    SensitiveRevealReasonError,
    bind_sensitive_reveal_context,
    reveal_sensitive_value,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["evidence"])


def _require_csrf(request: Request, context: AuthContext) -> None:
    token = request.headers.get("X-CSRF-Token")
    if not token or not verify_csrf_token(token, context.auth_session.csrf_token_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf validation failed",
            headers={"Cache-Control": "no-store"},
        )


@router.post(
    "/{evidence_id}/sensitive/{value_id}/{field_name}/reveal",
    response_model=SensitiveValueRevealResponse,
)
async def reveal_evidence_sensitive_value_route(
    case_id: UUID,
    evidence_id: UUID,
    value_id: UUID,
    field_name: str,
    payload: SensitiveValueRevealRequest,
    request: Request,
    response: Response,
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: DbSession,
) -> SensitiveValueRevealResponse:
    """Reveal one evidence field only after authorization and durable audit."""

    _require_csrf(request, context)
    crypto = getattr(request.app.state, "sensitive_field_crypto", None)
    if not isinstance(crypto, SensitiveFieldCrypto):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="sensitive field crypto unavailable",
            headers={"Cache-Control": "no-store"},
        )
    try:
        canonical_field_name = canonical_sensitive_field_name(field_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
            headers={"Cache-Control": "no-store"},
        ) from exc
    bind_sensitive_reveal_context(
        db,
        provider=EvidenceSensitiveValueProvider(expected_evidence_id=evidence_id),
        permission_predicate=EvidenceSensitiveRevealPolicy(),
        crypto=crypto,
        request_id=request.headers.get("X-Request-ID") or str(uuid4()),
    )
    try:
        plaintext = await reveal_sensitive_value(
            actor=context.user,
            case_id=case_id,
            resource_type=EVIDENCE_RESOURCE_TYPE,
            resource_id=str(value_id),
            field_name=canonical_field_name,
            reason=payload.reason,
            session=db,
        )
    except CaseNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="resource not found",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except AuthorizationDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="permission denied",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except SensitiveRevealReasonError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
            headers={"Cache-Control": "no-store"},
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    return SensitiveValueRevealResponse(value=plaintext)


__all__ = ["router"]
