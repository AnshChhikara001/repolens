"""Resolve and download repository Snapshots from GitHub."""

import tarfile
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx2

from repolens.ingest import IngestError
from repolens.snapshot import RepoRef, Snapshot

API_URL = "https://api.github.com"


class GitHubSource:
    def __init__(
        self, token: str | None = None, transport: httpx2.BaseTransport | None = None
    ) -> None:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx2.Client(
            base_url=API_URL,
            headers=headers,
            timeout=30,
            follow_redirects=True,
            transport=transport,
        )

    def resolve(self, repo: RepoRef) -> Snapshot:
        with _wrap_errors():
            return self._resolve(repo)

    def download(self, snapshot: Snapshot, dest: Path) -> None:
        with _wrap_errors():
            self._download(snapshot, dest)

    def _resolve(self, repo: RepoRef) -> Snapshot:
        response = self._client.get(f"/repos/{repo.owner}/{repo.name}")
        if response.status_code == 404:
            raise IngestError(f"repository {repo.owner}/{repo.name} not found")
        _raise_for_status(response)
        data = response.json()
        full_name: str = data["full_name"]
        ref: str = repo.ref or data["default_branch"]

        response = self._client.get(
            f"/repos/{full_name}/commits/{quote(ref, safe='')}",
            headers={"Accept": "application/vnd.github.sha"},
        )
        if response.status_code in (404, 422):
            raise IngestError(f"ref {ref!r} not found in {full_name}")
        _raise_for_status(response)
        owner, name = full_name.split("/")
        return Snapshot(owner, name, response.text.strip())

    def _download(self, snapshot: Snapshot, dest: Path) -> None:
        with tempfile.TemporaryFile() as archive:
            url = f"/repos/{snapshot.owner}/{snapshot.name}/tarball/{snapshot.sha}"
            with self._client.stream("GET", url) as response:
                _raise_for_status(response)
                for data in response.iter_bytes():
                    archive.write(data)
            archive.seek(0)
            with tarfile.open(fileobj=archive, mode="r:gz") as tar:
                for member in tar:
                    # Paths start with a single `owner-repo-sha/` directory. Links are skipped.
                    parts = PurePosixPath(member.name).parts[1:]
                    if member.isfile() and parts:
                        tar.extract(member.replace(name="/".join(parts)), dest, filter="data")


@contextmanager
def _wrap_errors() -> Generator[None]:
    try:
        yield
    except httpx2.HTTPError as exc:
        raise IngestError(f"can't reach GitHub: {exc}") from exc
    except tarfile.TarError as exc:
        raise IngestError(f"bad tarball from GitHub: {exc}") from exc


def _raise_for_status(response: httpx2.Response) -> None:
    if response.is_success:
        return
    response.read()
    raise IngestError(f"GitHub API returned {response.status_code}: {response.text[:200]}")
