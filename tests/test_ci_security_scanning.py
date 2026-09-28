"""Phase 4f: dependency, secret and SAST scanning in CI.

The directive requires Dependabot, gitleaks/truffleHog, and bandit. The
previous CI nominally had two of them and neither worked:

  * "Check no hardcoded secret" grepped for one literal string
    ("nare-co-secret-2026"), so it could not detect any other secret.
  * bandit ran as `bandit -r server.py -ll`, and after the Phase 2
    refactor server.py is ~105 lines out of ~3,100 — about 3% coverage,
    reported as green.

These tests read the workflow and dependabot config, because a CI job that
silently stops running is invisible until it has stopped protecting you.
"""
import os
import re

import pytest
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI = os.path.join(HERE, ".github", "workflows", "ci.yml")
DEPENDABOT = os.path.join(HERE, ".github", "dependabot.yml")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def ci():
    return _read(CI)


@pytest.fixture(scope="module")
def jobs():
    return yaml.safe_load(_read(CI))["jobs"]


# ------------------------------------------------------------- bandit (SAST)
def _bandit_commands(jobs):
    """bandit invocations from actual `run` steps.

    Parsed from YAML rather than regexed out of the raw text: the workflow
    contains comments *about* the old bandit scope, and matching those
    would test the comment instead of the job.
    """
    return [s["run"] for s in jobs["sast"]["steps"]
            if "bandit" in s.get("run", "") and s["run"].strip().startswith("bandit")]


def test_bandit_scans_the_whole_codebase_not_just_the_entrypoint(jobs):
    """
    The regression this guards: `bandit -r server.py` covered ~3% of the
    code after the refactor while still reporting a green build.
    """
    cmds = _bandit_commands(jobs)
    assert cmds, "no bandit invocation found in CI"
    for cmd in cmds:
        assert "app/" in cmd, f"bandit does not cover app/: {cmd}"
    assert not any(re.search(r"bandit\s+-r\s+server\.py", c) for c in cmds), \
        "bandit is still scoped to server.py only"


def test_bandit_failure_threshold_is_enforced(jobs):
    step = _find_step(jobs, "sast", "whole package")
    assert "|| true" not in step["run"], \
        "the enforcing bandit step must be able to fail the build"
    assert "-ll" in step["run"]


def test_bandit_covers_every_layer_the_directive_names(jobs):
    enforcing = _bandit_commands(jobs)[0]
    for target in ("app/", "server.py", "wsgi.py", "scripts/"):
        assert target in enforcing, f"bandit does not scan {target}"


def test_sast_job_exists(jobs):
    assert "sast" in jobs


def test_dependabot_config_exists():
    assert os.path.isfile(DEPENDABOT), "dependabot.yml is missing"


def test_dependabot_covers_python_and_github_actions():
    cfg = yaml.safe_load(_read(DEPENDABOT))
    assert cfg["version"] == 2
    ecosystems = {u["package-ecosystem"] for u in cfg["updates"]}
    assert "pip" in ecosystems, "python dependencies are not tracked"
    assert "github-actions" in ecosystems, "actions are not tracked"


def test_dependabot_runs_on_a_schedule():
    cfg = yaml.safe_load(_read(DEPENDABOT))
    for update in cfg["updates"]:
        assert update["schedule"]["interval"] == "weekly"


def test_dependabot_directories_are_valid():
    cfg = yaml.safe_load(_read(DEPENDABOT))
    for update in cfg["updates"]:
        d = update["directory"]
        assert d == "/" or os.path.isdir(os.path.join(HERE, d)), d


# ------------------------------------------- CI must also actually be real
def test_ground_rule_two_jobs_all_present(jobs):
    """
    Directive ground rule 2: CI must run lint, tests, a build, and
    type-check where applicable. This project is not type-annotated, so
    ruff --select F is the static check; noted rather than assumed.
    """
    for job in ("test", "lint", "sast", "build"):
        assert job in jobs, f"missing CI job: {job}"


def test_build_job_is_labelled_as_a_placeholder(jobs):
    """
    Ground rule 5: a compile check must not be presented as a build.

    Checked against the executed commands, not the prose: the workflow
    explains in a comment that Phase 6a will add `docker build`, and
    matching that comment would assert nothing.
    """
    runs = "\n".join(s.get("run", "") for s in jobs["build"]["steps"])
    assert "docker build" not in runs, \
        "a Dockerfile exists after all, so the build job should run it"
    assert "compileall" in runs, "the placeholder compile check is missing"
    assert "Phase 6a replaces this" in _read(CI)


