"""Phase 4g: secrets come from the platform's secret store, not a file.

Directive: "Move secrets out of .env files for any real deployment — use
the hosting provider's secrets manager (Render/Railway secrets, AWS Secrets
Manager, etc.) in staging/production; .env remains local-dev-only."

The code half of that is the part that was actually broken. Previously a
deploy with no SECRET_KEY would generate one and write it into the
container filesystem: the key died with the container, invalidating every
session on restart, and the deploy still looked healthy. These tests run
the real import in a subprocess, because the failure mode is at import
time and an in-process assertion would not see it.
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
    "PYTHONPATH": HERE,
    # deliberately absent: SECRET_KEY
}


def _import_config(**env):
    """Import app.config in a clean subprocess. Returns the CompletedProcess."""
    e = dict(BASE_ENV)
    e.update(env)
    return subprocess.run(
        [sys.executable, "-c", "import app.config as c; print('IS_PRODUCTION', c.IS_PRODUCTION)"],
        capture_output=True, text=True, cwd=HERE, env=e, timeout=120,
    )


# ---------------------------------------------------- production refuses to start
def test_production_without_a_secret_key_refuses_to_start():
    r = _import_config(APP_ENV="production")
    assert r.returncode != 0, "production started with no SECRET_KEY"
    assert "SECRET_KEY" in (r.stdout + r.stderr)


def test_the_error_names_the_supported_secret_stores():
    """The operator has to be told where to put the secret."""
    r = _import_config(APP_ENV="production")
    out = r.stdout + r.stderr
    for provider in ("Render", "Railway", "Fly.io", "AWS"):
        assert provider in out, f"{provider} is not mentioned in the failure message"


def test_the_error_explains_why_it_refuses():
    """Not just 'missing variable' — the reason matters at 3am."""
    r = _import_config(APP_ENV="production")
    out = r.stdout + r.stderr
    assert "container filesystem" in out
    assert "restart" in out


@pytest.mark.parametrize("marker", [
    "RENDER=1",
    "RAILWAY_ENVIRONMENT=production",
    "FLY_APP_NAME=nare",
    "DYNO=web.1",
    "KUBERNETES_SERVICE_HOST=10.0.0.1",
])
def test_platform_markers_are_detected_as_production(marker):
    k, v = marker.split("=", 1)
    r = _import_config(**{k: v})
    assert r.returncode != 0, f"{marker} was not treated as production"
    assert "IS_PRODUCTION" not in r.stdout


def test_short_secret_key_is_fatal_in_production_but_not_in_dev():
    bad = _import_config(APP_ENV="production", SECRET_KEY="short")
    assert bad.returncode != 0
    assert "32" in (bad.stdout + bad.stderr)
    # the same value is only a warning locally
    ok = _import_config(APP_ENV="development", SECRET_KEY="short")
    assert ok.returncode == 0, "a short key should not block local development"


def test_production_starts_cleanly_when_the_secret_store_supplies_a_key():
    r = _import_config(APP_ENV="production",
                       SECRET_KEY="a" * 64, BASE_URL="https://app.example.com")
    assert r.returncode == 0, r.stderr
    assert "IS_PRODUCTION True" in r.stdout


# ------------------------------------------------------- development is unchanged
def test_development_still_auto_generates_and_persists(tmp_path):
    """
    The directive says ".env remains local-dev-only" — not that local dev
    should get harder. A fresh clone with no SECRET_KEY must still work.
    """
    e = dict(BASE_ENV)
    e["SECRET_KEY"] = ""
    env_file = os.path.join(HERE, ".env")
    existed = os.path.exists(env_file)
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import app.config as c; print('KEYLEN', len(c.SECRET_KEY))"],
            capture_output=True, text=True, cwd=HERE, env=e, timeout=120,
        )
        assert r.returncode == 0, r.stderr
        assert "KEYLEN 64" in r.stdout
        assert os.path.exists(env_file), "no .env written for a fresh local dev run"
        with open(env_file, encoding="utf-8") as f:
            assert "SECRET_KEY=" in f.read()
    finally:
        if not existed and os.path.exists(env_file):
            os.remove(env_file)


# ------------------------------------------------------------ nothing committed
def test_env_file_is_git_ignored():
    import subprocess as sp
    r = sp.run(["git", "check-ignore", ".env"], cwd=HERE,
               capture_output=True, text=True)
    assert r.returncode == 0, ".env is not git-ignored"


def test_env_file_is_not_tracked():
    import subprocess as sp
    r = sp.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=HERE,
               capture_output=True, text=True)
    assert r.returncode != 0, ".env is tracked in git"


def test_env_example_documents_the_secret_store():
    """The example file is where a deployer looks first."""
    with open(os.path.join(HERE, ".env.example"), encoding="utf-8") as f:
        body = f.read()
    assert "APP_ENV" in body
    assert "secret" in body.lower()
