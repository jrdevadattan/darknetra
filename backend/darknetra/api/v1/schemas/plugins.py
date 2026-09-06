from pydantic import Field

from .common import Schema


class Plugin(Schema):
    id: str
    installed: bool
    installation_kind: str
    manifest_hash: str
    tools: list[str]
    requires_network: bool
    enabled: bool
    status: str
    unavailable_reason: str | None = None


class PluginPatch(Schema):
    enabled: bool
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
