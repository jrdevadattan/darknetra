import pytest

from darknetra_api.security.passwords import (
    PasswordPolicyError,
    hash_password,
    validate_password_policy,
    verify_password,
)


def test_argon2id_password_hash_round_trip() -> None:
    encoded = hash_password("Correct horse battery staple 42")
    assert encoded.startswith("$argon2id$")
    assert verify_password("Correct horse battery staple 42", encoded) is True
    assert verify_password("wrong password", encoded) is False


def test_hashes_use_unique_salts() -> None:
    first = hash_password("Correct horse battery staple 42")
    second = hash_password("Correct horse battery staple 42")
    assert first != second


@pytest.mark.parametrize("password", ["short", "x" * 129, "valid-password\x00suffix"])
def test_password_policy_rejects_invalid_lengths_and_nul(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy(password, username="analyst")


def test_password_policy_rejects_password_equal_to_username_case_insensitive() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("Investigator01", username="INVESTIGATOR01")


def test_password_policy_does_not_trim_passwords() -> None:
    password = "  valid password with spaces  "
    validate_password_policy(password, username="analyst")
    encoded = hash_password(password)
    assert verify_password(password, encoded) is True
    assert verify_password(password.strip(), encoded) is False
