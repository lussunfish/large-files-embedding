import typer

from large_files_embedding.presentation.cli.ingest import ingest

app = typer.Typer(no_args_is_help=True)
app.command()(ingest)


@app.callback()
def _root() -> None:
    """시장품질 문서 입고·조회 CLI."""


@app.command()
def health() -> None:
    """Print ok. Used as a CLI smoke check."""
    typer.echo("ok")
