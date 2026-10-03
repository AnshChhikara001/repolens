import json
from pathlib import Path
from typing import Any

import pytest
from fakes import NOTHING_NEW, SHA, FailingLLM, FakeEmbedder, FixtureSource, ScriptedLLM
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr
from typer.testing import CliRunner

from repolens import cli, limits
from repolens.code_navigator import AgentAction
from repolens.config import Settings
from repolens.ingest import ingest
from repolens.llm import LLM, LLMError
from repolens.report import Citation, Finding
from repolens.report_writer import ReportDraft
from repolens.snapshot import RepoRef
from repolens.store import ChunkStore
from repolens.web.app import create_app

pytestmark = pytest.mark.usefixtures("clean_env")

SNAPSHOT = f"acme/shop@{SHA}"
QUESTION = "How are passwords stored?"
HASHED = Finding(
    claim="Passwords are hashed with SHA-256 and a fixed salt.",
    citations=[Citation(path="app/auth.py", start_line=6, end_line=7, symbol="hash_password")],
)
EXAMPLE: dict[str, Any] = {
    "snapshot": SNAPSHOT,
    "question": "Where is the salt?",
    "answer": "In a constant [1].",
    "findings": [],
    "model": "Claude Sonnet 5",
    "rejected": 0,
    "calls": 3,
    "input_tokens": 30_000,
    "output_tokens": 900,
    "duration_s": 40.0,
}


class Models:
    """Stands in for `build_llm`: the next scripted model, and the keys it was built with."""

    def __init__(self) -> None:
        self.next: LLM = ScriptedLLM()
        self.keys: list[str | None] = []

    def __call__(self, settings: Settings, api_key: str | None = None) -> LLM:
        self.keys.append(api_key)
        return self.next

    def script(self, *answers: BaseModel) -> None:
        self.next = ScriptedLLM(*answers)


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch) -> Models:
    models = Models()
    monkeypatch.setattr(limits, "build_llm", models)
    return models


@pytest.fixture
def examples(tmp_path: Path) -> Path:
    path = tmp_path / "examples.json"
    elsewhere = {**EXAMPLE, "snapshot": f"acme/other@{SHA}"}  # never ingested
    path.write_text(json.dumps([EXAMPLE, elsewhere]))
    return path


@pytest.fixture
def client(store: ChunkStore, examples: Path, tmp_path: Path) -> TestClient:
    ingest(RepoRef("acme", "shop"), FixtureSource(), FakeEmbedder(), store)
    settings = Settings(
        database_url=store.url,
        runs_dir=tmp_path / "runs",
        google_api_key=SecretStr("our-key"),
        demo_runs_per_hour=1,
    )
    return TestClient(create_app(settings, FakeEmbedder(), None, examples))


