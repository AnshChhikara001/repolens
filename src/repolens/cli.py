import typer

from repolens import __version__
from repolens.config import Settings
from repolens.doctor import healthy, probe_database, run_checks

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


@app.command()
def doctor() -> None:
    """Check the database connection and configured API keys."""
    checks = run_checks(Settings(), probe_database)
    for check in checks:
        status = "ok" if check.ok else "FAIL" if check.required else "missing"
        typer.echo(f"{status:<9}{check.name:<21}{check.detail}")
    if not healthy(checks):
        raise typer.Exit(code=1)
