from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated

import openai
import psycopg
import typer
from langchain_core.exceptions import LangChainException

from repolens import __version__
from repolens.config import Settings
from repolens.doctor import healthy, probe_database, run_checks
from repolens.embedding import OpenAIEmbedder
from repolens.github import GitHubSource
from repolens.ingest import IngestError, IngestResult, ingest
from repolens.models import ModelConfigError, chat_model
from repolens.report import Report
from repolens.run import RunConfig, run
from repolens.snapshot import RepoRef
from repolens.store import ChunkStore

app = typer.Typer(
    help="Ask questions about a GitHub repository and get answers with verifiable citations.",
    no_args_is_help=True,
)

RepoArgument = Annotated[
    str,
    typer.Argument(
        metavar="OWNER/REPO[@REF]",
        help="REF is a branch, tag or SHA (default: the default branch).",
    ),
]


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
def ingest_command(repo: RepoArgument) -> None:
    """Download, chunk and embed a repository at a pinned commit."""
    repo_ref = _parse_repo(repo)
    settings = Settings()
    embedder = _embedder(settings)
    with _errors_as_messages():
        result = _ingest(repo_ref, settings, embedder, ChunkStore(settings.database_url))
    status = "Ingested" if result.created else "Already ingested"
    typer.echo(f"{status} {_counts(result)}")


@app.command()
def ask(
    repo: RepoArgument,
    question: Annotated[str, typer.Argument(help="A question about the code.")],
) -> None:
    """Answer a question about a repository with a cited Report."""
    repo_ref = _parse_repo(repo)
    settings = Settings()
    embedder = _embedder(settings)
    with _errors_as_messages():
        model = chat_model(settings)
        store = ChunkStore(settings.database_url)
        result = _ingest(repo_ref, settings, embedder, store)
        if result.created:
            typer.echo(f"Ingested {_counts(result)}", err=True)
        report = run(question, result.snapshot, RunConfig(model, embedder, store))
    typer.echo(_render(report))


def _parse_repo(repo: str) -> RepoRef:
    try:
        return RepoRef.parse(repo)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="OWNER/REPO[@REF]") from exc


def _embedder(settings: Settings) -> OpenAIEmbedder:
    if settings.openai_api_key is None:
        typer.echo("error: OPENAI_API_KEY is not set (needed for embeddings)", err=True)
        raise typer.Exit(code=1)
    return OpenAIEmbedder(api_key=settings.openai_api_key.get_secret_value())


def _ingest(
    repo: RepoRef, settings: Settings, embedder: OpenAIEmbedder, store: ChunkStore
) -> IngestResult:
    github_token = settings.github_token.get_secret_value() if settings.github_token else None
    store.setup()
    return ingest(repo, GitHubSource(token=github_token), embedder, store)


@contextmanager
def _errors_as_messages() -> Generator[None]:
    """Turn expected failures into a one-line error and exit code 1."""
    try:
        yield
    except (IngestError, ModelConfigError, openai.OpenAIError, LangChainException) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except psycopg.OperationalError as exc:
        typer.echo("error: can't reach the database, run `repolens doctor`", err=True)
        raise typer.Exit(code=1) from exc


def _counts(result: IngestResult) -> str:
    return f"{result.snapshot}: {result.chunk_count} chunks from {result.file_count} files"


def _render(report: Report) -> str:
    lines = [f"Snapshot: {report.snapshot}", f"Question: {report.question}", "", report.answer]
    if report.findings:
        lines.append("")
    for number, finding in enumerate(report.findings, 1):
        lines.append(f"[{number}] {finding.claim}")
        lines.extend(f"    {citation}" for citation in finding.citations)
    return "\n".join(lines)
