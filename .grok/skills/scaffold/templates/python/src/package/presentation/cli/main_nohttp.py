import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def health() -> None:
    """Print ok. Used as a CLI smoke check."""
    typer.echo("ok")
