# FILE: backend/tests/conftest.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Фикстуры API-тестов: приложение на SQLite in-memory через ту же схему.
#   SCOPE: engine + override сессии + TestClient.
#   LAYER: DATA
#   DEPENDS: M-DB, M-MODELS, M-API
#   LINKS: V-M-DB
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   client - TestClient с изолированной БД
#   STATEMENT - байты эталонной выписки
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation]
# END_CHANGE_SUMMARY

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app

STATEMENT = (Path(__file__).resolve().parents[2] / "bank_statement.pdf").read_bytes()


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override
    # без контекст-менеджера: lifespan ломился бы в PostgreSQL, а схема уже создана
    yield TestClient(app)
    app.dependency_overrides.clear()
