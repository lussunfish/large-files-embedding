"""Generate a Grok stdio MCP config.toml snippet without touching home config."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from large_files_embedding.domain.document import (
    DEFAULT_MCP_ARGS,
    DEFAULT_MCP_COMMAND,
    DEFAULT_MCP_SERVER_NAME,
    DEFAULT_STARTUP_TIMEOUT_SEC,
    DEFAULT_TOOL_TIMEOUT_SEC,
    GrokConfigExporter,
    GrokMcpSnippet,
    require_export_destination,
)


class ConfigureGrok:
    def __init__(self, exporter: GrokConfigExporter) -> None:
        self._exporter = exporter

    def execute(
        self,
        destination: Path,
        *,
        command: str = DEFAULT_MCP_COMMAND,
        args: Sequence[str] | None = None,
        cwd: str | Path | None = None,
        enabled: bool = True,
        startup_timeout_sec: int = DEFAULT_STARTUP_TIMEOUT_SEC,
        tool_timeout_sec: int = DEFAULT_TOOL_TIMEOUT_SEC,
        server_name: str = DEFAULT_MCP_SERVER_NAME,
    ) -> Path:
        snippet = GrokMcpSnippet(
            server_name=server_name,
            command=command,
            args=tuple(args if args is not None else DEFAULT_MCP_ARGS),
            cwd="." if cwd is None else str(cwd),
            enabled=enabled,
            startup_timeout_sec=startup_timeout_sec,
            tool_timeout_sec=tool_timeout_sec,
        )
        require_export_destination(destination)
        return self._exporter.export(snippet, destination)
