import base64
import binascii

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_INTEGRATION_PACKAGE_BYTES = 2 * 1024 * 1024
MAX_INTEGRATION_PACKAGE_B64_CHARS = ((MAX_INTEGRATION_PACKAGE_BYTES + 2) // 3) * 4


class IntegrationRead(BaseModel):
    slug: str
    name: str
    repository_url: str
    integration_mode: str
    pipeline_role: str
    accepted_outputs: list[str]


class IntegrationListResponse(BaseModel):
    items: list[IntegrationRead]


class IntegrationNormalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_name: str = Field(min_length=3, max_length=200)
    payload_base64: str = Field(
        min_length=1,
        max_length=MAX_INTEGRATION_PACKAGE_B64_CHARS,
        repr=False,
    )

    @model_validator(mode="after")
    def validate_payload(self) -> "IntegrationNormalizeRequest":
        try:
            decoded = base64.b64decode(self.payload_base64, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("payload_base64 must contain valid base64") from None
        if len(decoded) > MAX_INTEGRATION_PACKAGE_BYTES:
            raise ValueError("integration package exceeds the 2 MiB limit")
        return self

    def decoded_payload(self) -> bytes:
        return base64.b64decode(self.payload_base64, validate=True)


class NormalizedObservationRead(BaseModel):
    kind: str
    value: str
    provenance: str
    title: str | None
    parent: str | None


class IntegrationNormalizeResponse(BaseModel):
    adapter: str
    content_sha256: str
    observations: list[NormalizedObservationRead]


__all__ = [
    "MAX_INTEGRATION_PACKAGE_B64_CHARS",
    "MAX_INTEGRATION_PACKAGE_BYTES",
    "IntegrationListResponse",
    "IntegrationNormalizeRequest",
    "IntegrationNormalizeResponse",
    "IntegrationRead",
    "NormalizedObservationRead",
]
