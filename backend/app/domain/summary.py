# FILE: backend/app/domain/summary.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Свести показатели дашборда по выборке оплат (итоги + разрез по проектам).
#   SCOPE: Чистая агрегация. Инварианты полноты обязательны — на них ловят враньё цифр.
#   LAYER: DOMAIN
#   DEPENDS: M-ACTSTATUS
#   LINKS: M-SUMMARY, V-M-SUMMARY, VF-005
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   summarize - оплаты -> Totals (итоги дашборда)
#   summarize_by_project - оплаты -> [ProjectSummary] (включая строку «Без проекта»)
#   PaymentView - вход агрегации (сумма, статус, проект)
#   Totals / ProjectSummary - результаты
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-SUMMARY contract]
# END_CHANGE_SUMMARY

from decimal import Decimal
from typing import Iterable, NamedTuple

from app.domain.act_status import ActStatus

ZERO = Decimal("0.00")


class PaymentView(NamedTuple):
    amount: Decimal
    status: ActStatus
    project_id: int | None
    project_name: str | None
    is_sent: bool
    is_signed: bool


class Totals(NamedTuple):
    total_amount: Decimal
    payments_count: int
    projects_count: int
    closed_amount: Decimal
    open_amount: Decimal
    needs_attention_amount: Decimal  # ключевая цифра руководителя: сколько денег висит просроченным
    closed_count: int
    not_sent_count: int
    awaiting_count: int
    needs_attention_count: int


class ProjectSummary(NamedTuple):
    project_id: int | None
    project_name: str  # «Без проекта» для непривязанных
    payments_count: int
    total: Decimal
    sent_count: int
    signed_count: int
    closed_ratio: Decimal | None  # None при total == 0 — деления на ноль нет


# START_CONTRACT: summarize
#   PURPOSE: Итоги дашборда.
#   INPUTS: { payments: Iterable[PaymentView] }
#   OUTPUTS: { Totals }
#   SIDE_EFFECTS: none
#   INVARIANTS: closed + open == total; сумма счётчиков статусов == payments_count
# END_CONTRACT: summarize
def summarize(payments: Iterable[PaymentView]) -> Totals:
    items = list(payments)
    total = sum((p.amount for p in items), ZERO)
    closed = sum((p.amount for p in items if p.status is ActStatus.CLOSED), ZERO)
    attention = sum((p.amount for p in items if p.status is ActStatus.NEEDS_ATTENTION), ZERO)
    projects = {p.project_id for p in items if p.project_id is not None}

    return Totals(
        total_amount=total,
        payments_count=len(items),
        projects_count=len(projects),
        closed_amount=closed,
        open_amount=total - closed,  # needs_attention относится к open, а не к отдельной корзине
        needs_attention_amount=attention,
        closed_count=sum(1 for p in items if p.status is ActStatus.CLOSED),
        not_sent_count=sum(1 for p in items if p.status is ActStatus.NOT_SENT),
        awaiting_count=sum(1 for p in items if p.status is ActStatus.AWAITING_SIGNATURE),
        needs_attention_count=sum(1 for p in items if p.status is ActStatus.NEEDS_ATTENTION),
    )


# START_CONTRACT: summarize_by_project
#   PURPOSE: Разрез по проектам; непривязанные оплаты — строкой «Без проекта».
#   INPUTS: { payments: Iterable[PaymentView] }
#   OUTPUTS: { list[ProjectSummary] }
#   SIDE_EFFECTS: none
#   INVARIANTS: Σ by_project.total == total_amount (иначе часть денег исчезает из разреза)
# END_CONTRACT: summarize_by_project
def summarize_by_project(payments: Iterable[PaymentView]) -> list[ProjectSummary]:
    groups: dict[int | None, list[PaymentView]] = {}
    for p in payments:
        groups.setdefault(p.project_id, []).append(p)

    result: list[ProjectSummary] = []
    for project_id, items in groups.items():
        total = sum((p.amount for p in items), ZERO)
        closed = sum((p.amount for p in items if p.status is ActStatus.CLOSED), ZERO)
        result.append(
            ProjectSummary(
                project_id=project_id,
                project_name=(items[0].project_name or "Без проекта") if project_id else "Без проекта",
                payments_count=len(items),
                total=total,
                sent_count=sum(1 for p in items if p.is_sent),
                signed_count=sum(1 for p in items if p.is_signed),
                closed_ratio=(closed / total) if total > 0 else None,
            )
        )
    # непривязанные — в конец списка: сначала проекты, потом «хвост»
    result.sort(key=lambda r: (r.project_id is None, -r.total))
    return result
