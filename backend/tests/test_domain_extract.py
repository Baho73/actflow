# FILE: backend/tests/test_domain_extract.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Проверка извлечения реквизитов на реальных назначениях выписки (V-M-EXTRACT).
#   SCOPE: Счета (в т.ч. перечисление), договоры разных форм, услуги, ловушки regex.
#   LAYER: DOMAIN
#   DEPENDS: M-EXTRACT
#   LINKS: V-M-EXTRACT
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   test_* - счета, договоры, услуги, негативные тесты на ловушки реальной выписки
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per module contract]
# END_CHANGE_SUMMARY

import pytest

from app.domain.extract import extract_payment_details


def test_single_invoice():
    d = extract_payment_details("Оплата по счету № 746 от 10.07.2026 г. за настройку Директа")
    assert d.invoice_numbers == ["746"]


def test_multiple_invoices_real_case():
    """Реальный краевой случай выписки: один платёж по трём счетам."""
    d = extract_payment_details(
        "Оплата по счетам № 738, 791 и 792. Ежемесячное сопровождение сайта и услуги наполнения сайта"
    )
    assert d.invoice_numbers == ["738", "791", "792"]


def test_invoice_order_variants():
    assert extract_payment_details("Оплата по сч. № 728 от 15.07.2026, аванс по договору № 214").invoice_numbers == ["728"]
    assert extract_payment_details("Оплата по счет-заказу № 5381124 от 01.08.2026").invoice_numbers == ["5381124"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Оплата по счету № 771 по договору № 224 от 13.09.2025 за разработку сайта", "224"),
        ("Оплата по счету № 731, договор услуг № 318 от 27.04.2025", "318"),
        ("Оплата по договору № 306 от 18.06.2026, по сч. № 748", "306"),
        ("Возврат депозита по договору 981200-АНОН от 27.06.2026", "981200-АНОН"),
    ],
)
def test_contract_forms(text, expected):
    assert extract_payment_details(text).contract_number == expected


def test_rko_contract_is_not_project_contract():
    """«Договор РКО № 40802810937184056213» — служебный договор с банком, не проектный."""
    d = extract_payment_details(
        "Комиссия в другие банки. Договор РКО № 40802810937184056213 от 15.03.2024"
    )
    assert d.contract_number is None


def test_noise_is_not_taken_for_requisites():
    """Реальные ловушки: «Сумма 107500-00», «НДС 6-48», «реестру № 58»."""
    d = extract_payment_details("Оплата по счету № 731 за маркетинговые услуги. Сумма 107500-00")
    assert d.invoice_numbers == ["731"]

    d2 = extract_payment_details("Перевод средств предпринимателя на личный счет по реестру № 58")
    assert d2.invoice_numbers == []

    d3 = extract_payment_details("Комиссия, в т. ч. НДС 6-48 RUR (по операции 31864-00 RUB)")
    assert d3.invoice_numbers == []


def test_two_services_in_one_payment():
    """Реальный случай: в платеже две услуги — угадывать одну нельзя."""
    d = extract_payment_details("Ежемесячное сопровождение сайта и услуги наполнения сайта")
    assert set(d.service_stages) == {"Сопровождение сайта", "Наполнение сайта"}


@pytest.mark.parametrize(
    "text,service",
    [
        ("за настройку и сопровождение Директа", "Контекстная реклама"),
        ("за SEO-оптимизацию и продвижение сайта", "SEO"),
        ("услуги SERM 15.07.2026-14.08.2026", "SERM"),
        ("финальный платеж за этап дизайна", "Дизайн"),
        ("за разработку лендинга учебного проекта", "Лендинг"),
        ("Оплата за разработку личного кабинета", "Личный кабинет"),
        ("за подготовку коммерческих текстов", "Копирайтинг"),
        ("за маркетинговые услуги", "Маркетинговые услуги"),
        ("Размещение объявлений на сервисе", "Размещение объявлений"),
        ("за авансовый платеж на создание презентации", "Презентация"),
    ],
)
def test_service_dictionary_covers_real_purposes(text, service):
    assert service in extract_payment_details(text).service_stages


def test_personal_cabinet_not_confused_with_site():
    """Длинные фразы раньше коротких: «личный кабинет» не должен стать «разработкой сайта»."""
    d = extract_payment_details("Оплата за разработку личного кабинета по счету № 776")
    assert d.service_stages[0] == "Личный кабинет"


def test_no_requisites_is_valid_result():
    """«Оплата за услуги по SEO-продвижению сайта» — ни счёта, ни договора. Это не ошибка."""
    d = extract_payment_details("Оплата за услуги по SEO-продвижению сайта")
    assert d.invoice_numbers == []
    assert d.contract_number is None
    assert d.service_stages == ["SEO"]
