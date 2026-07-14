# FILE: backend/app/db.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Подключение к БД, фабрика сессий, declarative base.
#   SCOPE: Только инфраструктура доступа к данным.
#   LAYER: DATA
#   DEPENDS: none
#   LINKS: M-DB, V-M-DB
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   engine / SessionLocal / Base - SQLAlchemy 2.0
#   get_session - FastAPI dependency
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-DB contract]
# END_CHANGE_SUMMARY

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://actflow:actflow@localhost:5432/actflow"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
