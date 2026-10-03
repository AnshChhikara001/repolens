"""The web app: ask about a demo repo in the browser and watch the Run, or read example answers.

Demo repos are those with example answers that are ingested under the current index version.
A question is a Run on our chat model within the demo limits, or on the visitor's own key. The
Run streams its Run log events as server-sent events, then the Report with its cited code.
Runs need one process, for the demo limits' counts.
"""

import json
import logging
import queue
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from repolens.config import ModelConfigError, Settings
from repolens.embedding import Embedder
from repolens.ingest import index_version
from repolens.limits import DemoLimits, LimitExceeded, llm_for_visitor
from repolens.llm import LLMError
from repolens.rerank import Reranker
from repolens.run import RunConfig, run
from repolens.snapshot import RepoRef, Snapshot
from repolens.store import ChunkStore
from repolens.web.answers import Answer, answer_from_report, load_answers

HERE = Path(__file__).parent
EXAMPLES = HERE / "examples.json"
STATIC = HERE / "static"
MAX_QUESTION_CHARS = 500
# The Run log events the page shows while a Run works.
PROGRESS_EVENTS = frozenset({"tool", "step", "call"})

logger = logging.getLogger(__name__)


class DemoRepo(BaseModel):
    snapshot: str
    repo: str
    sha: str
    examples: list[Answer]


class Question(BaseModel):
    snapshot: str
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS)
    ]
    api_key: str | None = Field(default=None, max_length=200)


def create_app(
    settings: Settings,
    embedder: Embedder,
    reranker: Reranker | None,
    examples: Path = EXAMPLES,
) -> FastAPI:
    store = ChunkStore(settings.database_url)
    limits = DemoLimits(settings)
    app = FastAPI(title="repolens", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def demo_repos() -> dict[str, DemoRepo]:
        version = index_version(embedder)
        repos: dict[str, DemoRepo] = {}
        for example in load_answers(examples):
            if example.snapshot not in repos:
                snapshot = _snapshot(example.snapshot)
                stored = store.find(snapshot)
                if stored is None or stored.index_version != version:
                    continue
                repos[example.snapshot] = DemoRepo(
                    snapshot=example.snapshot,
                    repo=f"{snapshot.owner}/{snapshot.name}",
                    sha=snapshot.sha,
                    examples=[],
                )
            if example.snapshot in repos:
                repos[example.snapshot].examples.append(example)
        return repos

    @app.get("/", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/repos")
    def list_repos() -> list[DemoRepo]:
        return list(demo_repos().values())

    @app.post("/api/ask")
    def ask(body: Question, request: Request) -> StreamingResponse:
        if body.snapshot not in demo_repos():
            raise HTTPException(404, f"{body.snapshot} is not a demo repo.")
        try:
            llm = llm_for_visitor(settings, limits, _address(request), body.api_key)
        except LimitExceeded as exc:
            raise HTTPException(429, str(exc)) from exc
        except ModelConfigError as exc:
            raise HTTPException(503, str(exc)) from exc
        config = RunConfig(llm, embedder, store, reranker, settings.runs_dir)
        snapshot = _snapshot(body.snapshot)

        def answer(events: queue.Queue[tuple[str, object] | None]) -> None:
            def progress(event: dict[str, object]) -> None:
                if event["event"] in PROGRESS_EVENTS:
                    events.put((str(event.pop("event")), event))

            try:
                report = run(body.question, snapshot, config, progress)
                events.put(("report", answer_from_report(report, llm.name, store).model_dump()))
            except Exception as exc:
                events.put(("error", {"message": _message(exc, settings)}))
            finally:
                events.put(None)

        def stream() -> Iterator[str]:
            events: queue.Queue[tuple[str, object] | None] = queue.Queue()
            threading.Thread(target=answer, args=(events,), daemon=True).start()
            while (item := events.get()) is not None:
                name, data = item
                yield f"event: {name}\ndata: {json.dumps(data)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _snapshot(text: str) -> Snapshot:
    repo = RepoRef.parse(text)
    return Snapshot(repo.owner, repo.name, repo.ref or "")


def _address(request: Request) -> str:
    """The visitor's address: the last one a proxy added, since a visitor can write the others."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else ""


def _message(exc: Exception, settings: Settings) -> str:
    """What went wrong, for the page. The Run log or the server log has the details."""
    if isinstance(exc, TimeoutError):
        return f"The model took longer than {settings.chat_timeout:g}s to answer. Try again."
    if isinstance(exc, LLMError):
        return f"The model failed: {exc}"
    logger.error("A web app question failed", exc_info=exc)
    return "Something went wrong while answering. Try again."
