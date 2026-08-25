from __future__ import annotations

import logging
import re
from functools import partial
from typing import Annotated
from uuid import UUID, uuid4

import anyio
from darknetra_api.authz.permissions import Permission
from darknetra_api.authz.policy import (
    AuthorizationDenied,
    CaseNotFound,
    PasswordChangeRequired,
    authorize_case,
)
from darknetra_api.dependencies.auth import DbSession, get_current_auth_context
from darknetra_api.middleware.upload_limit import MULTIPART_ENVELOPE_MAX_BYTES
from darknetra_api.policy.ingestion import (
    DEFAULT_PREFIX_BYTES,
    EvidenceSourceMetadata,
    UploadPolicyError,
    preserve_upload,
)
from darknetra_api.schemas.evidence import (
    EvidenceIngestResponse,
    EvidenceJobRead,
    PreservedEvidenceRead,
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
from darknetra_api.services.evidence_ingest import (
    IngestPublisher,
    persist_preserved_upload,
    publish_ingest_payload,
)
from darknetra_api.services.sensitive_values import (
    SensitiveRevealReasonError,
    bind_sensitive_reveal_context,
    reveal_sensitive_value,
)
from darknetra_api.storage.base import (
    ObjectHashMismatchError,
    ObjectIntegrityError,
    ObjectKeyError,
    ObjectStore,
    ObjectStoreConfigurationError,
)
from darknetra_api.storage.local import LocalObjectStore
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import ValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["evidence"])
logger = logging.getLogger(__name__)
_REVEAL_PATH_PATTERN = re.compile(
    r"^/api/v1/cases/[^/]+/evidence/[^/]+/sensitive/[^/]+/[^/]+/reveal/?$"
)
_UPLOAD_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["metadata", "file"],
                    "properties": {
                        "metadata": {
                            "type": "string",
                            "description": "JSON-encoded evidence source metadata",
                        },
                        "file": {"type": "string", "format": "binary"},
                    },
                }
            }
        },
    }
}


def is_sensitive_reveal_path(path: str) -> bool:
    return bool(_REVEAL_PATH_PATTERN.fullmatch(path))


def _require_csrf(request: Request, context: AuthContext) -> None:
    token = request.headers.get("X-CSRF-Token")
    if not token or not verify_csrf_token(token, context.auth_session.csrf_token_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="csrf validation failed",
            headers={"Cache-Control": "no-store"},
        )


def get_evidence_object_store(request: Request) -> ObjectStore:
    existing = getattr(request.app.state, "evidence_object_store", None)
    if isinstance(existing, ObjectStore):
        return existing
    settings = request.app.state.runtime_settings
    store = LocalObjectStore(
        settings.evidence_store_root,
        allow_trusted_volume_fallback=settings.evidence_store_allow_trusted_volume_fallback,
    )
    request.app.state.evidence_object_store = store
    return store


def get_ingest_publisher(request: Request) -> IngestPublisher:
    return getattr(request.app.state, "ingest_publisher", publish_ingest_payload)


