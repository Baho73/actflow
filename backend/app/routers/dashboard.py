# FILE: backend/app/routers/dashboard.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: HTTP: импорт выписки, оплаты с фильтрами, отметки актов, привязка, сводка, экспорт.
#   SCOPE: Транспорт. Все бизнес-решения принимает домен — здесь только выборка и вызов.
#   LAYER: API
#   DEPENDS: M-PARSER, M-ACTSTATUS, M-SUMMARY, M-MODELS, M-DB, import_service
#   LINKS: M-API, V-M-API
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   router - APIRouter /api
#   PaymentFilters - общий набор фильтров (оплаты, сводка и экспорт видят одно и то же)
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-API contract]
# END_CHANGE_SUMMARY
#
# «Сегодня» задаётся здесь (Москва) и передаётся в домен: домен сам время не выясняет,
# иначе тесты недетерминированы, а часовой пояс сервера двигает границу просрочки.

import csv
import io
import logging
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.domain.act_status import DEFAULT_SLA_DAYS, compute_act_status
from app.domain.parser import StatementFormatError
from app.domain.summary import PaymentView, summarize, summarize_by_project
from app.models import Act, LegalEntity, Payment, Project
from app.schemas import (
    ActPatch,
    BulkActIn,
    ClientOut,
    DashboardOut,
    ImportReportOut,
    PaymentOut,
    PaymentPage,
    ProjectOut,
    ProjectPatch,
    ProjectRename,
)
from app.services.import_service import import_statement, rebind_unbound

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dashboard"])

MOSCOW = ZoneInfo("Europe/Moscow")
MAX_UPLOAD = 10 * 1024 * 1024


def today_msk(as_of: date | None = Query(None, description="Демо/тесты: считать статусы на эту дату")) -> date:
    return as_of or datetime.now(MOSCOW).date()


class PaymentFilters:
    """Один набор фильтров на список, сводку и экспорт — иначе цифры разойдутся с таблицей."""

    def __init__(
        self,
        project_id: int | None = None,
        client_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        service_stage: str | None = None,
        act_status: str | None = None,
        unbound_only: bool = False,
        search: str | None = None,
    ):
        self.project_id = project_id
        self.client_id = client_id
        self.date_from = date_from
        self.date_to = date_to
        self.service_stage = service_stage
        self.act_status = act_status
        self.unbound_only = unbound_only
        self.search = search


def _query(session: Session, f: PaymentFilters):
    q = (
        select(Payment)
        .options(selectinload(Payment.act), selectinload(Payment.client), selectinload(Payment.project))
    )
    if f.project_id:
        q = q.where(Payment.project_id == f.project_id)
    if f.client_id:
        q = q.where(Payment.client_id == f.client_id)
    if f.date_from:
        q = q.where(Payment.payment_date >= f.date_from)
    if f.date_to:
        q = q.where(Payment.payment_date <= f.date_to)
    if f.unbound_only:
        q = q.where(Payment.project_id.is_(None))
    if f.search:
        like = f"%{f.search}%"
        q = q.join(LegalEntity, LegalEntity.id == Payment.client_id).where(
            or_(Payment.purpose_text.ilike(like), LegalEntity.name.ilike(like))
        )
    return q


def _to_out(p: Payment, today: date) -> PaymentOut:
    act = p.act or Act()
    status = compute_act_status(
        is_sent=act.is_sent,
        is_signed=act.is_signed,
        payment_date=p.payment_date,
        today=today,
    )
    return PaymentOut(
        id=p.id,
        payment_date=p.payment_date,
        amount=p.amount,
        client_id=p.client_id,
        client_name=p.client.name,
        client_inn=p.client.inn,
        project_id=p.project_id,
        project_name=p.project.name if p.project else None,
        binding_method=p.binding_method,
        conflict_reason=p.conflict_reason,
        stage_mismatch=p.stage_mismatch,
        service_stages=p.service_stages or [],
        invoice_numbers=p.invoice_numbers or [],
        contract_number=p.contract_number,
        doc_number=p.doc_number,
        purpose_text=p.purpose_text,
        is_sent=act.is_sent,
        sent_at=act.sent_at,
        is_signed=act.is_signed,
        signed_at=act.signed_at,
        manager_comment=act.manager_comment,
        act_status=str(status),
    )