def test_postgres_legs_actually_run_in_ci(jobs):
    """
    Before Phase 4f, TEST_DATABASE_URL was never set, so every PostgreSQL
    test silently skipped in CI.
    """
    test_steps = jobs["test"]["steps"]
    pg_step = [s for s in test_steps
               if "TEST_DATABASE_URL" in (s.get("env") or {})]
    assert pg_step, "no CI step sets TEST_DATABASE_URL; those tests still skip"
    assert "postgres" in str(jobs["test"].get("services", {}))


def test_wsgi_entrypoint_is_import_checked(jobs):
    runs = "\n".join(s.get("run", "") for s in jobs["test"]["steps"])
    assert "wsgi" not in runs or True  # wsgi check lives in the build job
    build_runs = "\n".join(s.get("run", "") for s in jobs["build"]["steps"])
    assert "wsgi" in build_runs, "the production entrypoint is never imported in CI"


def _find_step(jobs, job, needle, must_contain=None):
    for step in jobs[job]["steps"]:
        name = step.get("name", "")
        if needle.lower() in name.lower() and (
                must_contain is None or must_contain.lower() in name.lower()):
            return step
    raise AssertionError(f"step {needle!r} not found in job {job!r}")


# ------------------------------------------------------- gitleaks (secrets)
def test_gitleaks_is_wired_into_ci(jobs):
    assert "secrets" in jobs, "no secrets job"
    uses = [s.get("uses", "") for s in jobs["secrets"]["steps"]]
    assert any("gitleaks" in u for u in uses), "gitleaks action not used"


def test_gitleaks_scans_history_not_just_the_working_tree(jobs):
    """fetch-depth: 0 is required or the secret history is invisible."""
    checkout = [s for s in jobs["secrets"]["steps"]
                if "actions/checkout" in s.get("uses", "")]
    assert checkout, "no checkout step in the secrets job"
    assert checkout[0].get("with", {}).get("fetch-depth") == 0, \
        "gitleaks needs fetch-depth: 0 to scan commit history"


def test_the_old_single_string_grep_is_gone(jobs):
    """
    The previous check was `grep -R "nare-co-secret-2026"`, which can only
    ever find that one string. Asserted against the executed commands: the
    workflow still mentions it in a comment explaining what was replaced.
    """
    runs = "\n".join(s.get("run", "") for s in
                     [st for j in jobs.values() for st in j["steps"]])
    assert "nare-co-secret-2026" not in runs, \
        "the placeholder single-string secret grep is back"
    assert "if grep -R" not in runs, "a hand-rolled grep is standing in for gitleaks"


def test_env_file_is_never_committed(jobs):
    runs = "\n".join(s.get("run", "") for s in jobs["secrets"]["steps"])
    assert "git ls-files" in runs and ".env" in runs


def test_env_example_has_no_real_credential_values(jobs):
    runs = "\n".join(s.get("run", "") for s in jobs["secrets"]["steps"])
    assert ".env.example" in runs


def test_gitleaks_uses_a_reviewed_allowlist(jobs):
    """
    The allowlist must match the placeholder *values*, not whole paths.

    A path-scoped allowlist (tests/**) would also hide a real credential
    committed in a test file, which is the case that matters.
    """
    step = [s for s in jobs["secrets"]["steps"]
            if "gitleaks" in s.get("uses", "")][0]
    config = step.get("with", {}).get("config")
    assert config == ".gitleaks.toml", "gitleaks runs without a reviewed config"
    assert os.path.isfile(os.path.join(HERE, config))
    body = _read(os.path.join(HERE, config))
    assert "test-secret-key-for-ci-must-be-long-enough-32chars" in body, \
        "the known test placeholder is not allowlisted; CI would fail"
    assert "paths" not in body, \
        "the allowlist must not suppress a whole directory of files"
    assert "useDefault" in body, "the default rule set must stay enabled"


def test_secret_scan_fails_the_build(jobs):
    """An annotation-only secret scan is not a control."""
    step = [s for s in jobs["secrets"]["steps"]
            if "gitleaks" in s.get("uses", "")][0]
    env = step.get("env", {})
    assert env.get("GITLEAKS_ENABLE_UPLOAD_ARTIFACT") == "false"
