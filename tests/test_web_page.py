"""The web page in a real browser, against the app with a scripted model."""

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fakes import NOTHING_NEW, SHA, FakeEmbedder, FixtureSource, ScriptedLLM
from playwright.sync_api import Page, expect
from pydantic import SecretStr

from repolens import limits
from repolens.code_navigator import AgentAction
from repolens.config import Settings
from repolens.ingest import ingest
from repolens.report import Citation, Finding
from repolens.report_writer import ReportDraft
from repolens.snapshot import RepoRef
from repolens.store import ChunkStore
from repolens.web.app import create_app

pytestmark = pytest.mark.usefixtures("clean_env")

SNAPSHOT = f"acme/shop@{SHA}"
SALT_URL = f"https://github.com/acme/shop/blob/{SHA}/app/auth.py#L3-L3"
EXAMPLE: dict[str, Any] = {
    "snapshot": SNAPSHOT,
    "question": "Where is the salt?",
    "answer": "In the `SALT` constant [1].",
    "findings": [
        {
            "claim": "The salt is a module constant.",
            "citations": [
                {
                    "path": "app/auth.py",
                    "start_line": 3,
                    "end_line": 3,
                    "symbol": None,
                    "url": SALT_URL,
                    "code": 'SALT = "pepper"',
                }
            ],
        }
    ],
    "model": "Claude Sonnet 5",
    "rejected": 0,
    "calls": 3,
    "input_tokens": 30_000,
    "output_tokens": 900,
    "duration_s": 40.0,
}
HASHED = Finding(
    claim="Passwords are hashed with SHA-256 and a fixed salt.",
    citations=[Citation(path="app/auth.py", start_line=6, end_line=7, symbol="hash_password")],
)


@pytest.fixture
def site(store: ChunkStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """The app on a free local port, allowing one question an hour on our key."""
    ingest(RepoRef("acme", "shop"), FixtureSource(), FakeEmbedder(), store)
    examples = tmp_path / "examples.json"
    examples.write_text(json.dumps([EXAMPLE]))

    def scripted_model(settings: Settings, api_key: str | None = None) -> ScriptedLLM:
        return ScriptedLLM(
            NOTHING_NEW,
            AgentAction(action="answer", findings=[HASHED]),
            ReportDraft(answer="Salted SHA-256 [1]."),
        )

    monkeypatch.setattr(limits, "build_llm", scripted_model)
    settings = Settings(
        database_url=store.url,
        runs_dir=tmp_path / "runs",
        google_api_key=SecretStr("our-key"),
        demo_runs_per_hour=1,
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    app = create_app(settings, FakeEmbedder(), None, examples)
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


def test_a_saved_answer_shows_on_load_and_its_citation_opens_to_the_code(
    site: str, page: Page
) -> None:
    page.goto(site)

    answer = page.locator("#answer")
    expect(page.get_by_role("radio", name="acme/shop")).to_be_checked()
    expect(answer.get_by_role("heading")).to_have_text("Where is the salt?")
    expect(answer).to_contain_text("Saved answer by Claude Sonnet 5, about acme/shop@3f78685.")
    page.get_by_role("link", name="Finding 1").click()
    expect(answer.locator("pre")).to_be_visible()
    expect(answer.locator("pre .line")).to_have_text('3SALT = "pepper"')  # line number, line
    expect(answer.get_by_role("link", name="Open these lines on GitHub")).to_have_attribute(
        "href", SALT_URL
    )


def test_a_question_shows_its_steps_and_answer_then_the_limit_offers_an_own_key(
    site: str, page: Page
) -> None:
    page.goto(site)
    question = page.get_by_label("Question")

    question.fill("How are passwords stored?")
    question.press("Enter")

    answer = page.locator("#answer")
    expect(answer).to_contain_text("Answered just now by scripted")
    expect(answer.locator(".prose")).to_have_text("Salted SHA-256 1.")
    steps = page.locator("#steps li")
    expect(steps.first).to_have_text(
        "Searched for “How are passwords stored?” and found 6 excerpts"
    )
    expect(steps.last).to_have_text("Writing the answer from what it found")

    page.get_by_role("button", name="Ask").click()

    expect(page.get_by_role("alert")).to_contain_text("1 questions an hour")
    expect(page.get_by_label("Gemini API key")).to_be_focused()
    expect(answer).to_contain_text("Salted SHA-256")  # the last answer stays