def _filtered(session: Session, f: PaymentFilters, today: date) -> list[PaymentOut]:
    rows = session.scalars(_query(session, f).order_by(Payment.payment_date.desc(), Payment.id.desc())).all()
    items = [_to_out(p, today) for p in rows]
    if f.service_stage:
        items = [i for i in items if f.service_stage in i.service_stages]
    if f.act_status:  # статус вычисляемый, поэтому фильтр применяется после расчёта
        items = [i for i in items if i.act_status == f.act_status]
    return items


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/import/statement", response_model=ImportReportOut)
async def import_statement_endpoint(file: UploadFile, session: Session = Depends(get_session)):
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "файл слишком большой (максимум 10 МБ)")
    try:
        report = import_statement(session, content)
    except StatementFormatError as e:
        raise HTTPException(400, str(e)) from e
    data = report._asdict()
    data["skipped"] = [g._asdict() for g in report.skipped]
    return ImportReportOut(**data)


@router.get("/payments", response_model=PaymentPage)
def list_payments(
    session: Session = Depends(get_session),
    f: PaymentFilters = Depends(),
    today: date = Depends(today_msk),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    items = _filtered(session, f, today)
    return PaymentPage(items=items[offset : offset + limit], total=len(items))


@router.get("/summary", response_model=DashboardOut)
def summary(
    session: Session = Depends(get_session),
    f: PaymentFilters = Depends(),
    today: date = Depends(today_msk),
):
    """Сводка считается по ТЕКУЩЕМУ фильтру, а не по всей базе — иначе цифры врут."""
    items = _filtered(session, f, today)
    views = [
        PaymentView(
            amount=i.amount,
            status=compute_act_status(
                is_sent=i.is_sent, is_signed=i.is_signed, payment_date=i.payment_date, today=today
            ),
            project_id=i.project_id,
            project_name=i.project_name,
            is_sent=i.is_sent,
            is_signed=i.is_signed,
        )
        for i in items
    ]
    return DashboardOut(
        totals=summarize(views)._asdict(),
        by_project=[p._asdict() for p in summarize_by_project(views)],
    )


@router.patch("/payments/{payment_id}/act", response_model=PaymentOut)
def patch_act(
    payment_id: int,
    payload: ActPatch,
    session: Session = Depends(get_session),
    today: date = Depends(today_msk),
):
    payment = session.get(Payment, payment_id, options=[selectinload(Payment.act)])
    if not payment:
        raise HTTPException(404, "оплата не найдена")
    act = payment.act or Act(payment_id=payment.id)
    _apply_act(act, payload.is_sent, payload.is_signed, today)
    if payload.manager_comment is not None:
        act.manager_comment = payload.manager_comment
    payment.act = act
    session.commit()
    session.refresh(payment)
    return _to_out(payment, today)


@router.post("/payments/bulk-act", response_model=dict)
def bulk_act(payload: BulkActIn, session: Session = Depends(get_session), today: date = Depends(today_msk)):
    """Массовое действие: отметить видимые акты отправленными/подписанными."""
    payments = session.scalars(
        select(Payment).where(Payment.id.in_(payload.payment_ids)).options(selectinload(Payment.act))
    ).all()
    for payment in payments:
        act = payment.act or Act(payment_id=payment.id)
        _apply_act(act, payload.is_sent, payload.is_signed, today)
        payment.act = act
    session.commit()
    return {"updated": len(payments)}


def _apply_act(act: Act, is_sent: bool | None, is_signed: bool | None, today: date) -> None:
    """Подпись подразумевает отправку: недопустимого состояния «подписан, но не отправлен» не создаём."""
    if is_sent is not None:
        act.is_sent = is_sent
        act.sent_at = today if is_sent else None
        if not is_sent:
            act.is_signed, act.signed_at = False, None
    if is_signed is not None:
        act.is_signed = is_signed
        act.signed_at = today if is_signed else None
        if is_signed and not act.is_sent:
            act.is_sent, act.sent_at = True, act.sent_at or today


@router.patch("/payments/{payment_id}/project", response_model=PaymentOut)
def patch_project(
    payment_id: int,
    payload: ProjectPatch,
    session: Session = Depends(get_session),
    today: date = Depends(today_msk),
):
    """Ручная привязка менеджером. Способ становится manual и переживает переимпорт."""
    payment = session.get(Payment, payment_id, options=[selectinload(Payment.act)])
    if not payment:
        raise HTTPException(404, "оплата не найдена")
    if payload.project_id is not None and not session.get(Project, payload.project_id):
        raise HTTPException(404, "проект не найден")
    payment.project_id = payload.project_id
    payment.binding_method = "manual" if payload.project_id else "unbound"
    payment.conflict_reason = None
    session.commit()
    session.refresh(payment)
    return _to_out(payment, today)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: Session = Depends(get_session)):
    rows = session.execute(
        select(Project, LegalEntity.name).join(LegalEntity, LegalEntity.id == Project.client_id).order_by(Project.name)
    ).all()
    return [
        ProjectOut(
            id=p.id,
            name=p.name,
            client_id=p.client_id,
            client_name=client_name,
            contract_number=p.contract_number,
            service_stage=p.service_stage,
            auto_created=p.auto_created,
        )
        for p, client_name in rows
    ]


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def rename_project(project_id: int, payload: ProjectRename, session: Session = Depends(get_session)):
    """Переименование проекта-черновика: автосозданный проект менеджер приводит в порядок."""
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(404, "проект не найден")
    project.name = payload.name
    project.auto_created = False
    session.commit()
    client = session.get(LegalEntity, project.client_id)
    return ProjectOut(
        id=project.id,
        name=project.name,
        client_id=project.client_id,
        client_name=client.name,
        contract_number=project.contract_number,
        service_stage=project.service_stage,
        auto_created=project.auto_created,
    )


