import typer

from repolens import __version__

app = typer.Typer(
    help="Ask questions about a GitHub repository and get answers with verifiable citations.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """repolens command-line interface."""


@app.command()
def version() -> None:
    """Print the installed repolens version."""
    typer.echo(f"repolens {__version__}")
