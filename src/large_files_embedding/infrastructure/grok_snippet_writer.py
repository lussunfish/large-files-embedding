"""Write a Grok [mcp_servers.*] TOML snippet. Never overwrites home config."""

from __future__ import annotations

from pathlib import Path

from large_files_embedding.domain.document import (
    GrokMcpSnippet,
    require_export_destination,
)


class TomlSnippetWriter:
    def export(self, snippet: GrokMcpSnippet, destination: Path) -> Path:
        require_export_destination(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_grok_mcp_toml(snippet), encoding="utf-8")
        return destination


def render_grok_mcp_toml(snippet: GrokMcpSnippet) -> str:
    args = ", ".join(_toml_string(arg) for arg in snippet.args)
    return (
        f"[mcp_servers.{snippet.server_name}]\n"
        f"command = {_toml_string(snippet.command)}\n"
        f"args = [{args}]\n"
        f"cwd = {_toml_string(snippet.cwd)}\n"
        f"enabled = {'true' if snippet.enabled else 'false'}\n"
        f"startup_timeout_sec = {int(snippet.startup_timeout_sec)}\n"
        f"tool_timeout_sec = {int(snippet.tool_timeout_sec)}\n"
    )


def _toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
