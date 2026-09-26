from typing import Annotated

import openai
import psycopg
import typer

from repolens import __version__
from repolens.config import Settings
from repolens.doctor import healthy, probe_database, run_checks
from repolens.embedding import OpenAIEmbedder
from repolens.github import GitHubSource
from repolens.ingest import IngestError, ingest
from repolens.snapshot import RepoRef
from repolens.store import ChunkStore

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


@app.command("ingest")
def ingest_command(
    repo: Annotated[
        str,
        typer.Argument(
            metavar="OWNER/REPO[@REF]",
            help="REF is a branch, tag or SHA (default: the default branch).",
        ),
    ],
) -> None:
    """Download, chunk and embed a repository at a pinned commit."""
    try:
        repo_ref = RepoRef.parse(repo)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="OWNER/REPO[@REF]") from exc
    settings = Settings()
    if settings.openai_api_key is None:
        typer.echo("error: OPENAI_API_KEY is not set (needed for embeddings)", err=True)
        raise typer.Exit(code=1)
    github_token = settings.github_token.get_secret_value() if settings.github_token else None
    store = ChunkStore(settings.database_url)
    try:
        store.setup()
        result = ingest(
            repo_ref,
            GitHubSource(token=github_token),
            OpenAIEmbedder(api_key=settings.openai_api_key.get_secret_value()),
            store,
        )
    except (IngestError, openai.OpenAIError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except psycopg.OperationalError as exc:
        typer.echo("error: can't reach the database, run `repolens doctor`", err=True)
        raise typer.Exit(code=1) from exc
    status = "Ingested" if result.created else "Already ingested"
    typer.echo(
        f"{status} {result.snapshot}: {result.chunk_count} chunks from {result.file_count} files"
    )
