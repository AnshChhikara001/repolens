"""Test doubles for the ingest boundaries: a repo on disk and a deterministic embedder."""

import shutil
from collections.abc import Sequence
from pathlib import Path

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
