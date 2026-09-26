import io
import tarfile
from pathlib import Path

import httpx2
import pytest

from repolens.github import GitHubSource
from repolens.ingest import IngestError
from repolens.snapshot import RepoRef, Snapshot

SHA = "3f786850e387550fdab836ed7e6dc881de23001b"


def tarball(files: dict[str, str]) -> bytes:
    """A GitHub-style tarball: every path sits under one top-level directory."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"Acme-Shop-3f78685/{path}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo("Acme-Shop-3f78685/escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        tar.addfile(link)
    return buffer.getvalue()


def fake_github(request: httpx2.Request) -> httpx2.Response:
    routes = {
        "/repos/acme/shop": httpx2.Response(
            200, json={"full_name": "Acme/Shop", "default_branch": "main"}
        ),
        "/repos/Acme/Shop/commits/main": httpx2.Response(200, text=SHA),
        f"/repos/Acme/Shop/tarball/{SHA}": httpx2.Response(
            302, headers={"Location": f"https://codeload.github.com/Acme/Shop/legacy.tar.gz/{SHA}"}
        ),
        f"/Acme/Shop/legacy.tar.gz/{SHA}": httpx2.Response(
            200, content=tarball({"app/auth.py": "def login(): ...\n"})
        ),
    }
    return routes.get(request.url.path, httpx2.Response(404, json={"message": "Not Found"}))


def source() -> GitHubSource:
    return GitHubSource(transport=httpx2.MockTransport(fake_github))


def test_resolve_pins_the_default_branch_to_a_sha() -> None:
    assert source().resolve(RepoRef("acme", "shop")) == Snapshot("Acme", "Shop", SHA)


def test_unknown_repository_is_an_ingest_error() -> None:
    with pytest.raises(IngestError, match="acme/missing not found"):
        source().resolve(RepoRef("acme", "missing"))


def test_unknown_ref_is_an_ingest_error() -> None:
    with pytest.raises(IngestError, match="ref 'nope' not found"):
        source().resolve(RepoRef("acme", "shop", "nope"))


def test_download_extracts_regular_files_without_the_top_directory(tmp_path: Path) -> None:
    source().download(Snapshot("Acme", "Shop", SHA), tmp_path)

    assert [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()] == [
        "app/auth.py"
    ]
    assert (tmp_path / "app/auth.py").read_text() == "def login(): ...\n"
