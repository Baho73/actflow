# FILE: backend/app/models.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: ORM-модели: LegalEntity, Project, Payment, Act. Только хранение.
#   SCOPE: Схема таблиц, связи, ключ идемпотентности. Никакой бизнес-логики.
#   LAYER: DATA
#   DEPENDS: M-DB
#   LINKS: M-MODELS, V-M-MODELS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   LegalEntity - клиент/юрлицо (ИНН unique); создаётся ТОЛЬКО из оплат клиентов
#   Project - проект (клиент + договор/услуга); auto_created — черновик автопривязки
#   Payment - оплата; dedup_key (unique) делает повторный импорт идемпотентным
#   Act - закрывающий документ; СТАТУС НЕ ХРАНИТСЯ (вычисляется доменом)
#   make_dedup_key - стабильный ключ по нормализованным полям
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-MODELS contract]
# END_CHANGE_SUMMARY
#
# Статус акта в БД отсутствует намеренно: он производная от флагов и возраста оплаты.
# Хранить его — держать вторую версию правды и ловить рассинхрон.

import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# START_CONTRACT: make_dedup_key
#   PURPOSE: Стабильный ключ операции — повторная загрузка выписки не двоит оплаты.
#   INPUTS: { payment_date, amount, doc_number, counterparty_inn, direction }
#   OUTPUTS: { str (sha256) }
#   SIDE_EFFECTS: none
#   LINKS: ключ считается по НОРМАЛИЗОВАННЫМ полям, иначе «33000.0» и «33000.00» дадут дубль
# END_CONTRACT: make_dedup_key
def make_dedup_key(
    payment_date: date, amount: Decimal, doc_number: str, counterparty_inn: str | None, direction: str
) -> str:
    raw = f"{payment_date:%Y-%m-%d}|{amount:.2f}|{(doc_number or '').strip()}|{counterparty_inn or ''}|{direction}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class LegalEntity(Base):
    """Клиент. Создаётся ТОЛЬКО из операций-оплат: иначе в справочник попадут
    налоговая, обслуживающий банк и получатели зарплаты."""

    __tablename__ = "legal_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    inn: Mapped[str] = mapped_column(String(12), unique=True)
    ogrn: Mapped[str | None] = mapped_column(String(15), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    projects: Mapped[list["Project"]] = relationship(back_populates="client")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    client_id: Mapped[int] = mapped_column(ForeignKey("legal_entities.id", ondelete="CASCADE"))
    contract_number: Mapped[str | None] = mapped_column(String(50), default=None)
    service_stage: Mapped[str | None] = mapped_column(String(100), default=None)
    # черновик автопривязки: помечен, виден менеджеру и переименовывается им
    auto_created: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped[LegalEntity] = relationship(back_populates="projects")
    payments: Mapped[list["Payment"]] = relationship(back_populates="project")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_date", "payment_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("legal_entities.id", ondelete="CASCADE"))
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), default=None
    )
    # способ привязки хранится и показывается: пользователь всегда знает, ПОЧЕМУ оплата тут
    binding_method: Mapped[str] = mapped_column(String(20), default="unbound")
    conflict_reason: Mapped[str | None] = mapped_column(String(300), default=None)
    stage_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)

    payment_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    purpose_text: Mapped[str] = mapped_column(Text)
    doc_number: Mapped[str] = mapped_column(String(30), default="")
    invoice_numbers: Mapped[list] = mapped_column(JSON, default=list)
    contract_number: Mapped[str | None] = mapped_column(String(50), default=None)
    service_stages: Mapped[list] = mapped_column(JSON, default=list)  # услуг может быть несколько

    dedup_key: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    client: Mapped[LegalEntity] = relationship()
    project: Mapped[Project | None] = relationship(back_populates="payments")
    act: Mapped["Act"] = relationship(back_populates="payment", cascade="all, delete-orphan", uselist=False)


class Act(Base):
    """Закрывающий документ. Статуса тут нет: он вычисляется доменом из флагов и возраста оплаты."""

    __tablename__ = "acts"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), unique=True)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[date | None] = mapped_column(Date, default=None)
    is_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_at: Mapped[date | None] = mapped_column(Date, default=None)
    manager_comment: Mapped[str] = mapped_column(Text, default="")

    payment: Mapped[Payment] = relationship(back_populates="act")
