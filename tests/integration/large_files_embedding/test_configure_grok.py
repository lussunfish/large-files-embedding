"""UC-06 integration: CLI writes a Grok MCP snippet to a tmp path."""

from __future__ import annotations

import tomllib
from pathlib import Path

from typer.testing import CliRunner

from large_files_embedding.presentation.cli.main import app


def test_cli_configure_grok_is_registered() -> None:
    result = CliRunner().invoke(app, ["configure-grok", "--help"])
    assert result.exit_code == 0
    assert "mcp_servers" in result.output or "snippet" in result.output.lower()


def test_cli_writes_snippet_to_tmp(tmp_path: Path) -> None:
    dest = tmp_path / "deploy" / "grok-mcp.toml"
    result = CliRunner().invoke(
        app,
        [
            "configure-grok",
            "--destination",
            str(dest),
            "--cwd",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert dest.is_file()
    payload = tomllib.loads(dest.read_text(encoding="utf-8"))
    server = payload["mcp_servers"]["market-quality"]
    assert server["command"] == "uv"
    assert server["args"] == [
        "run",
        "python",
        "-m",
        "large_files_embedding",
        "mcp",
    ]
    assert server["cwd"] == str(tmp_path)
    assert server["enabled"] is True
    assert int(server["startup_timeout_sec"]) >= 30
    assert "tool_timeout_sec" in server


def test_cli_rejects_empty_command(tmp_path: Path) -> None:
    dest = tmp_path / "grok-mcp.toml"
    result = CliRunner().invoke(
        app,
        ["configure-grok", "--destination", str(dest), "--command", ""],
    )
    assert result.exit_code != 0
    assert "empty_mcp_command" in (result.output + result.stderr)
    assert not dest.exists()
