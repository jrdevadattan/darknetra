from darknetra_api.dependencies.auth import CurrentUser
from darknetra_api.schemas.intelligence import (
    IntegrationListResponse,
    IntegrationNormalizeRequest,
    IntegrationNormalizeResponse,
    IntegrationRead,
    NormalizedObservationRead,
)
from fastapi import APIRouter, HTTPException, status

from services.collector.darknetra_collector.adapters import (
    get_integration_catalog,
    normalize_integration_output,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/integrations", response_model=IntegrationListResponse)
async def list_integrations_route(user: CurrentUser) -> IntegrationListResponse:
    del user
    return IntegrationListResponse(
        items=[
            IntegrationRead(
                slug=item.slug,
                name=item.name,
                repository_url=item.repository_url,
                integration_mode=item.integration_mode,
                pipeline_role=item.pipeline_role,
                accepted_outputs=list(item.accepted_outputs),
            )
            for item in get_integration_catalog()
        ]
    )


@router.post(
    "/integrations/{adapter}/normalize",
    response_model=IntegrationNormalizeResponse,
)
async def normalize_integration_route(
    adapter: str,
    payload: IntegrationNormalizeRequest,
    user: CurrentUser,
) -> IntegrationNormalizeResponse:
    del user
    try:
        normalized = normalize_integration_output(
            adapter=adapter,
            payload=payload.decoded_payload(),
            source_name=payload.source_name,
        )
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="integration package could not be normalized",
        ) from exc
    return IntegrationNormalizeResponse(
        adapter=normalized.adapter,
        content_sha256=normalized.content_sha256,
        observations=[
            NormalizedObservationRead(
                kind=item.kind,
                value=item.value,
                provenance=item.provenance,
                title=item.title,
                parent=item.parent,
            )
            for item in normalized.observations
        ],
    )


__all__ = ["list_integrations_route", "normalize_integration_route", "router"]
