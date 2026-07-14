# FILE: backend/tests/test_domain_parser.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Проверка парсера на эталонной выписке (V-M-PARSER).
#   SCOPE: Контрольные суммы подвала, направление, чистка назначения, ошибки файла.
#   LAYER: DOMAIN
#   DEPENDS: M-PARSER
#   LINKS: V-M-PARSER, VF-002
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   STATEMENT - байты эталонной выписки
#   test_* - контрольные суммы, направление, чистка, ошибки
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per module contract]
# END_CHANGE_SUMMARY

from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.parser import (
    StatementFormatError,
    clean_purpose,
    parse_statement,
)

STATEMENT = (Path(__file__).resolve().parents[2] / "bank_statement.pdf").read_bytes()

# Эталон выведен ручным разбором и сверен с подвалом выписки
EXPECTED_DEBIT_COUNT = 21
EXPECTED_CREDIT_COUNT = 26
EXPECTED_DEBIT_SUM = Decimal("2437811.53")
EXPECTED_CREDIT_SUM = Decimal("2220310.00")


def test_owner_from_header():
    owner, _ = parse_statement(STATEMENT)
    assert owner.account == "40802810937184056213"
    assert owner.inn == "782934761208"  # ИП — ИНН 12-значный


def test_control_sums_match_footer():
    """Парсер доказывает сам себя: числа обязаны сойтись с подвалом выписки."""
    _, ops = parse_statement(STATEMENT)
    debit = [o for o in ops if o.direction == "debit"]
    credit = [o for o in ops if o.direction == "credit"]
    assert len(debit) == EXPECTED_DEBIT_COUNT
    assert len(credit) == EXPECTED_CREDIT_COUNT
    assert len(ops) == EXPECTED_DEBIT_COUNT + EXPECTED_CREDIT_COUNT
    assert sum(o.amount for o in debit) == EXPECTED_DEBIT_SUM
    assert sum(o.amount for o in credit) == EXPECTED_CREDIT_SUM


def test_operations_have_required_fields():
    _, ops = parse_statement(STATEMENT)
    for o in ops:
        assert o.amount > 0
        assert o.direction in ("debit", "credit")
        assert o.date.year == 2026
    # у большинства операций есть контрагент с ИНН
    with_inn = [o for o in ops if o.counterparty_inn]
    assert len(with_inn) >= 40


def test_purpose_cleaned_from_tax_tail():
    """Налоговый хвост обязан быть срезан ДО классификации: иначе слово «налог»
    в «Без налога (НДС)» отправит реальные оплаты в налоги."""
    assert clean_purpose("Оплата по счету № 733. Без налога (НДС).") == "Оплата по счету № 733"
    assert clean_purpose("Оплата за SEO. НДС не облагается.") == "Оплата за SEO"
    assert clean_purpose("Оплата по счету № 771. Сумма 60500-00. Без НДС.") == (
        "Оплата по счету № 771. Сумма 60500-00"
    )
    assert "налог" not in clean_purpose("Услуги. Без налога (НДС).").lower()


def test_purpose_cleaned_from_page_marks():
    assert clean_purpose("Оплата по счету № 751 от 16 июля 2026 г. 1 / 5") == (
        "Оплата по счету № 751 от 16 июля 2026 г"
    )


def test_reference_payments_are_credit():
    """Реальные оплаты клиентов из выписки распознаны как приход."""
    _, ops = parse_statement(STATEMENT)
    by_purpose = {o.purpose_text: o for o in ops}
    sigma = [o for o in ops if "Размещение объявлений" in o.purpose_text]
    assert sigma and sigma[0].direction == "credit"
    assert sigma[0].amount == Decimal("54400.00")


def test_not_a_pdf():
    with pytest.raises(StatementFormatError):
        parse_statement(b"not a pdf at all")
