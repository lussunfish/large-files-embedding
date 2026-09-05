"""UC-06: generate Grok stdio MCP config.toml snippet (tmp paths only)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from large_files_embedding.application.configure_grok import ConfigureGrok
from large_files_embedding.domain.document import (
    FailureReason,
    GrokConfigError,
    GrokMcpSnippet,
)
from large_files_embedding.infrastructure.grok_snippet_writer import TomlSnippetWriter


def _uc() -> ConfigureGrok:
    return ConfigureGrok(TomlSnippetWriter())


def test_empty_command_raises(tmp_path: Path) -> None:
    dest = tmp_path / "deploy" / "grok-mcp.toml"

    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(dest, command="")

    assert exc_info.value.reason is FailureReason.EMPTY_MCP_COMMAND
    assert not dest.exists()


def test_whitespace_command_raises(tmp_path: Path) -> None:
    dest = tmp_path / "grok-mcp.toml"

    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(dest, command="   ")

    assert exc_info.value.reason is FailureReason.EMPTY_MCP_COMMAND
    assert not dest.exists()


def test_home_config_toml_is_not_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    grok_dir = fake_home / ".grok"
    grok_dir.mkdir(parents=True)
    home_config = grok_dir / "config.toml"
    home_config.write_text("# keep-me\n", encoding="utf-8")
    skills = grok_dir / "skills" / "log" / "SKILL.md"
    skills.parent.mkdir(parents=True)
    skills.write_text("skill-keep\n", encoding="utf-8")
    agent = grok_dir / "agents" / "coder.md"
    agent.parent.mkdir(parents=True)
    agent.write_text("agent-keep\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    dest = tmp_path / "deploy" / "grok-mcp.toml"
    written = _uc().execute(dest, cwd=tmp_path)

    assert written == dest
    assert dest.is_file()
    assert home_config.read_text(encoding="utf-8") == "# keep-me\n"
    assert skills.read_text(encoding="utf-8") == "skill-keep\n"
    assert agent.read_text(encoding="utf-8") == "agent-keep\n"

    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(home_config)
    assert exc_info.value.reason is FailureReason.PROTECTED_GROK_PATH
    assert home_config.read_text(encoding="utf-8") == "# keep-me\n"

    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(skills)
    assert exc_info.value.reason is FailureReason.PROTECTED_GROK_PATH
    assert skills.read_text(encoding="utf-8") == "skill-keep\n"

    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(agent)
    assert exc_info.value.reason is FailureReason.PROTECTED_GROK_PATH
    assert agent.read_text(encoding="utf-8") == "agent-keep\n"


def test_snippet_matches_grok_mcp_servers_format(tmp_path: Path) -> None:
    dest = tmp_path / "grok-mcp.toml"
    cwd = tmp_path / "project"
    cwd.mkdir()

    _uc().execute(dest, cwd=cwd)

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
    assert server["cwd"] == str(cwd)
    assert server["enabled"] is True
    assert int(server["startup_timeout_sec"]) >= 30
    assert "tool_timeout_sec" in server


def test_startup_timeout_below_minimum_raises(tmp_path: Path) -> None:
    dest = tmp_path / "grok-mcp.toml"

    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(dest, startup_timeout_sec=10)

    assert exc_info.value.reason is FailureReason.STARTUP_TIMEOUT_TOO_SHORT
    assert not dest.exists()


def test_case_variant_home_config_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    grok_dir = fake_home / ".grok"
    grok_dir.mkdir(parents=True)
    home_config = grok_dir / "config.toml"
    home_config.write_text("# keep-me\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    variant = grok_dir / "CONFIG.TOML"
    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(variant)
    assert exc_info.value.reason is FailureReason.PROTECTED_GROK_PATH
    assert home_config.read_text(encoding="utf-8") == "# keep-me\n"


def test_case_variant_missing_home_config_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    grok_dir = fake_home / ".grok"
    grok_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    variant = grok_dir / "CONFIG.TOML"
    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(variant)
    assert exc_info.value.reason is FailureReason.PROTECTED_GROK_PATH
    assert not (grok_dir / "config.toml").exists()
    assert not variant.exists()


def test_case_variant_codex_config_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    codex_dir = fake_home / ".codex"
    codex_dir.mkdir(parents=True)
    codex_config = codex_dir / "config.toml"
    codex_config.write_text("# keep-codex\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(codex_dir / "CONFIG.TOML")
    assert exc_info.value.reason is FailureReason.PROTECTED_GROK_PATH
    assert codex_config.read_text(encoding="utf-8") == "# keep-codex\n"


def test_case_variant_skills_path_is_rejected(tmp_path: Path) -> None:
    skills = tmp_path / ".grok" / "skills" / "log" / "SKILL.md"
    skills.parent.mkdir(parents=True)
    skills.write_text("skill-keep\n", encoding="utf-8")

    variant = tmp_path / ".grok" / "SKILLS" / "log" / "SKILL.md"
    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(variant)
    assert exc_info.value.reason is FailureReason.PROTECTED_GROK_PATH
    assert skills.read_text(encoding="utf-8") == "skill-keep\n"


def test_case_variant_agents_and_roles_are_rejected(tmp_path: Path) -> None:
    agent = tmp_path / ".grok" / "agents" / "coder.md"
    agent.parent.mkdir(parents=True)
    agent.write_text("agent-keep\n", encoding="utf-8")
    role = tmp_path / ".grok" / "roles" / "coder.toml"
    role.parent.mkdir(parents=True)
    role.write_text("role-keep\n", encoding="utf-8")

    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(tmp_path / ".grok" / "AGENTS" / "coder.md")
    assert exc_info.value.reason is FailureReason.PROTECTED_GROK_PATH
    assert agent.read_text(encoding="utf-8") == "agent-keep\n"

    with pytest.raises(GrokConfigError) as exc_info:
        _uc().execute(tmp_path / ".grok" / "ROLES" / "coder.toml")
    assert exc_info.value.reason is FailureReason.PROTECTED_GROK_PATH
    assert role.read_text(encoding="utf-8") == "role-keep\n"


def test_snippet_vo_rejects_empty_command() -> None:
    with pytest.raises(GrokConfigError) as exc_info:
        GrokMcpSnippet(
            server_name="market-quality",
            command="",
            args=("run", "python", "-m", "large_files_embedding", "mcp"),
            cwd=".",
            enabled=True,
            startup_timeout_sec=30,
            tool_timeout_sec=60,
        )
    assert exc_info.value.reason is FailureReason.EMPTY_MCP_COMMAND
