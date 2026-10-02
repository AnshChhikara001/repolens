"""Test doubles for the external boundaries: GitHub, embedding, reranking and chat models."""

import shutil
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from repolens.code_navigator import ToolCall
from repolens.embedding import EMBEDDING_DIMENSIONS
from repolens.llm import Reply
from repolens.snapshot import RepoRef, Snapshot

SAMPLE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"
SHA = "3f786850e387550fdab836ed7e6dc881de23001b"


class FixtureSource:
    """Serves a directory on disk as every commit of every repository."""

    def __init__(self, root: Path = SAMPLE_REPO) -> None:
        self.root = root
        self.downloads = 0

    def resolve(self, repo: RepoRef) -> Snapshot:
        return Snapshot(repo.owner, repo.name, SHA)

    def download(self, snapshot: Snapshot, dest: Path) -> None:
        self.downloads += 1
        shutil.copytree(self.root, dest, dirs_exist_ok=True)


class FakeEmbedder:
    model = "fake-embedding"

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return [[float(len(text))] + [1.0] * (EMBEDDING_DIMENSIONS - 1) for text in texts]


def fixture_source(token: str | None) -> FixtureSource:
    """Stands in for `GitHubSource(token=...)`."""
    return FixtureSource()


def fake_embedder(api_key: str) -> FakeEmbedder:
    """Stands in for `OpenAIEmbedder(api_key=...)`."""
    return FakeEmbedder()


# A Code Navigator's first Tool call that shows nothing, so the answer rests on the first search.
NOTHING_NEW = ToolCall(action="define", name="logout")


class KeywordReranker:
    """Scores a text by how many of the given words it contains."""

    def __init__(self, *words: str) -> None:
        self.words = words

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        return [float(sum(word in text for word in self.words)) for text in texts]


class ScriptedLLM:
    """Answers each call with the next scripted object of the asked-for schema.

    Records every (system, user) prompt it receives. A call with no scripted answer fails the
    test. Every call reports 1,000 input and 100 output tokens.
    """

    name = "fake:scripted"

    def __init__(self, *script: BaseModel) -> None:
        self.script = list(script)
        self.prompts: list[tuple[str, str]] = []

    def structured[T: BaseModel](self, system: str, user: str, schema: type[T]) -> Reply[T]:
        self.prompts.append((system, user))
        answer = next((a for a in self.script if isinstance(a, schema)), None)
        if answer is None:
            raise AssertionError(f"no scripted answer for {schema.__name__}")
        self.script.remove(answer)
        return Reply(answer, input_tokens=1000, output_tokens=100, latency_s=0.5)


class FailingLLM:
    """Fails every call with the given error, e.g. a timeout."""

    name = "fake:failing"

    def __init__(self, error: BaseException) -> None:
        self.error = error

    def structured[T: BaseModel](self, system: str, user: str, schema: type[T]) -> Reply[T]:
        raise self.error
