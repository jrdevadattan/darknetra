import base64
import json
import re

import pytest
from darknetra_api.config import Settings
from darknetra_api.security.encrypted_fields import (
    EncryptedFieldValidationError,
    pack_envelope,
    unpack_envelope,
)
from darknetra_api.security.encryption import (
    EncryptedValue,
    SensitiveFieldConfigurationError,
    SensitiveFieldCrypto,
)
from darknetra_api.security.keyring import SensitiveFieldKeyring
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

_ACCEPTED_KEY_VERSION = re.compile(r"v[1-9][0-9]{0,62}")
_VALID_VERSIONS = st.from_regex(_ACCEPTED_KEY_VERSION, fullmatch=True)
_INVALID_VERSIONS = st.text(max_size=70).filter(
    lambda value: _ACCEPTED_KEY_VERSION.fullmatch(value) is None
)
_NONCE_B64 = "AAECAwQFBgcICQoL"
_CIPHERTEXT_B64 = "AAECAwQFBgcICQoLDA0ODw=="


def key(byte: int) -> bytes:
    return bytes([byte]) * 32


def encoded_key(byte: int) -> str:
    return base64.b64encode(key(byte)).decode("ascii")


@given(version=_VALID_VERSIONS)
def test_every_accepted_key_version_round_trips_through_all_boundaries(version: str) -> None:
    """Catches config, keyring, crypto, and persistence drifting on an accepted version."""
    settings = Settings(
        field_keyring_b64_json=json.dumps({version: encoded_key(0x11)}),
        field_active_key_version=version,
        field_blind_index_key_b64=encoded_key(0x22),
        _env_file=None,
    )
    service = settings.require_sensitive_field_crypto()
    encrypted = service.encrypt(
        "version round trip",
        purpose="custody.notes",
        resource_id="record-a",
    )
    restored = unpack_envelope(pack_envelope(encrypted))

    assert restored.key_version == version
    assert (
        service.decrypt(
            restored,
            purpose="custody.notes",
            resource_id="record-a",
        )
        == "version round trip"
    )


@given(version=_INVALID_VERSIONS)
def test_every_invalid_key_version_is_rejected_by_all_boundaries(version: str) -> None:
    """Catches any boundary accepting a version that another boundary rejects."""
    with pytest.raises(ValidationError, match="invalid sensitive field key version"):
        Settings(field_active_key_version=version, _env_file=None)

    with pytest.raises(ValidationError, match="invalid sensitive field key version"):
        Settings(
            field_keyring_b64_json=json.dumps({version: encoded_key(0x11)}),
            _env_file=None,
        )

    with pytest.raises(SensitiveFieldConfigurationError, match="invalid sensitive field key version"):
        SensitiveFieldCrypto(
            field_keys={version: key(0x11)},
            active_key_version=version,
            blind_index_key=key(0x22),
        )

    with pytest.raises(SensitiveFieldConfigurationError, match="invalid sensitive field key version"):
        SensitiveFieldKeyring(
            keys={version: key(0x11)},
            active_version=version,
            blind_index_key=key(0x22),
        )

    envelope = EncryptedValue(
        key_version=version,
        nonce_b64=_NONCE_B64,
        ciphertext_b64=_CIPHERTEXT_B64,
    )
    with pytest.raises(EncryptedFieldValidationError, match="invalid encrypted field envelope"):
        pack_envelope(envelope)
    with pytest.raises(EncryptedFieldValidationError, match="invalid encrypted field envelope"):
        unpack_envelope(
            {
                "key_version": version,
                "nonce_b64": _NONCE_B64,
                "ciphertext_b64": _CIPHERTEXT_B64,
            }
        )
