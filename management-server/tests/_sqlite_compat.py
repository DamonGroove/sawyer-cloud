"""SQLite compatibility shim for test DB.

Maps postgres-specific JSONB onto SQLite's JSON type at DDL-compile time
so SQLAlchemy can run create_all against SQLite. The ARRAY problem is
gone now that models use JSON instead of ARRAY(String) — see
management-server/README.md for the tradeoff note.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"
