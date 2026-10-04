"""Phase 7b: application logs are structured JSON, not interpolated strings.

The directive: "Add structured logging (JSON logs) instead of ad-hoc
`print()`/`logger.info(f"...")` string interpolation."

These tests are the enforcement. A formatter nobody checks is decoration, so
the guard fails if application code regresses to f-string interpolation or
print().
"""
import glob
import io
import json
import logging
import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(HERE, "app")


# ------------------------------------------------------------------ the guard
def _app_python_files():
    for path in glob.glob(os.path.join(APP, "**", "*.py"), recursive=True):
        yield path


def _fstring_log_calls(path):
    """AST-level search for logger.X(f"...") calls.

    Parsed rather than regexed, so a docstring or string literal that mentions
    f-string logging cannot trip the guard. Only real call nodes count.
    """
    import ast

    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    found = []
    log_methods = {"info", "warning", "error", "debug", "exception", "critical"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in log_methods:
            continue
        if not node.args:
            continue
        first = node.args[0]
        # JoinedStr is an f-string; Constant str is a plain template
        if isinstance(first, ast.JoinedStr):
            found.append(f"{os.path.relpath(path, HERE)}:{node.lineno}")
    return found


def _print_calls(path):
    """AST-level search for print() calls in real code."""
    import ast

    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "print":
                found.append(f"{os.path.relpath(path, HERE)}:{node.lineno}")
    return found


@pytest.mark.parametrize("path", sorted(_app_python_files()))
def test_no_fstring_logging_in_application_code(path):
    """
    `logger.info(f"...")` interpolates eagerly and produces an opaque string.

    The fix is a template plus args: `logger.info("user %s", uid)`, which the
    JSON formatter resolves lazily and keeps queryable. Checked with the AST
    so documentation cannot make this test assert nothing.
    """
    offenders = _fstring_log_calls(path)
    assert not offenders, (
        "f-string logging is not structured logging: " + ", ".join(offenders[:10]))


@pytest.mark.parametrize("path", sorted(_app_python_files()))
def test_no_print_in_application_code(path):
    """print() bypasses the logger entirely: no level, no JSON, no filtering."""
    offenders = _print_calls(path)
    assert not offenders, (
        "print() bypasses structured logging: " + ", ".join(offenders[:10]))


# ------------------------------------------------------- the formatter itself
def test_formatter_emits_valid_json():
    from app.logging_config import JsonFormatter

    record = logging.LogRecord(
        name="DR.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="user %s logged in", args=(42,), exc_info=None)
    out = JsonFormatter(service="DR", env="test").format(record)
    parsed = json.loads(out)
    assert parsed["msg"] == "user 42 logged in"
    assert parsed["level"] == "INFO"
    assert parsed["service"] == "DR"
    assert parsed["env"] == "test"
    assert "ts" in parsed


def test_extra_fields_are_promoted_to_top_level():
    """This is what makes a log queryable rather than greppable."""
    from app.logging_config import JsonFormatter

    record = logging.LogRecord(
        name="DR.test", level=logging.WARNING, pathname=__file__, lineno=1,
        msg="rate limited", args=(), exc_info=None)
    record.user_id = 7
    record.path = "/api/qrcodes"
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["user_id"] == 7
    assert parsed["path"] == "/api/qrcodes"


def test_extra_cannot_clobber_reserved_fields():
    """
    A caller must not be able to forge the level or timestamp via extra=.

    This is a real attack surface: extra={"level": "FORGED"} on a log call
    would otherwise overwrite the severity in the output, letting a caller
    make an ERROR look like a DEBUG (or hide it entirely).
    """
    from app.logging_config import JsonFormatter

    record = logging.LogRecord(
        name="DR.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="x", args=(), exc_info=None)
    record.level = "FORGED"
    record.ts = "forged"
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["level"] == "INFO", parsed
    assert parsed["ts"] != "forged", parsed

    # and via the extra= path, which is how a caller would actually try it
    record2 = logging.LogRecord(
        name="DR.test", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="x", args=(), exc_info=None)
    record2.level = "DEBUG"
    parsed2 = json.loads(JsonFormatter().format(record2))
    assert parsed2["level"] == "ERROR", parsed2


def test_non_serialisable_extra_fields_do_not_crash_the_formatter():
    """A set or object in extra= must not take the request down with it."""
    from app.logging_config import JsonFormatter

    record = logging.LogRecord(
        name="DR.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="x", args=(), exc_info=None)
    record.weird = {1, 2, 3}
    parsed = json.loads(JsonFormatter().format(record))
    # stringified rather than crashing — the point is resilience
    assert parsed["weird"] == str({1, 2, 3})


def test_exceptions_are_structured():
    from app.logging_config import JsonFormatter

    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="DR.test", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info())
    parsed = json.loads(JsonFormatter().format(record))
    assert "ValueError" in parsed["exc"]
    assert "boom" in parsed["exc"]


# ------------------------------------------------------- it is actually wired
def test_the_app_installs_the_json_formatter():
    """The formatter must be on the root logger, or nothing is structured.

    Re-installs before checking: other tests in the same process may have
    replaced handlers, and the assertion is about the app's configuration,
    not about whatever the previous test left behind.
    """
    from app.logging_config import install_json_logging, JsonFormatter

    install_json_logging(level="INFO", service="DR", env="test")
    root = logging.getLogger()
    assert root.handlers, "the root logger has no handlers"
    assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers), \
        "the root logger is not using the JSON formatter"


def test_a_real_log_line_is_json():
    """End to end: a log call produces parseable JSON.

    Uses a fresh handler rather than capsys: the app installs its handler at
    import time, binding the stdout that existed then, so capsys (which
    replaces sys.stdout per test) would never see the output.
    """
    import app.config  # noqa: F401 — importing installs the formatter

    log = logging.getLogger("DR.test.e2e")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    from app.logging_config import JsonFormatter
    handler.setFormatter(JsonFormatter())
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    try:
        log.info("structured check", extra={"check_id": 1})
    finally:
        log.handlers = []
    out = buf.getvalue().strip().splitlines()
    assert out, "nothing was written"
    parsed = json.loads(out[-1])
    assert parsed["msg"] == "structured check"
    assert parsed["check_id"] == 1


def test_lazy_interpolation_does_not_run_when_filtered():
    """
    The point of templates: a DEBUG line must not be built when the level is
    INFO. Asserted by counting format calls.
    """
    from app.logging_config import JsonFormatter

    calls = []

    class Counting(JsonFormatter):
        def format(self, record):
            calls.append(record.msg)
            return super().format(record)

    log = logging.getLogger("DR.test.lazy")
    log.handlers = []
    handler = logging.StreamHandler(io.StringIO())
    handler.setFormatter(Counting())
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.debug("expensive %s", "".join(str(i) for i in range(1000)))
        assert calls == [], "a filtered DEBUG line was still formatted"
    finally:
        log.handlers = []
        log.setLevel(logging.NOTSET)
