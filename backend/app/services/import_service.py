# FILE: backend/app/services/import_service.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Импорт выписки: домен разбирает и решает, этот слой сохраняет.
#   SCOPE: Оркестрация парсер → классификация → извлечение → привязка → запись + отчёт.
#   LAYER: API (сервисный слой: единственное место, где домен встречается с БД)
#   DEPENDS: M-PARSER, M-CLASSIFY, M-EXTRACT, M-BINDING, M-MODELS
#   LINKS: M-API, DF-IMPORT, VF-002, VF-006
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   import_statement - bytes -> ImportReport (принято / уже было / отсеяно с причинами)
#   ImportReport / SkippedGroup - отчёт импорта
#   rebind_unbound - пересчёт привязки после пополнения справочника (только unbound)
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-API contract]
# END_CHANGE_SUMMARY
#
# Отчёт из трёх корзин — требование контракта: пользователь должен видеть не только что
# принято, но и что отсеяно и почему (молчаливого выбрасывания нет), и что уже было.

import logging
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.binding import BindingMethod, ProjectRef, bind_payment
from app.domain.classify import OperationKind, classify_operation
from app.domain.extract import extract_payment_details
from app.domain.parser import RawOperation, StatementOwner, parse_statement
from app.models import Act, LegalEntity, Payment, Project, make_dedup_key

logger = logging.getLogger(__name__)


class SkippedGroup(NamedTuple):
    code: str
    text: str
    count: int
    amount: Decimal


class ImportReport(NamedTuple):
    imported: int
    already_known: int
    skipped: list[SkippedGroup]
    created_projects: int
    unbound: int


# START_CONTRACT: import_statement
#   PURPOSE: Разобрать выписку и сохранить оплаты клиентов; вернуть честный отчёт.
#   INPUTS: { session, content: bytes }
#   OUTPUTS: { ImportReport }
#   SIDE_EFFECTS: запись LegalEntity/Project/Payment/Act; commit
#   LINKS: идемпотентность — по dedup_key; повторная загрузка не двоит и не обновляет
# END_CONTRACT: import_statement
def import_statement(session: Session, content: bytes) -> ImportReport:
    # START_BLOCK_IMPORT_STATEMENT
    owner, operations = parse_statement(content)

    payments: list[tuple[RawOperation, object]] = []
    skipped: dict[str, list[RawOperation]] = {}
    skipped_text: dict[str, str] = {}

    for op in operations:
        kind, reason = classify_operation(op, owner)
        if kind is OperationKind.CLIENT_PAYMENT:
            payments.append((op, reason))
        else:
            skipped.setdefault(reason.code, []).append(op)
            skipped_text[reason.code] = reason.text

    imported = already = created_projects = unbound = 0

    for op, _ in payments:
        if not op.counterparty_inn:
            skipped.setdefault("no_inn", []).append(op)
            skipped_text["no_inn"] = "Не удалось определить ИНН плательщика"
            continue

        key = make_dedup_key(op.date, op.amount, op.doc_number, op.counterparty_inn, op.direction)
        if session.scalar(select(Payment).where(Payment.dedup_key == key)):
            already += 1  # повторная загрузка: существующую оплату НЕ трогаем,
            continue      # поэтому ручная привязка переживает переимпорт по построению

        client = _get_or_create_client(session, op.counterparty_inn, op.counterparty_name)
        details = extract_payment_details(op.purpose_text)
        binding = bind_payment(
            client_inn=client.inn,
            client_name=client.name,
            contract_number=details.contract_number,
            service_stages=details.service_stages,
            projects=_project_refs(session),
        )

        project_id = binding.project_id
        if binding.draft_project:
            project = Project(
                name=binding.draft_project.name,
                client_id=client.id,
                contract_number=binding.draft_project.contract_number,
                service_stage=binding.draft_project.service_stage,
                auto_created=True,
            )
            session.add(project)
            session.flush()
            project_id = project.id
            created_projects += 1

        method = binding.method if project_id else BindingMethod.UNBOUND
        if not project_id:
            unbound += 1

        payment = Payment(
            client_id=client.id,
            project_id=project_id,
            binding_method=str(method),
            conflict_reason=binding.conflict_reason,
            stage_mismatch=binding.stage_mismatch,
            payment_date=op.date,
            amount=op.amount,
            purpose_text=op.purpose_text,
            doc_number=op.doc_number,
            invoice_numbers=details.invoice_numbers,
            contract_number=details.contract_number,
            service_stages=details.service_stages,
            dedup_key=key,
        )
        payment.act = Act()
        session.add(payment)
        session.flush()
        imported += 1

    session.commit()

    groups = [
        SkippedGroup(code, skipped_text[code], len(ops), sum(o.amount for o in ops))
        for code, ops in sorted(skipped.items(), key=lambda kv: -sum(o.amount for o in kv[1]))
    ]
    logger.info(
        "[Api][import_statement][BLOCK_IMPORT_STATEMENT] statement imported",
        extra={"imported": imported, "already": already, "skipped_groups": len(groups)},
    )
    # END_BLOCK_IMPORT_STATEMENT
    return ImportReport(imported, already, groups, created_projects, unbound)


def _get_or_create_client(session: Session, inn: str, name: str) -> LegalEntity:
    """Клиенты создаются ТОЛЬКО отсюда — из оплат. Налоговая и банк в справочник не попадают."""
    client = session.scalar(select(LegalEntity).where(LegalEntity.inn == inn))
    if client:
        return client
    client = LegalEntity(inn=inn, name=name or f"ИНН {inn}")
    session.add(client)
    session.flush()
    return client


def _project_refs(session: Session) -> list[ProjectRef]:
    rows = session.execute(
        select(Project.id, Project.name, LegalEntity.inn, Project.contract_number, Project.service_stage)
        .join(LegalEntity, LegalEntity.id == Project.client_id)
    ).all()
    return [ProjectRef(*r) for r in rows]


# START_CONTRACT: rebind_unbound
#   PURPOSE: Пересчитать привязку после пополнения справочника проектов.
#   INPUTS: { session }
#   OUTPUTS: { int — сколько оплат привязалось }
#   SIDE_EFFECTS: обновляет ТОЛЬКО оплаты с binding_method == unbound
#   LINKS: manual и by_contract не трогаются никогда — иначе ручная работа менеджера пропадёт
# END_CONTRACT: rebind_unbound
def rebind_unbound(session: Session) -> int:
    projects = _project_refs(session)
    unbound = session.scalars(
        select(Payment).where(Payment.binding_method == str(BindingMethod.UNBOUND))
    ).all()
    bound = 0
    for payment in unbound:
        client = session.get(LegalEntity, payment.client_id)
        binding = bind_payment(
            client_inn=client.inn,
            client_name=client.name,
            contract_number=payment.contract_number,
            service_stages=payment.service_stages or [],
            projects=projects,
        )
        if binding.project_id:
            payment.project_id = binding.project_id
            payment.binding_method = str(binding.method)
            payment.conflict_reason = None
            payment.stage_mismatch = binding.stage_mismatch
            bound += 1
    session.commit()
    return bound
