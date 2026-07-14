# FILE: backend/tests/test_domain_summary.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Инварианты сводки (V-M-SUMMARY, VF-005): цифры карточек не должны врать.
#   SCOPE: Полнота сумм и счётчиков, разрез по проектам, «Без проекта».
#   LAYER: DOMAIN
#   DEPENDS: M-SUMMARY
#   LINKS: V-M-SUMMARY
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   view - хелпер построения PaymentView
#   test_* - инварианты полноты, разрез по проектам
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per module contract]
# END_CHANGE_SUMMARY

from decimal import Decimal

from app.domain.act_status import ActStatus
from app.domain.summary import PaymentView, summarize, summarize_by_project


def view(amount, status, project_id=1, name="Проект", sent=False, signed=False):
    return PaymentView(Decimal(amount), status, project_id, name, sent, signed)


PAYMENTS = [
    view("100.00", ActStatus.CLOSED, 1, "Сайт", sent=True, signed=True),
    view("200.00", ActStatus.AWAITING_SIGNATURE, 1, "Сайт", sent=True),
    view("300.00", ActStatus.NOT_SENT, 2, "SEO"),
    view("400.00", ActStatus.NEEDS_ATTENTION, None, None),
]


def test_totals_completeness_invariant():
    """closed + open == total. Иначе часть денег исчезает из карточек."""
    t = summarize(PAYMENTS)
    assert t.total_amount == Decimal("1000.00")
    assert t.closed_amount + t.open_amount == t.total_amount


def test_status_counters_sum_to_payments_count():
    """not_sent + awaiting + needs_attention + closed == payments_count."""
    t = summarize(PAYMENTS)
    assert (
        t.not_sent_count + t.awaiting_count + t.needs_attention_count + t.closed_count
        == t.payments_count
        == 4
    )


def test_needs_attention_is_part_of_open_and_has_amount():
    """Ключевая цифра руководителя: сколько денег висит просроченным."""
    t = summarize(PAYMENTS)
    assert t.needs_attention_amount == Decimal("400.00")
    assert t.needs_attention_amount <= t.open_amount


def test_projects_count_ignores_unbound():
    t = summarize(PAYMENTS)
    assert t.projects_count == 2  # проекты 1 и 2; непривязанная оплата проектом не считается


def test_by_project_sums_to_total_including_unbound():
    """Σ по проектам == общей сумме: непривязанные не должны выпадать из разреза."""
    rows = summarize_by_project(PAYMENTS)
    assert sum(r.total for r in rows) == summarize(PAYMENTS).total_amount
    unbound = [r for r in rows if r.project_id is None]
    assert len(unbound) == 1
    assert unbound[0].project_name == "Без проекта"
    assert unbound[0].total == Decimal("400.00")


def test_closed_ratio():
    rows = {r.project_id: r for r in summarize_by_project(PAYMENTS)}
    assert rows[1].closed_ratio == Decimal("100.00") / Decimal("300.00")
    assert rows[2].closed_ratio == Decimal("0")


def test_empty_selection_does_not_divide_by_zero():
    t = summarize([])
    assert t.total_amount == Decimal("0.00")
    assert t.payments_count == 0
    assert summarize_by_project([]) == []
