from collections.abc import Iterator
from pathlib import Path

import pytest

from immepe_bot.store import JobRepository


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run in an empty directory so a developer's local .env never leaks in."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[JobRepository]:
    """An initialized job repository backed by a throwaway sqlite file."""
    repository = JobRepository(tmp_path / "jobs.db")
    repository.initialize()
    try:
        yield repository
    finally:
        repository.close()
