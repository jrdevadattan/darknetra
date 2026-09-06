"""Startup failures keep protocol stdout and credential values clean."""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("invalid_case", [False, True])
def test_missing_or_invalid_binding_exits_without_secret_output(invalid_case):
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("DARKNETRA_MCP_")
    }
    secret = "dk_SYNTHETIC_NEVER_PRINT_THIS_TOKEN"
    if invalid_case:
        environment.update(
            {"DARKNETRA_MCP_CASE_ID": "SYNTHETIC-not-a-uuid", "DARKNETRA_MCP_API_TOKEN": secret}
        )
    result = subprocess.run(
        [sys.executable, "-m", "darknetra.tools.adapters.stdio_mcp"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "MCP startup refused" in result.stderr
    assert secret not in result.stderr
    assert "SYNTHETIC-not-a-uuid" not in result.stderr
