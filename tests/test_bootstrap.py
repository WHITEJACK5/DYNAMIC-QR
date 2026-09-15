"""Phase 1c: cold-start bootstrap tests.

Covers the pre-`logger` reference bug: `logger.warning(...)` was called in the
SECRET_KEY bootstrap block before `logger = logging.getLogger(...)` was
defined, so a fresh clone with no SECRET_KEY set crashed with NameError.
"""
import os
import re
import subprocess
import sys


def test_logger_defined_before_first_use():
    here = os.path.dirname(os.path.dirname(__file__))
    src = open(os.path.join(here, "app.py"), encoding="utf-8").read()
    lines = src.splitlines()
    def_no = next(
        i for i, l in enumerate(lines) if "logger = logging.getLogger" in l
    )
    uses = [
        i for i, l in enumerate(lines)
        if re.search(r"(^|[^a-zA-Z_.])logger\.(warning|exception|debug|info|error)", l)
    ]
    assert uses, "expected at least one logger.* usage in app.py"
    assert def_no < min(uses), (
        f"logger used at line {min(uses)+1} before definition at line {def_no+1}"
    )


def test_cold_start_no_secret_key(tmp_path):
    """Fresh-clone path: no SECRET_KEY/JWT_SECRET in env must import cleanly."""
    here = os.path.dirname(os.path.dirname(__file__))
    env_path = os.path.join(here, ".env")
    backup = None
    if os.path.exists(env_path):
        backup = env_path + ".testbak"
        with open(env_path, "rb") as f:
            data = f.read()
        with open(backup, "wb") as f:
            f.write(data)
    try:
        env = {k: v for k, v in os.environ.items()
               if k not in ("SECRET_KEY", "JWT_SECRET")}
        # Keep PATH/system vars; ensure python can find deps
        proc = subprocess.run(
            [sys.executable, "-c",
             "import app; print('import ok'); print(len(app.SECRET_KEY))"],
            cwd=here,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "NameError" not in (proc.stderr or ""), proc.stderr[-2000:]
        assert proc.returncode == 0, (
            f"cold-start import failed rc={proc.returncode}\n"
            f"STDOUT:\n{(proc.stdout or '')[-2000:]}\n"
            f"STDERR:\n{(proc.stderr or '')[-2000:]}"
        )
        assert "import ok" in (proc.stdout or "")
    finally:
        if backup and os.path.exists(backup):
            with open(backup, "rb") as f:
                data = f.read()
            with open(env_path, "wb") as f:
                f.write(data)
            os.remove(backup)
        elif backup is None and os.path.exists(env_path):
            # subprocess may have created .env; leave it (expected fresh-clone
            # behaviour) but ensure it does not contain a real secret leak
            # beyond the generated key — nothing to do.
            pass
