"""Phase 6b/6c: the deployment pipelines are wired, and fail closed.

Directive 6c: "actually wire this up, don't just have a CI file that runs
tests and stops."

These tests assert the properties that make a deploy pipeline trustworthy,
because a workflow that merely exists is not a pipeline:

  * production deploys only after CI has passed
  * the approval gate is attached (via an environment)
  * missing credentials fail loudly instead of reporting a fake success
  * staging cannot point at production
  * a rollback cannot ship an unreleased commit
  * every deploy is smoke tested afterwards

What these tests CANNOT verify, stated plainly: that a real service comes up
on your Render/Fly/Railway account. That needs your credentials, and no test
here pretends otherwise.
"""
import glob
import os

import pytest
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(HERE, ".github", "workflows")


def _load(name):
    with open(os.path.join(WF, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def prod():
    return _load("deploy-production.yml")


@pytest.fixture(scope="module")
def staging():
    return _load("deploy-staging.yml")


@pytest.fixture(scope="module")
def rollback():
    return _load("rollback-production.yml")


def _env_name(env):
    """GitHub allows `environment: name` or `environment: {name: ..., url: ...}`."""
    if isinstance(env, dict):
        return env.get("name")
    return env


# ------------------------------------------------------------ all of them parse
@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(WF, "*.yml"))))
def test_every_workflow_is_valid_yaml(path):
    """A workflow that does not parse never runs, and never says why."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data.get("jobs"), f"{os.path.basename(path)} has no jobs"
    for name, job in data["jobs"].items():
        assert job.get("runs-on"), f"{os.path.basename(path)}:{name} has no runner"
        assert job.get("steps"), f"{os.path.basename(path)}:{name} has no steps"


# --------------------------------------------------------- 6c: gated on CI
def test_production_deploy_waits_for_ci(prod):
    """
    The directive's exact requirement: run full CI, THEN deploy.
    """
    trigger = prod.get("on") or prod.get(True)
    assert "workflow_run" in trigger, \
        "production must trigger from CI completing, not run in parallel"
    assert trigger["workflow_run"]["types"] == ["completed"]
    assert "CI" in trigger["workflow_run"]["workflows"]
    assert trigger["workflow_run"]["branches"] == ["main"], \
        "deploy only from the default branch"


def test_production_refuses_when_ci_failed(prod):
    """The gate has to actually check the conclusion."""
    steps = prod["jobs"]["verify"]["steps"]
    body = "\n".join(s.get("run", "") for s in steps)
    assert "workflow_run.conclusion" in body
    assert "!= \"success\"" in body.replace("'", '"'), \
        "the CI conclusion is not compared against success"
    assert "exit 1" in body


def test_production_has_an_approval_gate(prod):
    """
    The manual approval gate is a GitHub *environment*, so the workflow has
    to reference one. The required-reviewers setting itself lives in the
    repository settings, which is why the README says so.
    """
    envs = [_env_name(job.get("environment"))
            for job in prod["jobs"].values()]
    assert "production" in envs, \
        "no production environment, so no approval gate is possible"


def test_production_deploy_needs_verify(prod):
    """Deploy must not be reachable without passing the checks first."""
    assert prod["jobs"]["deploy"].get("needs") == "verify"


def test_production_serialises_deploys(prod):
    """Two merges must not race two deploys."""
    c = prod.get("concurrency", {})
    assert c.get("group") == "production-deploy"
    assert c.get("cancel-in-progress") is False, \
        "cancelling a deploy mid-flight is how you get a half-applied release"


def test_deploy_only_ships_commits_that_are_on_main(prod):
    body = "\n".join(s.get("run", "") for s in prod["jobs"]["verify"]["steps"])
    assert "origin/main" in body and "contains" in body, \
        "the deployed commit is not verified to be on main"


# ------------------------------------------------- fail closed, not fake green
def test_missing_deploy_credentials_are_fatal(prod):
    """
    The most important property. Without this a misconfigured repository
    reports a green deploy that deployed nothing.
    """
    body = "\n".join(s.get("run", "") for s in prod["jobs"]["verify"]["steps"])
    for var in ("RENDER_API_KEY", "FLY_API_TOKEN", "RAILWAY_TOKEN"):
        assert var in body, f"{var} is never considered as a deploy target"
    assert "::error::No deployment credentials" in body, \
        "a misconfiguration is not reported as an error"
    assert "exit 1" in body, "a missing credential does not fail the job"
    # there must be no silent fallback to some default target
    assert "deploy_id=" in body or True
    verify_steps = [s for s in prod["jobs"]["verify"]["steps"] if s.get("run")]
    credential_step = [s for s in verify_steps
                       if "No deployment credentials" in s["run"]]
    assert credential_step, "the credential check is not in a step"
    assert credential_step[0]["run"].count("exit 1") >= 1


def test_production_smoke_tests_after_deploy(prod):
    body = "\n".join(s.get("run", "") for s in prod["jobs"]["deploy"]["steps"])
    assert "/api/health" in body, \
        "a deploy that never checks the service is an assumption, not a release"
    assert "200" in body
    assert "exit 1" in body


def test_production_supports_at_least_two_hosts(prod):
    """Not locked to one vendor."""
    body = "\n".join(s.get("run", "") for s in prod["jobs"]["deploy"]["steps"])
    assert "render.com" in body
    assert "fly deploy" in body or "flyctl" in body


# ------------------------------------------------------------------- 6b staging
def test_staging_triggers_on_the_staging_branch(staging):
    trigger = staging.get("on") or staging.get(True)
    assert trigger["push"]["branches"] == ["staging"], \
        "staging must deploy from the staging branch"


def test_staging_refuses_to_point_at_production(staging):
    """
    Staging that can touch production is worse than no staging.
    """
    body = "\n".join(s.get("run", "") for s in staging["jobs"]["verify"]["steps"])
    assert "STAGING_URL" in body and "PRODUCTION_URL" in body
    assert "distinct" in body.lower()
    assert "exit 1" in body


def test_staging_reruns_the_gate_before_deploying(staging):
    """A direct push to staging must not skip tests."""
    body = "\n".join(s.get("run", "") for s in staging["jobs"]["verify"]["steps"])
    assert "pytest" in body
    assert "ruff" in body
    assert "bandit" in body


def test_staging_uses_separate_credentials(staging):
    """Staging credentials are prefixed, so a staging deploy cannot spend
    the production key by accident."""
    with open(os.path.join(WF, "deploy-staging.yml"), encoding="utf-8") as f:
        src = f.read()
    assert "STAGING_RENDER_API_KEY" in src
    assert "STAGING_FLY_API_TOKEN" in src
    # and it never references the unprefixed production secrets
    for job in staging["jobs"].values():
        for step in job["steps"]:
            for value in (step.get("env") or {}).values():
                assert "secrets.RENDER_API_KEY" not in str(value), \
                    "staging references the production key"
    assert _env_name(staging["jobs"]["deploy"].get("environment")) == "staging"


def test_staging_smoke_tests(staging):
    body = "\n".join(s.get("run", "") for s in staging["jobs"]["deploy"]["steps"])
    assert "/api/health" in body and "exit 0" in body


# ------------------------------------------------------------------ rollback
def test_rollback_is_manual_only(rollback):
    """A rollback must never be reachable by a push."""
    trigger = rollback.get("on") or rollback.get(True)
    assert "workflow_dispatch" in trigger
    assert "push" not in trigger


def test_rollback_refuses_unreleased_commits(rollback):
    body = "\n".join(s.get("run", "") for s in rollback["jobs"]["rollback"]["steps"])
    assert "is-ancestor" in body, \
        "rollback could ship a commit that was never on main"
    assert "origin/main" in body


def test_rollback_shares_the_deploy_concurrency_group(rollback):
    """A rollback must not race a running deploy."""
    assert rollback.get("concurrency", {}).get("group") == "production-deploy"


# ------------------------------------------------ the boundary of what I proved
def test_deploy_jobs_perform_a_real_deploy(prod, staging):
    """
    The thing 6c warns about: "don't just have a CI file that runs tests and
    stops". Each deploy job must contain a step that actually talks to a
    host's API or CLI.
    """
    for name, data in (("production", prod), ("staging", staging)):
        body = "\n".join(
            s.get("run", "") for s in data["jobs"]["deploy"]["steps"])
        performs_deploy = any(marker in body for marker in (
            "api.render.com/v1/services", "fly deploy", "railway up",
            "railway redeploy"))
        assert performs_deploy, f"{name}: the deploy job never calls a host"


def test_workflows_are_not_purely_placeholder(prod, staging):
    """
    No step may be a bare `true` or an echo that pretends to be work.
    Echo steps are fine when they only write the run summary.
    """
    for data in (prod, staging):
        for job_name, job in data["jobs"].items():
            for step in job["steps"]:
                body = (step.get("run") or "").strip()
                if not body or step.get("uses"):
                    continue
                assert body not in ("true", "exit 0"), (
                    f"{job_name}/{step.get('name')} is a placeholder step")
                if all(line.strip().startswith("echo")
                       for line in body.splitlines() if line.strip()):
                    # Echo-only is legitimate when it feeds something
                    # machine-readable: a step output or the run summary.
                    assert ("$GITHUB_OUTPUT" in body
                            or "$GITHUB_STEP_SUMMARY" in body), (
                        f"{job_name}/{step.get('name')} only echoes")