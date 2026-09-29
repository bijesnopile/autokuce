"""deploy/backup.sh must never store an unencrypted backup and must fail loudly (with
instructions) when encryption is impossible — checked before anything is dumped.

Runs the real script with bash (Linux, or Git Bash on Windows); skipped without a POSIX bash.
No Docker or database is needed: the encryption check happens before pg_dump.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _bash() -> str | None:
    path = shutil.which("bash")
    if not path or "system32" in path.lower():  # WSL launcher is not a usable POSIX bash here
        return None
    return path


BASH = _bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="POSIX bash nije dostupan")


def run_backup(tmp_path: Path, env_lines: list[str], target="test-klijent", **extra_env):
    client = tmp_path / "clients" / "test-klijent"
    (client / "data" / "backups").mkdir(parents=True, exist_ok=True)
    (client / "docker-compose.yml").write_text("# test\n", encoding="utf-8")
    (client / ".env").write_text("\n".join(["CLIENT=test-klijent", *env_lines]) + "\n", "utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BACKUP_", "AGE_", "GPG_"))}
    env.update(
        CLIENTS_DIR=(tmp_path / "clients").as_posix(),
        BACKUP_ENV_FILE=(tmp_path / "no-backup.env").as_posix(),  # ignore a local deploy/backup.env
        **extra_env,
    )
    result = subprocess.run(
        [BASH, "deploy/backup.sh", target],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    output = result.stdout + result.stderr
    stored = [p.name for p in (client / "data" / "backups").iterdir()]
    return result.returncode, output, stored


AGE_KEY = "age1" + "q" * 58


def test_age_recipient_without_age_binary_fails_with_instructions(tmp_path):
    code, output, stored = run_backup(
        tmp_path, [f"BACKUP_AGE_RECIPIENT={AGE_KEY}"], AGE_BIN="/nonexistent/age"
    )
    assert code == 1
    assert "naredba 'age' nije instalirana" in output
    assert "sudo apt install age" in output and "BACKUP_GPG_RECIPIENT" in output
    assert "pg_dump" not in output  # failed before any data left the database
    assert stored == []  # nothing (and certainly nothing unencrypted) was written


def test_missing_recipient_fails_instead_of_storing_unencrypted(tmp_path):
    code, output, stored = run_backup(tmp_path, [])
    assert code == 1
    assert "nije postavljen BACKUP_AGE_RECIPIENT ni BACKUP_GPG_RECIPIENT" in output
    assert "pg_dump" not in output and stored == []


def test_invalid_age_recipient_is_rejected(tmp_path):
    # `true` exists everywhere, so only the recipient format is checked.
    code, output, stored = run_backup(tmp_path, ["BACKUP_AGE_RECIPIENT=not-a-key"], AGE_BIN="true")
    assert code == 1 and "ne izgleda kao javni age ključ" in output and stored == []


def test_gpg_recipient_without_gpg_binary_fails(tmp_path):
    code, output, stored = run_backup(
        tmp_path, ["BACKUP_GPG_RECIPIENT=backup@primjer.hr"], GPG_BIN="/nonexistent/gpg"
    )
    assert code == 1 and "naredba 'gpg' nije instalirana" in output and stored == []


def test_all_mode_reports_failed_clients_with_nonzero_exit(tmp_path):
    code, output, _ = run_backup(
        tmp_path, [f"BACKUP_AGE_RECIPIENT={AGE_KEY}"], target="all", AGE_BIN="/nonexistent/age"
    )
    assert code == 1
    assert "backup NIJE uspio za: test-klijent" in output
