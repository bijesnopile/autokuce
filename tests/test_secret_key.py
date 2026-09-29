"""SECRET_KEY lifecycle: never regenerated silently, persisted once, change detected."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from app.config import SecretKeyError, Settings, ensure_secret_key

ROOT = Path(__file__).resolve().parent.parent


def prod(tmp_path: Path, key: str = "") -> Settings:
    return Settings(
        _env_file=None,
        APP_ENV="production",
        SECRET_KEY=key,
        DATA_DIR=tmp_path,
        DATABASE_URL="postgresql://u:p@db:5432/app",
    )


def test_production_without_key_refuses_and_generates_nothing(tmp_path):
    settings = prod(tmp_path)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.validate_for_startup()
    with pytest.raises(SecretKeyError):
        _ = settings.secret_key
    assert list(tmp_path.iterdir()) == []  # no silently generated key file


def test_production_reads_persisted_key_file_and_env_wins(tmp_path):
    (tmp_path / ".secret_key").write_text("k" * 64 + "\n", encoding="utf-8")
    settings = prod(tmp_path)
    settings.validate_for_startup()
    assert settings.secret_key == "k" * 64
    assert prod(tmp_path, key="e" * 40).secret_key == "e" * 40


def test_ensure_secret_key_generates_once_and_never_again(tmp_path):
    settings = prod(tmp_path)
    assert ensure_secret_key(settings) == "generated"
    key_file = tmp_path / ".secret_key"
    first = key_file.read_text(encoding="utf-8")
    assert len(first) >= 32
    # Second, third... start: the same key is reused, never regenerated.
    assert ensure_secret_key(prod(tmp_path)) == "file"
    assert ensure_secret_key(prod(tmp_path)) == "file"
    assert key_file.read_text(encoding="utf-8") == first
    assert prod(tmp_path).secret_key == first.strip()
    if os.name == "posix":
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600


def test_ensure_secret_key_with_env_key_writes_nothing(tmp_path):
    assert ensure_secret_key(prod(tmp_path, key="e" * 40)) == "env"
    assert not (tmp_path / ".secret_key").exists()


def test_ensure_secret_key_refuses_short_file_and_ephemeral_container_dir(tmp_path, monkeypatch):
    (tmp_path / ".secret_key").write_text("short", encoding="utf-8")
    with pytest.raises(SecretKeyError, match="prekratak"):
        ensure_secret_key(prod(tmp_path))

    ephemeral = tmp_path / "container-data"
    monkeypatch.setattr("app.config.running_in_container", lambda: True)
    monkeypatch.setattr("app.config.os.path.ismount", lambda path: False)
    with pytest.raises(SecretKeyError, match="nije trajni volumen"):
        ensure_secret_key(prod(ephemeral))
    assert not (ephemeral / ".secret_key").exists()


def test_development_key_is_generated_once_and_persisted(tmp_path):
    first = Settings(_env_file=None, APP_ENV="development", SECRET_KEY="", DATA_DIR=tmp_path)
    second = Settings(_env_file=None, APP_ENV="development", SECRET_KEY="", DATA_DIR=tmp_path)
    assert first.secret_key == second.secret_key
    assert (tmp_path / ".dev_secret_key").exists()


def test_check_secret_key_stores_fingerprint_and_refuses_a_changed_key(db, monkeypatch, caplog):
    from app.cli import SECRET_FINGERPRINT_KEY, main
    from app.config import get_settings
    from app.models import Setting

    assert main(["check-secret-key"]) == 0  # first start: fingerprint stored
    stored = db.get(Setting, SECRET_FINGERPRINT_KEY).value
    assert get_settings().secret_key not in stored  # only a fingerprint, never the key
    assert main(["check-secret-key"]) == 0  # same key: OK

    monkeypatch.setattr(get_settings(), "SECRET_KEY", "a-completely-different-key-0123456789")
    assert main(["check-secret-key"]) == 1  # lost/changed key: start refused
    assert "ne podudara" in caplog.text
    assert main(["check-secret-key", "--accept"]) == 0  # deliberate rotation
    assert main(["check-secret-key"]) == 0
    db.expire_all()
    assert db.get(Setting, SECRET_FINGERPRINT_KEY).value != stored


def test_docker_entrypoint_uses_persistent_key_and_checks_it():
    script = (ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
    assert "secrets.token" not in script  # the entrypoint itself never generates a key
    ensure = script.index("python -m app.cli ensure-secret-key")
    seed = script.index("python -m app.seed --minimal --if-empty")
    check = script.index("python -m app.cli check-secret-key")
    assert ensure < seed < check < script.index('exec "$@"')
