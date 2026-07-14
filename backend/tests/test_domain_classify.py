# FILE: backend/tests/test_domain_classify.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Проверка классификации на эталонной выписке (V-M-CLASSIFY, VF-002).
#   SCOPE: Точный эталон 24 оплаты / 1 405 820,00; регрессии дефектов, найденных до кода.
#   LAYER: DOMAIN
#   DEPENDS: M-CLASSIFY
#   LINKS: V-M-CLASSIFY, VF-002
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   parsed - фикстура: разобранная эталонная выписка
#   classified - все операции с их видом
#   test_* - эталон, регрессии, категории отсева
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per module contract]
# END_CHANGE_SUMMARY

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.classify import OperationKind, classify_operation
from app.domain.parser import parse_statement

STATEMENT = (Path(__file__).resolve().parents[2] / "bank_statement.pdf").read_bytes()

# ЭТАЛОН: выведен ручным разбором 47 операций, сверен с контрольными суммами подвала.
# 2 220 310,00 (весь приход) − 810 000,00 (возврат депозита себе) − 4 490,00 (проценты банка)
EXPECTED_CLIENT_PAYMENTS = 24
EXPECTED_CLIENT_AMOUNT = Decimal("1405820.00")


@pytest.fixture(scope="module")
def classified():
    owner, ops = parse_statement(STATEMENT)
    return owner, [(op, *classify_operation(op, owner)) for op in ops]


def test_reference_client_payments_exact(classified):
    """Главная цифра дашборда. Ошибка здесь искажает всё остальное."""
    _, rows = classified
    payments = [op for op, kind, _ in rows if kind is OperationKind.CLIENT_PAYMENT]
    assert len(payments) == EXPECTED_CLIENT_PAYMENTS
    assert sum(p.amount for p in payments) == EXPECTED_CLIENT_AMOUNT


def test_all_client_payments_are_income(classified):
    _, rows = classified
    for op, kind, _ in rows:
        if kind is OperationKind.CLIENT_PAYMENT:
            assert op.direction == "credit", f"расход не может быть оплатой клиента: {op.purpose_text}"


def test_regression_tax_tail_does_not_hijack_payments(classified):
    """РЕГРЕССИЯ (дефект найден до кода): хвост «Без налога (НДС)» у реальных оплат
    отправил бы 4 платежа на 211 800 ₽ в налоги."""
    _, rows = classified
    tax_ops = [op for op, kind, _ in rows if kind is OperationKind.TAX]
    for op in tax_ops:
        assert op.direction == "debit", "налог не может быть приходом"
    # платежи, у которых в исходнике был налоговый хвост, остались оплатами
    payments_text = " ".join(
        op.purpose_text for op, kind, _ in rows if kind is OperationKind.CLIENT_PAYMENT
    )
    assert "налог" not in payments_text.lower()  # хвост срезан парсером
    assert sum(1 for op, kind, _ in rows if kind is OperationKind.TAX) == 4


def test_regression_payment_without_word_oplata(classified):
    """РЕГРЕССИЯ: оплата без слова «оплата» в назначении (СИГМА-МАРКЕТ, 110 700 ₽)."""
    _, rows = classified
    sigma = [
        (op, kind)
        for op, kind, _ in rows
        if "Размещение объявлений" in op.purpose_text or "Настройка и ведение кампании" in op.purpose_text
    ]
    assert sigma, "тестовые платежи не найдены в выписке"
    for op, kind in sigma:
        assert kind is OperationKind.CLIENT_PAYMENT, f"потеряна оплата: {op.purpose_text}"


def test_deposit_return_is_not_revenue(classified):
    """Возврат депозита 810 000 ₽ приходит КРЕДИТОМ — но это движение своих денег."""
    _, rows = classified
    own = [op for op, kind, _ in rows if kind is OperationKind.OWN_TRANSFER]
    assert any(op.amount == Decimal("810000.00") and op.direction == "credit" for op in own)


def test_bank_interest_is_not_client_payment(classified):
    """Проценты банка (приход) не должны стать «оплатой клиента», а банк — «клиентом»."""
    _, rows = classified
    interest = [op for op, kind, _ in rows if kind is OperationKind.BANK_INTEREST]
    assert interest
    assert all(op.direction == "credit" for op in interest)


def test_every_filtered_operation_has_reason(classified):
    """Молчаливого выбрасывания нет: у каждой отсеянной операции есть код и текст причины."""
    _, rows = classified
    for op, kind, reason in rows:
        assert reason.code and reason.text
        if kind is not OperationKind.CLIENT_PAYMENT:
            assert reason.code != "client_payment"


def test_filtered_operations_grouped_by_reason(classified):
    """Отчёт импорта группируется по коду причины — это должно читаться как понимание бизнеса."""
    _, rows = classified
    groups: dict[str, list] = defaultdict(list)
    for op, kind, reason in rows:
        if kind is not OperationKind.CLIENT_PAYMENT:
            groups[reason.code].append(op)
    # все посторонние операции разложены по осмысленным категориям
    assert set(groups) >= {"tax", "own_transfer", "salary", "contractor_payment"}
    assert sum(len(v) for v in groups.values()) == 47 - EXPECTED_CLIENT_PAYMENTS
