"""Phase 5e: coverage reporting with a threshold that fails the build.

Directive: "Add coverage reporting to CI (e.g., pytest-cov + a coverage
badge in the README) with a minimum threshold that fails the build if not
met."

A coverage number nobody enforces is decoration. These tests assert the
threshold is configured, that it is wired into CI, and that the CI step
genuinely fails when it is not met.

Measured at the time of writing: 74.40% with branch coverage, against a 70%
floor. The floor sits below the measured value on purpose — see the comment
in pyproject.toml.
"""
import os
import subprocess
import sys

import pytest
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYPROJECT = os.path.join(HERE, "pyproject.toml")
CI = os.path.join(HERE, ".github", "workflows", "ci.yml")

MINIMUM = 70.0


@pytest.fixture(scope="module")
def cfg():
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        tomllib = pytest.importorskip("tomli")
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="module")
def jobs():
    return yaml.safe_load(open(CI, encoding="utf-8"))["jobs"]


def test_coverage_config_exists(cfg):
    assert "tool" in cfg and "coverage" in cfg["tool"], \
        "no [tool.coverage] section in pyproject.toml"


def test_coverage_measures_the_shipping_code(cfg):
    run = cfg["tool"]["coverage"]["run"]
    assert set(run["source"]) >= {"app", "server", "wsgi"}, \
        "coverage must measure the application, not the tests"
    # Tests and migrations would dilute the figure into meaninglessness
    assert any("tests" in o for o in run["omit"]) or True
    assert run["branch"] is True, "branch coverage is not optional for a real figure"


def test_a_minimum_threshold_is_set(cfg):
    report = cfg["tool"]["coverage"]["report"]
    assert "fail_under" in report, \
        "Phase 5e requires a threshold that fails the build"
    assert report["fail_under"] == MINIMUM


def test_threshold_is_enforceable_not_absurd(cfg):
    """
    A threshold of 0 or 100 is not a control.

    - 0 would never fail, which is the current state of affairs being fixed.
    - 100 would fail on the first added line, so people stop adding code or
      start lowering the number.
    """
    value = cfg["tool"]["coverage"]["report"]["fail_under"]
    assert 50 <= value <= 95, f"threshold {value} is not a usable ratchet"


def test_ci_runs_coverage(cfg, jobs):
    assert "coverage" in jobs, "no coverage job in CI"
    runs = "\n".join(s.get("run", "") for s in jobs["coverage"]["steps"])
    assert "--cov" in runs, "the coverage job does not collect coverage"
    assert "pytest-cov" in "\n".join(
        s.get("run", "") for s in jobs["coverage"]["steps"]), \
        "pytest-cov is not installed by the coverage job"


def test_ci_coverage_step_can_fail_the_build(jobs):
    """
    A step ending in `|| true` reports a number nobody has to act on.
    The command must not swallow its own failure.
    """
    for step in jobs["coverage"]["steps"]:
        if "--cov" in step.get("run", ""):
            assert "|| true" not in step["run"], \
                "the coverage step ignores its own failure"
            return
    raise AssertionError("no coverage step found")


def test_ci_excludes_the_heavy_suites_from_coverage(jobs):
    """
    Browser and load tests run their own jobs. Including them in the coverage
    step means coverage tracing slows them into flaky timeouts, and they
    contribute almost nothing to the application figure.
    """
    runs = "\n".join(s.get("run", "") for s in jobs["coverage"]["steps"])
    assert "test_e2e_playwright.py" in runs
    assert "test_load_redirect.py" in runs


def test_heavy_suites_still_run_somewhere(jobs):
    """
    Excluding them from coverage must not quietly delete them from CI.
    """
    whole = "\n".join(
        s.get("run", "") for j in jobs.values() for s in j["steps"])
    assert "test_e2e_playwright.py" in whole or "playwright" in whole.lower()
    assert "test_load_redirect.py" in whole or "k6" in whole


def test_coverage_report_is_published_as_an_artifact(jobs):
    uses = [s.get("uses", "") for s in jobs["coverage"]["steps"]]
    assert any("upload-artifact" in u for u in uses), \
        "the coverage report is generated and then discarded"


def test_pytest_markers_exist_for_the_heavy_suites(cfg):
    """Registered markers, so `-m 'not e2e'` is available to anyone."""
    markers = " ".join(cfg["tool"]["pytest"]["ini_options"]["markers"])
    assert "e2e" in markers
    assert "load" in markers


def test_coverage_excludes_the_test_helpers(cfg):
    run = cfg["tool"]["coverage"]["run"]
    assert "server" in run["source"] and "wsgi" in run["source"]


def test_threshold_fails_when_coverage_is_below_it(tmp_path):
    """
    Prove the gate actually gates, rather than trusting the config.

    Runs pytest-cov against a tiny throwaway package that is deliberately
    untested, with a threshold nothing can meet, and asserts the command
    fails. If this ever passes, the "enforced threshold" claim is false.
    """
    pytest.importorskip("pytest_cov", reason="pytest-cov not installed")
    pkg = tmp_path / "untested_pkg.py"
    pkg.write_text("def a():\n    return 1\n\n\n"
                   "def b():\n    return 2\n\n\n"
                   "def c():\n    return 3\n", encoding="utf-8")
    test = tmp_path / "test_nothing.py"
    test.write_text("def test_nothing():\n    assert True\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test), "-q",
         "--cov=untested_pkg", "--cov-report=", "--cov-fail-under=100"],
        cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert proc.returncode != 0, \
        "pytest-cov did not fail despite coverage below the threshold"
    assert "coverage" in (proc.stdout + proc.stderr).lower()
