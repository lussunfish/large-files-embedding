import typer

app = typer.Typer(no_args_is_help=True)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the HTTP app if present."""
    import uvicorn

    uvicorn.run(
        "{{PYTHON_PACKAGE}}.presentation.http.app:app",
        host=host,
        port=port,
        reload=False,
    )


@app.command()
def health() -> None:
    """Print ok. Used as a CLI smoke check."""
    typer.echo("ok")
