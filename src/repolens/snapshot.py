import re
from dataclasses import dataclass

_REPO = re.compile(r"(?P<owner>[A-Za-z0-9-]+)/(?P<name>[A-Za-z0-9._-]+)")


@dataclass(frozen=True)
class RepoRef:
    """A repository and an optional branch, tag or commit, before it is pinned to a SHA."""

    owner: str
    name: str
    ref: str | None = None

    @classmethod
    def parse(cls, text: str) -> "RepoRef":
        """Parse `owner/repo` or `owner/repo@ref`."""
        repo, _, ref = text.partition("@")
        match = _REPO.fullmatch(repo)
        if match is None or (ref == "" and "@" in text):
            raise ValueError(f"expected owner/repo or owner/repo@ref, got {text!r}")
        return cls(match["owner"], match["name"], ref or None)


@dataclass(frozen=True)
class Snapshot:
    """A repository pinned to a commit SHA."""

    owner: str
    name: str
    sha: str

    def __str__(self) -> str:
        return f"{self.owner}/{self.name}@{self.sha}"
