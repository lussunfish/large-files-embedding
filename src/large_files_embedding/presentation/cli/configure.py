"""CLI adapter: write Grok MCP config.toml snippet."""

from pathlib import Path

import typer

from large_files_embedding.application.configure_grok import ConfigureGrok
from large_files_embedding.domain.document import GrokConfigError
from large_files_embedding.infrastructure.grok_snippet_writer import TomlSnippetWriter


def configure_grok(
    destination: Path = typer.Option(
        Path("deploy/grok-mcp.toml"),
        "--destination",
        "-o",
        help="저장소 스니펫 경로. 홈 ~/.grok/config.toml 은 쓰지 않는다.",
    ),
    command: str = typer.Option("uv", "--command"),
    cwd: Path | None = typer.Option(None, "--cwd"),
    startup_timeout_sec: int = typer.Option(30, "--startup-timeout-sec"),
    tool_timeout_sec: int = typer.Option(60, "--tool-timeout-sec"),
) -> None:
    """Write a Grok MCP snippet. Does not edit ~/.grok/config.toml."""
    try:
        path = ConfigureGrok(TomlSnippetWriter()).execute(
            destination,
            command=command,
            cwd=cwd if cwd is not None else Path.cwd(),
            startup_timeout_sec=startup_timeout_sec,
            tool_timeout_sec=tool_timeout_sec,
        )
    except GrokConfigError as exc:
        typer.echo(f"FAIL reason={exc.reason.value}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(path))
