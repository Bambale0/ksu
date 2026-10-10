"""Execute the actual deployment preflight only, against synthetic git/env fixtures."""

import os
import subprocess
import textwrap
from pathlib import Path

import pytest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/deploy-production.yml"
SYNTHETIC_KEY = "test-only-admin-key-with-32-chars!"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
        text=True,
        stderr=subprocess.PIPE,
        env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"},
    ).strip()


@pytest.fixture
def release_repo(tmp_path: Path) -> tuple[Path, str, str]:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-b", "main")
    _git(origin, "config", "user.name", "Deployment test")
    _git(origin, "config", "user.email", "deployment@example.invalid")
    (origin / ".gitignore").write_text(".env\nstatic/uploads/\napp/web/mini_app/release.json\n")
    (origin / "docker-compose.yml").write_text("services: {}\n")
    (origin / "version.txt").write_text("old release\n")
    (origin / "app/web/mini_app").mkdir(parents=True)
    (origin / "app/web/mini_app/README.md").write_text("Generated release marker\n")
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "Baseline")
    previous = _git(origin, "rev-parse", "HEAD")
    checkout = tmp_path / "checkout"
    _git(tmp_path, "clone", str(origin), str(checkout))
    (origin / "version.txt").write_text("new release\n")
    (origin / "new.txt").write_text("release-owned file\n")
    (origin / "static/uploads").mkdir(parents=True)
    (origin / "static/uploads/new.txt").write_text("release collision fixture\n")
    _git(origin, "add", ".")
    _git(origin, "add", "-f", "static/uploads/new.txt")
    _git(origin, "commit", "-m", "Candidate")
    target = _git(origin, "rev-parse", "HEAD")
    (checkout / ".env").write_text(f"ADMIN_SECURITY_KEY={SYNTHETIC_KEY}\n")
    return checkout, previous, target


def _run_preflight(repo: Path, target: str) -> subprocess.CompletedProcess[str]:
    remote = WORKFLOW.read_text().split("<<'REMOTE'\n", 1)[1].split("          REMOTE", 1)[0]
    preflight = textwrap.dedent(remote).split("docker compose config -q", 1)[0]
    # Diagnostics must never reach a Docker daemon when testing the workflow.
    return subprocess.run(
        ["bash", "-c", 'docker() { return 0; }; export -f docker\n' + preflight],
        cwd=repo,
        text=True,
        capture_output=True,
        env={**os.environ, "DEPLOY_PATH": str(repo), "DEPLOY_SHA": target,
             "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"},
        timeout=15,
    )


@pytest.mark.parametrize("value", [None, "", "short", "x" * 31, '\"   \"', "# empty"])
def test_invalid_admin_key_stops_before_checkout_without_rewriting_env(release_repo, value):
    repo, previous, target = release_repo
    contents = "UNRELATED=preserved\n"
    if value is not None:
        contents += f"ADMIN_SECURITY_KEY={value}\n"
    env_file = repo / ".env"
    env_file.write_text(contents)
    env_file.chmod(0o640)

    result = _run_preflight(repo, target)

    assert result.returncode != 0
    assert "ADMIN_SECURITY_KEY must be configured with at least 32 characters" in result.stderr
    assert env_file.read_text() == contents
    assert env_file.stat().st_mode & 0o777 == 0o640
    assert _git(repo, "rev-parse", "HEAD") == previous
    assert "short" not in result.stdout + result.stderr


@pytest.mark.parametrize("value", [SYNTHETIC_KEY, f'"{SYNTHETIC_KEY}"',
                                   f"'{SYNTHETIC_KEY}'", f"{SYNTHETIC_KEY} # comment"])
def test_valid_admin_key_deploys_exact_sha_preserving_existing_artifacts(release_repo, value):
    repo, _previous, target = release_repo
    artifacts = {
        ".env": f"ADMIN_SECURITY_KEY={value}\nUNRELATED=preserved\n",
        "static/uploads/feed/retained.txt": "historical media\n",
        "backups/predeploy-20000101T000000Z-old.dump": "historical archive\n",
        "backups/predeploy-20000101T000000Z-old.dump.sha256": "historical checksum\n",
    }
    for name, contents in artifacts.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    (repo / "app/web/mini_app/release.json").write_text('{"sha":"previous"}\n')

    result = _run_preflight(repo, target)

    assert result.returncode == 0, result.stderr
    assert _git(repo, "rev-parse", "HEAD") == target
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    for name, contents in artifacts.items():
        assert (repo / name).read_text() == contents
    assert (repo / "app/web/mini_app/release.json").read_text() == f'{{"sha":"{target}"}}\n'
    assert SYNTHETIC_KEY not in result.stdout + result.stderr


@pytest.mark.parametrize("staged", [False, True])
def test_dirty_tracked_checkout_fails_closed(release_repo, staged):
    repo, previous, target = release_repo
    (repo / "version.txt").write_text("operator work must survive\n")
    if staged:
        _git(repo, "add", "version.txt")

    result = _run_preflight(repo, target)

    assert result.returncode != 0
    assert "tracked changes" in result.stderr
    assert _git(repo, "rev-parse", "HEAD") == previous
    assert (repo / "version.txt").read_text() == "operator work must survive\n"


@pytest.mark.parametrize("filename", ["new.txt", "static/uploads/new.txt"])
def test_untracked_and_ignored_collisions_fail_closed(release_repo, filename):
    repo, previous, target = release_repo
    collision = repo / filename
    collision.parent.mkdir(parents=True, exist_ok=True)
    collision.write_text("operator file must survive\n")

    result = _run_preflight(repo, target)

    assert result.returncode != 0
    assert _git(repo, "rev-parse", "HEAD") == previous
    assert collision.read_text() == "operator file must survive\n"
