# FILE: backend/app/main.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Сборка FastAPI-приложения: роутеры под /api, схема БД при старте с ретраями.
#   SCOPE: Точка входа.
#   LAYER: API
#   DEPENDS: M-API, M-DB, M-MODELS
#   LINKS: M-API
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   app - ASGI-приложение
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation]
# END_CHANGE_SUMMARY

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.exc import OperationalError

from app import models  # noqa: F401 — регистрация таблиц в Base.metadata
from app.db import Base, engine
from app.routers import dashboard

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_RETRIES = 30


@asynccontextmanager
async def lifespan(app: FastAPI):
    # START_BLOCK_DB_INIT_RETRY
    for attempt in range(1, DB_RETRIES + 1):
        try:
            Base.metadata.create_all(engine)
            logger.info("[Main][lifespan][BLOCK_DB_INIT_RETRY] schema ready")
            break
        except OperationalError:
            if attempt == DB_RETRIES:
                raise
            logger.info("[Main][lifespan][BLOCK_DB_INIT_RETRY] db not ready, retry %s", attempt)
            time.sleep(1)
    # END_BLOCK_DB_INIT_RETRY
    yield


app = FastAPI(title="ActFlow API", lifespan=lifespan)
app.include_router(dashboard.router)
