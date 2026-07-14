# FILE: backend/tests/test_domain_act_status.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Матрица статусов актов и границы SLA (V-M-ACTSTATUS, VF-004).
#   SCOPE: Все комбинации флагов и возраста; closed окончателен; недопустимое состояние.
#   LAYER: DOMAIN
#   DEPENDS: M-ACTSTATUS
#   LINKS: V-M-ACTSTATUS
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   test_* - матрица, границы sla, краевые случаи
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per module contract]
# END_CHANGE_SUMMARY

from datetime import date, timedelta

import pytest

from app.domain.act_status import DEFAULT_SLA_DAYS, ActStatus, compute_act_status

TODAY = date(2026, 8, 14)
FRESH = TODAY - timedelta(days=3)
OLD = TODAY - timedelta(days=30)


@pytest.mark.parametrize(
    "is_sent,is_signed,payment_date,expected",
    [
        (False, False, FRESH, ActStatus.NOT_SENT),
        (True, False, FRESH, ActStatus.AWAITING_SIGNATURE),
        (True, True, FRESH, ActStatus.CLOSED),
        (False, False, OLD, ActStatus.NEEDS_ATTENTION),
        (True, False, OLD, ActStatus.NEEDS_ATTENTION),
        (True, True, OLD, ActStatus.CLOSED),  # закрытый акт просрочкой не становится
    ],
)
def test_status_matrix(is_sent, is_signed, payment_date, expected):
    assert compute_act_status(
        is_sent=is_sent, is_signed=is_signed, payment_date=payment_date, today=TODAY
    ) is expected


def test_sla_boundary_is_strict():
    """Ровно sla_days — ещё в срок. День спустя — просрочка."""
    exactly = TODAY - timedelta(days=DEFAULT_SLA_DAYS)
    day_after = TODAY - timedelta(days=DEFAULT_SLA_DAYS + 1)
    assert compute_act_status(is_sent=False, is_signed=False, payment_date=exactly, today=TODAY) is ActStatus.NOT_SENT
    assert compute_act_status(is_sent=False, is_signed=False, payment_date=day_after, today=TODAY) is ActStatus.NEEDS_ATTENTION


def test_custom_sla():
    d = TODAY - timedelta(days=5)
    assert compute_act_status(is_sent=False, is_signed=False, payment_date=d, today=TODAY, sla_days=3) is ActStatus.NEEDS_ATTENTION
    assert compute_act_status(is_sent=False, is_signed=False, payment_date=d, today=TODAY, sla_days=10) is ActStatus.NOT_SENT


def test_future_payment_date_is_not_overdue():
    future = TODAY + timedelta(days=5)
    assert compute_act_status(is_sent=False, is_signed=False, payment_date=future, today=TODAY) is ActStatus.NOT_SENT


def test_signed_without_sent_is_invalid_state():
    with pytest.raises(ValueError):
        compute_act_status(is_sent=False, is_signed=True, payment_date=FRESH, today=TODAY)
