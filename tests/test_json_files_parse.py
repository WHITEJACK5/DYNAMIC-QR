"""Pre-merge check: every .json file in the repository must parse.

This exists because a previous commit shipped a lighthouserc.json containing
// comments, which is not valid JSON. lhci autorun failed at runtime with a
parse error, and no test caught it because the file was never loaded.

The test walks the repository (excluding .git and node_modules) and asserts
that every file ending in .json is valid JSON. It also asserts that the
Lighthouse config, if present, is discoverable and parseable.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv"}


def _all_json_files():
    for dirpath, dirnames, filenames in os.walk(HERE):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".json"):
                yield os.path.join(dirpath, fn)


def test_there_is_at_least_one_json_file():
    """Guard against the walker silently finding nothing."""
    files = list(_all_json_files())
    assert files, "no .json files found; the walker is broken"


@pytest.mark.parametrize("path", sorted(_all_json_files()), ids=lambda p: os.path.relpath(p, HERE))
def test_json_file_parses(path):
    with open(path, encoding="utf-8") as f:
        try:
            json.load(f)
        except json.JSONDecodeError as e:
            pytest.fail(f"{os.path.relpath(path, HERE)} is not valid JSON: {e}")


def test_lighthouse_config_is_valid_json():
    """The Lighthouse CI config must be parseable by lhci autorun."""
    candidates = [
        os.path.join(HERE, "frontend", "lighthouserc.json"),
        os.path.join(HERE, "lighthouserc.json"),
    ]
    path = next((p for p in candidates if os.path.isfile(p)), None)
    if path is None:
        pytest.skip("no lighthouserc.json found")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    assert "ci" in cfg, "lighthouserc.json must contain a 'ci' key"
