from pathlib import Path

from immepe_bot.config import Settings
from immepe_bot.preflight import check_profile_dir


def _settings(profile_dir: Path) -> Settings:
    return Settings(profile_dir=profile_dir)


def test_missing_dir_has_no_session(tmp_path: Path) -> None:
    check = check_profile_dir(_settings(tmp_path / "absent"))

    assert check.exists is False
    assert check.has_session is False


def test_empty_dir_has_no_session(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir()

    check = check_profile_dir(_settings(profile))

    assert check.exists is True
    assert check.has_session is False


def test_indexeddb_artifact_marks_session(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    artifact = (
        profile / "Default" / "IndexedDB" / "https_web.whatsapp.com_0.indexeddb.leveldb"
    )
    artifact.mkdir(parents=True)
    (artifact / "000001.log").write_text("data")

    check = check_profile_dir(_settings(profile))

    assert check.exists is True
    assert check.has_session is True


def test_populated_default_dir_marks_session(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    default = profile / "Default"
    default.mkdir(parents=True)
    (default / "Preferences").write_text("{}")

    check = check_profile_dir(_settings(profile))

    assert check.has_session is True
