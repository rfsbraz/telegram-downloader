"""Release flow: release-please on develop, a sync PR into main, release builds from main.

These tests read the workflow files and run scripts/find-release.sh against small local repos.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
FIND_RELEASE = ROOT / "scripts" / "find-release.sh"


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key `on` as True.
    return workflow.get("on", workflow.get(True))


def steps_text(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


# --- workflows -------------------------------------------------------------


def test_release_please_runs_on_develop_only():
    wf = load(WORKFLOWS / "release.yml")
    assert triggers(wf)["push"]["branches"] == ["develop"]
    step = next(s for s in wf["jobs"]["release-please"]["steps"] if s.get("id") == "release")
    assert step["with"]["target-branch"] == "develop"


def test_sync_to_main_merges_the_tagged_commit_with_a_merge_commit():
    wf = load(WORKFLOWS / "release.yml")
    job = wf["jobs"]["sync-to-main"]
    assert job["needs"] == "release-please"
    assert "release_created == 'true'" in job["if"]
    assert job["runs-on"] == "ubuntu-latest"
    env = job["steps"][0]["env"]
    assert env["GH_TOKEN"] == "${{ secrets.RELEASE_PLEASE_TOKEN }}"
    run = steps_text(job)
    assert 'branch="sync/develop-to-main-$TAG"' in run
    assert "--base main" in run
    assert 'gh pr merge "$url" --merge --match-head-commit "$sha"' in run
    assert "--squash" not in run and "--auto" not in run


def test_github_release_is_published_not_drafted():
    config = json.loads((ROOT / "release-please-config.json").read_text())
    assert config["packages"]["."]["draft"] is False


def test_ci_runs_on_main_and_develop():
    on = triggers(load(WORKFLOWS / "ci.yml"))
    assert sorted(on["push"]["branches"]) == ["develop", "main"]
    assert sorted(on["pull_request"]["branches"]) == ["develop", "main"]


def test_docker_release_tags_come_only_from_a_release_sync_on_main():
    wf = load(WORKFLOWS / "docker.yml")
    on = triggers(wf)
    assert "tags" not in on["push"]
    assert sorted(on["push"]["branches"]) == ["develop", "main"]
    steps = wf["jobs"]["build"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0
    find = next(s for s in steps if s.get("id") == "rel")
    assert find["run"] == "bash scripts/find-release.sh"
    assert find["if"] == "${{ github.ref == 'refs/heads/main' }}"
    stop = next(s for s in steps if s.get("name", "").startswith("Stop on a push to main"))
    assert "steps.rel.outputs.release != 'true'" in stop["if"]
    tags = next(s for s in steps if s.get("id") == "meta")["with"]["tags"]
    assert "type=raw,value=latest,enable=${{ steps.rel.outputs.release == 'true' }}" in tags
    assert tags.count("value=${{ steps.rel.outputs.tag }}") == 3


def test_dependabot_targets_develop():
    updates = load(ROOT / ".github" / "dependabot.yml")["updates"]
    assert updates
    assert all(u.get("target-branch") == "develop" for u in updates)


# --- scripts/find-release.sh ----------------------------------------------


def git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def commit(repo: Path, version: str, message: str) -> str:
    (repo / ".release-please-manifest.json").write_text(json.dumps({".": version}))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def find_release(repo: Path, sha: str, tmp_path: Path) -> tuple[subprocess.CompletedProcess, dict]:
    out = tmp_path / "out.txt"
    out.write_text("")
    env = {**os.environ, "GITHUB_SHA": sha, "TAG_GLOB": "v*", "GITHUB_OUTPUT": str(out)}
    proc = subprocess.run(
        ["bash", str(FIND_RELEASE)], cwd=repo, env=env, capture_output=True, text=True
    )
    values = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    return proc, values


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("jq") is None:
        pytest.skip("jq is not installed")
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    commit(path, "1.5.0", "chore(main): release 1.5.0")
    git(path, "tag", "v1.5.0")
    git(path, "switch", "-q", "-c", "develop")
    commit(path, "1.5.0", "feat: something new (#1)")
    return path


def sync(repo: Path, tag: str | None) -> str:
    """Tag develop (as release-please does) and merge it into main with a merge commit."""
    if tag:
        git(repo, "tag", tag, "develop")
    git(repo, "switch", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "chore(release): sync to main", "develop")
    return git(repo, "rev-parse", "HEAD")


def test_release_sync_merge_is_a_release(repo, tmp_path):
    commit(repo, "1.6.0", "chore(develop): release 1.6.0 (#2)")
    proc, out = find_release(repo, sync(repo, "v1.6.0"), tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert out == {"release": "true", "tag": "v1.6.0", "version": "1.6.0"}


def test_squash_or_direct_push_to_main_is_not_a_release(repo, tmp_path):
    git(repo, "switch", "-q", "main")
    sha = commit(repo, "1.5.0", "fix: pushed straight to main")
    proc, out = find_release(repo, sha, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert out == {"release": "false"}


def test_merge_of_an_untagged_commit_is_not_a_release(repo, tmp_path):
    proc, out = find_release(repo, sync(repo, None), tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert out == {"release": "false"}


def test_tag_that_does_not_match_the_manifest_fails(repo, tmp_path):
    commit(repo, "1.6.0", "chore(develop): release 1.6.0 (#2)")
    proc, out = find_release(repo, sync(repo, "v1.7.0"), tmp_path)
    assert proc.returncode != 0
    assert "does not match manifest" in proc.stderr
    assert "release" not in out
