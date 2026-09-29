from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import openai
import psycopg
import typer

from repolens import __version__
from repolens.config import ModelConfigError, Settings
from repolens.doctor import healthy, probe_database, run_checks
from repolens.embedding import OpenAIEmbedder
from repolens.evaluation import Question, evaluate, load_questions, results
from repolens.github import GitHubSource
from repolens.ingest import IngestError, IngestResult, ingest
from repolens.llm import LLMError
from repolens.models import build_llm
from repolens.report import Report
from repolens.rerank import CrossEncoderReranker
from repolens.run import RunConfig, run
from repolens.snapshot import RepoRef, Snapshot
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
    typer.echo(f"{status} {_ingest_summary(result)}")


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
        llm = build_llm(settings)
        store = ChunkStore(settings.database_url)
        result = _ingest(repo_ref, settings, embedder, store)
        if result.created:
            typer.echo(f"Ingested {_ingest_summary(result)}", err=True)
        config = RunConfig(llm, embedder, store, CrossEncoderReranker(), settings.runs_dir)
        typer.echo(f"Answering with {settings.chat_model}…", err=True)
        with _timeout_as_message(settings.chat_timeout):
            report = run(question, result.snapshot, config)
    typer.echo(str(report))


@app.command("eval")
def eval_command(
    dataset: Annotated[
        Path, typer.Option(help="A TOML file of questions pinned to commit SHAs.")
    ] = Path("evals/questions.toml"),
    rerank: Annotated[
        bool, typer.Option(help="Rerank the retrieved code before the model reads it.")
    ] = True,
) -> None:
    """Answer the eval questions and print the results as markdown tables."""
    try:
        questions = load_questions(dataset)
    except OSError as exc:
        typer.echo(f"error: {dataset}: {exc.strerror}", err=True)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.echo(f"error: {dataset}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    settings = Settings()
    embedder = _embedder(settings)
    with _errors_as_messages():
        llm = build_llm(settings)
        store = ChunkStore(settings.database_url)
        reranker = CrossEncoderReranker() if rerank else None
        config = RunConfig(llm, embedder, store, reranker, settings.runs_dir)
        snapshots: dict[str, Snapshot] = {}

        def answer(question: Question) -> Report:
            if question.repo not in snapshots:
                result = _ingest(RepoRef.parse(question.repo), settings, embedder, store)
                if result.created:
                    typer.echo(f"Ingested {_ingest_summary(result)}", err=True)
                snapshots[question.repo] = result.snapshot
            number = questions.index(question) + 1
            typer.echo(f"[{number}/{len(questions)}] {question.id}", err=True)
            return run(question.question, snapshots[question.repo], config)

        outcomes = evaluate(questions, answer)
    model = llm.name.partition(":")[2]
    typer.echo(f"Model: {model} · Reranking: {'on' if rerank else 'off'}\n")
    typer.echo(results(outcomes))


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
    except (IngestError, ModelConfigError, LLMError, openai.OpenAIError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except psycopg.OperationalError as exc:
        typer.echo("error: can't reach the database, run `repolens doctor`", err=True)
        raise typer.Exit(code=1) from exc


@contextmanager
def _timeout_as_message(timeout: float) -> Generator[None]:
    """Report a chat model request that took longer than CHAT_TIMEOUT.

    Embedding requests raise OpenAI's own timeout error, which `_errors_as_messages` prints.
    """
    try:
        yield
    except TimeoutError as exc:
        typer.echo(
            f"error: a chat model request took longer than {timeout:g}s,"
            " raise CHAT_TIMEOUT to wait longer",
            err=True,
        )
        raise typer.Exit(code=1) from exc


def _ingest_summary(result: IngestResult) -> str:
    return f"{result.snapshot}: {result.chunk_count} chunks from {result.file_count} files"