def ask(client: TestClient, **body: Any) -> list[tuple[str, dict[str, Any]]]:
    """POST a question and return the streamed (event, data) pairs."""
    response = client.post("/api/ask", json={"snapshot": SNAPSHOT, "question": QUESTION, **body})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events: list[tuple[str, dict[str, Any]]] = []
    for message in response.text.strip().split("\n\n"):
        event, data = message.split("\n")
        events.append((event.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def test_the_page_is_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "<title>repolens</title>" in response.text


def test_only_ingested_repos_are_listed_with_their_example_answers(client: TestClient) -> None:
    response = client.get("/api/repos")

    assert response.status_code == 200
    assert response.json() == [
        {"snapshot": SNAPSHOT, "repo": "acme/shop", "sha": SHA, "examples": [EXAMPLE]}
    ]


def test_an_answer_streams_its_steps_then_the_cited_report(
    client: TestClient, models: Models
) -> None:
    models.script(
        NOTHING_NEW,
        AgentAction(action="answer", findings=[HASHED]),
        ReportDraft(answer="Salted SHA-256 [1]."),
    )

    events = ask(client)

    names = [name for name, _ in events]
    assert names == ["tool", "call", "step", "tool", "call", "step", "call", "report"]
    first_search = events[0][1]
    assert first_search["tool"] == "search_code"
    assert first_search["args"] == {"query": QUESTION}
    report = events[-1][1]
    assert report["snapshot"] == SNAPSHOT
    assert report["question"] == QUESTION
    assert report["answer"] == "Salted SHA-256 [1]."
    assert report["model"] == "scripted"
    assert report["calls"] == 3
    assert (report["input_tokens"], report["output_tokens"]) == (3000, 300)
    [finding] = report["findings"]
    assert finding["claim"] == HASHED.claim
    assert finding["citations"] == [
        {
            "path": "app/auth.py",
            "start_line": 6,
            "end_line": 7,
            "symbol": "hash_password",
            "url": f"https://github.com/acme/shop/blob/{SHA}/app/auth.py#L6-L7",
            "code": "def hash_password(password: str) -> str:\n"
            "    return hashlib.sha256((SALT + password).encode()).hexdigest()",
        }
    ]


def test_a_repo_that_is_not_ingested_cannot_be_asked_about(
    client: TestClient, models: Models
) -> None:
    response = client.post("/api/ask", json={"snapshot": f"acme/other@{SHA}", "question": QUESTION})

    assert response.status_code == 404
    assert models.keys == []


def test_over_the_limit_the_page_is_told_and_an_own_key_still_works(
    client: TestClient, models: Models
) -> None:
    models.script(NOTHING_NEW, AgentAction(action="answer", findings=[]))
    ask(client)

    response = client.post("/api/ask", json={"snapshot": SNAPSHOT, "question": QUESTION})

    assert response.status_code == 429
    assert "1 questions an hour" in response.json()["detail"]
    models.script(NOTHING_NEW, AgentAction(action="answer", findings=[]))
    assert ask(client, api_key="their-key")[-1][0] == "report"
    assert models.keys == [None, None, "their-key"]


def test_the_visitor_address_is_the_one_the_proxy_added(client: TestClient, models: Models) -> None:
    def status(forwarded_for: str) -> int:
        models.script(NOTHING_NEW, AgentAction(action="answer", findings=[]))
        body = {"snapshot": SNAPSHOT, "question": QUESTION}
        headers = {"X-Forwarded-For": forwarded_for}
        return client.post("/api/ask", json=body, headers=headers).status_code

    assert status("1.1.1.1, 6.6.6.6") == 200
    assert status("2.2.2.2, 6.6.6.6") == 429  # the visitor wrote the first address
    assert status("7.7.7.7") == 200


def test_a_failed_model_call_ends_the_stream_with_a_message(
    client: TestClient, models: Models
) -> None:
    models.next = FailingLLM(LLMError("google:gemini: 400 INVALID_ARGUMENT, API key not valid"))

    events = ask(client, api_key="wrong-key")

    assert events[-1] == (
        "error",
        {"message": "The model failed: google:gemini: 400 INVALID_ARGUMENT, API key not valid"},
    )


def test_a_slow_model_ends_the_stream_with_a_message(client: TestClient, models: Models) -> None:
    models.next = FailingLLM(TimeoutError())

    events = ask(client)

    assert events[-1][0] == "error"
    assert "took longer than" in events[-1][1]["message"]


def test_a_question_must_not_be_empty(client: TestClient, models: Models) -> None:
    response = client.post("/api/ask", json={"snapshot": SNAPSHOT, "question": "  "})

    assert response.status_code == 422
    assert models.keys == []


def test_the_web_command_serves_the_app_in_one_process(
    offline: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    served: list[tuple[object, str, int]] = []

    def serve(app: object, host: str, port: int) -> None:
        served.append((app, host, port))

    monkeypatch.setattr(cli.uvicorn, "run", serve)

    result = CliRunner().invoke(cli.app, ["web", "--port", "8001"])

    assert result.exit_code == 0, result.output
    [(app, host, port)] = served
    assert isinstance(app, FastAPI)
    assert (host, port) == ("127.0.0.1", 8001)
    assert "http://127.0.0.1:8001" in result.output
