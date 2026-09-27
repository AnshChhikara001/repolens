"""Test doubles for the external boundaries: GitHub, the embedding API and chat models."""

import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field

from repolens.embedding import EMBEDDING_DIMENSIONS
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


class ScriptedChatModel(BaseChatModel):
    """Answers each structured-output call with the next scripted object of the asked-for schema.

    Records every prompt it receives. A call with no scripted answer fails the test.
    """

    script: list[BaseModel]
    prompts: list[list[BaseMessage]] = Field(default_factory=list[list[BaseMessage]])

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        names = [convert_to_openai_tool(tool)["function"]["name"] for tool in tools]
        return self.bind(tool_names=names)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        tool_names: Sequence[str] = (),
        **kwargs: Any,
    ) -> ChatResult:
        self.prompts.append(messages)
        answer = next((a for a in self.script if type(a).__name__ in tool_names), None)
        if answer is None:
            raise AssertionError(f"no scripted answer for {list(tool_names)}")
        self.script.remove(answer)
        call = {"name": type(answer).__name__, "args": answer.model_dump(), "id": "call"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage("", tool_calls=[call]))])