@router.post("/projects/rebind", response_model=dict)
def rebind(session: Session = Depends(get_session)):
    """Пересчёт привязки после пополнения справочника. Трогает ТОЛЬКО непривязанные."""
    return {"bound": rebind_unbound(session)}


@router.get("/clients", response_model=list[ClientOut])
def list_clients(session: Session = Depends(get_session)):
    return session.scalars(select(LegalEntity).order_by(LegalEntity.name)).all()


@router.get("/export.csv")
def export_csv(
    session: Session = Depends(get_session),
    f: PaymentFilters = Depends(),
    today: date = Depends(today_msk),
):
    """Выгружает ровно то, что видно под фильтром. UTF-8 с BOM — Excel открывает без плясок."""
    items = _filtered(session, f, today)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        ["Дата", "Клиент", "ИНН", "Проект", "Этап", "Счёт", "Договор", "Сумма",
         "Акт отправлен", "Акт подписан", "Статус", "Комментарий", "Назначение"]
    )
    for i in items:
        writer.writerow([
            i.payment_date.strftime("%d.%m.%Y"), i.client_name, i.client_inn,
            i.project_name or "Без проекта", ", ".join(i.service_stages),
            ", ".join(i.invoice_numbers), i.contract_number or "", f"{i.amount:.2f}",
            "да" if i.is_sent else "нет", "да" if i.is_signed else "нет",
            i.act_status, i.manager_comment, i.purpose_text,
        ])
    data = "﻿" + buf.getvalue()
    return Response(
        content=data.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="payments.csv"'},
    )