def _upload_error(code: str, *, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


@router.post(
    "",
    response_model=EvidenceIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra=_UPLOAD_OPENAPI,
)
async def ingest_evidence_route(
    case_id: UUID,
    request: Request,
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: DbSession,
) -> EvidenceIngestResponse:
    _require_csrf(request, context)
    try:
        await authorize_case(context.user, case_id, Permission.EVIDENCE_CREATE, db)
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail="resource not found") from exc
    except PasswordChangeRequired as exc:
        raise HTTPException(status_code=403, detail="password change required") from exc
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail="permission denied") from exc

    settings = request.app.state.runtime_settings
    content_length = request.headers.get("Content-Length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise _upload_error("INVALID_CONTENT_LENGTH", status_code=400) from exc
        if declared_length < 0:
            raise _upload_error("INVALID_CONTENT_LENGTH", status_code=400)
        if declared_length > settings.evidence_upload_max_bytes + MULTIPART_ENVELOPE_MAX_BYTES:
            raise _upload_error("UPLOAD_TOO_LARGE", status_code=413)

    try:
        form = await request.form(
            max_files=1,
            max_fields=1,
            max_part_size=MULTIPART_ENVELOPE_MAX_BYTES,
        )
    except (MultiPartException, StarletteHTTPException) as exc:
        raise _upload_error("INVALID_MULTIPART", status_code=400) from exc

    try:
        if set(form) != {"file", "metadata"}:
            raise _upload_error("INVALID_MULTIPART", status_code=422)
        file_values = form.getlist("file")
        metadata_values = form.getlist("metadata")
        if len(file_values) != 1 or len(metadata_values) != 1:
            raise _upload_error("INVALID_MULTIPART", status_code=422)
        file = file_values[0]
        metadata_json = metadata_values[0]
        if not isinstance(file, UploadFile) or not isinstance(metadata_json, str):
            raise _upload_error("INVALID_MULTIPART", status_code=422)

        try:
            metadata = EvidenceSourceMetadata.model_validate_json(metadata_json)
        except ValidationError as exc:
            raise _upload_error("INVALID_EVIDENCE_METADATA", status_code=422) from exc

        object_store = get_evidence_object_store(request)
        try:
            preserved = await anyio.to_thread.run_sync(
                partial(
                    preserve_upload,
                    stream=file.file,
                    object_store=object_store,
                    metadata=metadata,
                    filename=file.filename,
                    declared_content_type=file.content_type,
                    max_bytes=settings.evidence_upload_max_bytes,
                    prefix_bytes=DEFAULT_PREFIX_BYTES,
                )
            )
        except UploadPolicyError as exc:
            status_code = 413 if exc.code == "UPLOAD_TOO_LARGE" else 415
            raise _upload_error(exc.code, status_code=status_code) from exc
        except ObjectKeyError as exc:
            raise _upload_error("INVALID_OBJECT_KEY", status_code=400) from exc
        except ObjectHashMismatchError as exc:
            raise _upload_error("EVIDENCE_HASH_MISMATCH", status_code=409) from exc
        except ObjectIntegrityError as exc:
            raise _upload_error("EVIDENCE_OBJECT_INTEGRITY_FAILURE", status_code=409) from exc
        except (ObjectStoreConfigurationError, OSError) as exc:
            raise _upload_error("EVIDENCE_STORE_UNAVAILABLE", status_code=503) from exc
    finally:
        await form.close()

    crypto = getattr(request.app.state, "sensitive_field_crypto", None)
    if not isinstance(crypto, SensitiveFieldCrypto):
        raise _upload_error("SENSITIVE_FIELD_CRYPTO_UNAVAILABLE", status_code=503)
    publisher = get_ingest_publisher(request)
    try:
        result = await persist_preserved_upload(
            db,
            case_id=case_id,
            actor_user_id=context.user.id,
            metadata=metadata,
            preserved=preserved,
            crypto=crypto,
            request_id=request.headers.get("X-Request-ID") or str(uuid4()),
            pipeline_version=settings.evidence_ingest_pipeline_version,
            publisher=publisher,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "evidence persistence failed code=EVIDENCE_PERSISTENCE_FAILED "
            "case_id=%s error_type=%s",
            case_id,
            type(exc).__name__,
        )
        raise _upload_error("EVIDENCE_PERSISTENCE_FAILED", status_code=503) from None
    return EvidenceIngestResponse(
        evidence=PreservedEvidenceRead(
            id=result.evidence_id,
            case_id=result.case_id,
            media_type=result.media_type,
            size_bytes=result.size_bytes,
            sha256=result.sha256,
            state=result.evidence_state,
        ),
        job=EvidenceJobRead(
            id=result.job_id,
            status=result.job_status,
            dispatch_state=result.dispatch_state,
        ),
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


__all__ = [
    "get_evidence_object_store",
    "get_ingest_publisher",
    "ingest_evidence_route",
    "is_sensitive_reveal_path",
    "router",
]
