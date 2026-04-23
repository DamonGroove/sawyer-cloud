"""pytest fixtures.

Uses an in-memory-ish SQLite database for tests so the suite runs in any
dev env without Postgres. Postgres-only column types (JSONB, ARRAY,
UUID) are mapped to generic SQLAlchemy fallbacks by SQLAlchemy's
`JSON`/`String`/etc. — we do this via a conditional compile in
tests/_sqlite_compat.py loaded below.

For production-shape coverage, pytest can be run against the compose
postgres with DATABASE_URL overridden; the fixtures honor whatever
DATABASE_URL resolves to.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Force SQLite + in-memory BEFORE importing app.config — which caches settings.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "dev")
os.environ.setdefault("SESSION_SECRET", "test-secret-key-not-for-prod")

from app.db import Base  # noqa: E402
from app import models  # noqa: F401,E402
from tests import _sqlite_compat  # noqa: F401,E402


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    # StaticPool + a single shared connection is the canonical way to keep
    # an in-memory sqlite visible across sessions in one test.
    engine = create_async_engine(
        os.environ["DATABASE_URL"],
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[AsyncClient]:
    # Use FastAPI's dependency_overrides to swap get_session for one that
    # reads from our test-local engine. Also swap the db module's
    # _session_factory so routes that reach for it directly see ours.
    from app import db as db_module
    from app.main import create_app
    from app.db import get_session

    db_module._session_factory = session_factory

    async def _override_get_session():
        async with session_factory() as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_session] = _override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_flavor(session_factory) -> str:
    slug = f"test-flavor-{uuid4().hex[:8]}"
    async with session_factory() as s:
        s.add(models.Flavor(slug=slug, description="test flavor"))
        await s.commit()
    return slug


@pytest.fixture
def admin_token() -> str:
    from app.auth.tokens import create_session_jwt

    return create_session_jwt(
        subject=str(uuid4()),
        email="admin@test.invalid",
        roles=["admin"],
        customer_ids=[],
    )


@pytest.fixture
def operator_token() -> str:
    from app.auth.tokens import create_session_jwt

    return create_session_jwt(
        subject=str(uuid4()),
        email="operator@test.invalid",
        roles=["operator"],
        customer_ids=[],
    )
