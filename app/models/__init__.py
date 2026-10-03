"""Models layer: SQLAlchemy ORM entities (Phase 3a) for NARE & CO.

The directive lists `app/models/` as a required layer, so this is a package.
Declarations live in `entities`; everything is re-exported here so the
existing `from app.models import Base, User, QRCode, Scan, Folder, Template`
call sites (repositories, migrations/env.py, tests) are unchanged.

`__all__` is explicit so a typo in an import fails at once instead of
resolving to nothing.
"""
from app.models.entities import Base, Folder, QRCode, Review, Scan, Template, User

__all__ = ["Base", "User", "Folder", "QRCode", "Scan", "Review", "Template"]
