"""Core package — Phase 2 precursor to app/ layout.

Why `core/` and not `app/` yet: `app.py` (top-level module) and an `app/`
package cannot coexist (Python import collision breaks `import app` in
tests/CI/entrypoint). Phase 2b will rename the Flask entrypoint
(`app.py` -> `wsgi.py` + `app/__init__.py`) and move `core/*` -> `app/*`.
Until then, pure helpers live here with zero Flask/DB imports.
"""
