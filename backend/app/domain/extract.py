# FILE: backend/app/domain/extract.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Из назначения платежа вытащить бизнес-реквизиты: счета, договор, типы услуг.
#   SCOPE: Чистый разбор текста. Отсутствие реквизита — валидный результат, не ошибка.
#   LAYER: DOMAIN
#   DEPENDS: none
#   LINKS: M-EXTRACT, V-M-EXTRACT
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   extract_payment_details - назначение -> PaymentDetails(счета[], договор?, услуги[])
#   PaymentDetails - извлечённые реквизиты
#   SERVICE_DICTIONARY - упорядоченный словарь услуг агентства (длинные фразы раньше коротких)
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-EXTRACT contract]
# END_CHANGE_SUMMARY
#
# Извлекаем ТОЛЬКО по якорям («счет», «договор»), а не «любое число после №»: в реальных
# назначениях есть «Сумма 107500-00», «реестру № 58», «НДС 6-48», «Договор РКО № 4080…».
# Услуг в платеже может быть ДВЕ («сопровождение и наполнение сайта») — поэтому список.

import re
from typing import NamedTuple


class PaymentDetails(NamedTuple):
    invoice_numbers: list[str]
    contract_number: str | None
    service_stages: list[str]  # список: в платеже бывает две услуги


# Упорядоченный словарь: длинные фразы РАНЬШЕ коротких, иначе «разработка личного кабинета»
# матчится как «разработка сайта». Первое совпадение побеждает.
SERVICE_DICTIONARY: list[tuple[str, str]] = [
    (r"личн\w+ кабинет", "Личный кабинет"),
    (r"контекстн\w+ реклам|директ|ведени\w+ кампани", "Контекстная реклама"),
    (r"реклам\w+ кампани|сопровождени\w+ реклам", "Реклама"),
    (r"seo[\s-]*оптимизаци|seo[\s-]*продвижени|seo", "SEO"),
    (r"serm", "SERM"),
    (r"smm|соцсет|социальн\w+ сет", "SMM"),
    (r"этап\w* дизайн|дизайн", "Дизайн"),
    (r"разработк\w+ лендинг|лендинг", "Лендинг"),
    (r"разработк\w+ сайт|создани\w+ сайт", "Разработка сайта"),
    (r"наполнени\w+ сайт|публикаци\w+ .*материал", "Наполнение сайта"),
    (r"техническ\w+ сопровождени|сопровождени\w+ сайт|ежемесячн\w+ сопровождени", "Сопровождение сайта"),
    (r"копирайтинг|коммерческ\w+ текст|подготовк\w+ .*текст|проектировани\w+ и копирайтинг", "Копирайтинг"),
    (r"маркетингов\w+ услуг", "Маркетинговые услуги"),
    (r"размещени\w+ объявлени", "Размещение объявлений"),
    (r"презентаци", "Презентация"),
    (r"лицензи|прав\w+ на программ", "Лицензии и ПО"),
    (r"проектн\w+ команд", "Услуги проектной команды"),
    (r"проектировани", "Проектирование"),
]

# Якоря счетов. «счет-заказ» тоже счёт; «реестр» — нет.
# Захват перечисления целиком: «по счетам № 738, 791 и 792» — иначе средний номер теряется.
_INVOICE_ANCHOR = re.compile(
    r"(?:сч(?:ет|ёт|\.|етам|ету|етов)?(?:-заказу?)?)\s*№?\s*((?:\d+\s*(?:,|и)?\s*)+)",
    re.IGNORECASE,
)
# Договор: «договор № 61», «договор услуг № 318», «договору 981200-АНОН» (без №), «№ 17-А/26»
_CONTRACT_ANCHOR = re.compile(
    r"договор\w*(?:\s+услуг)?\s*№?\s*([\dA-Za-zА-Яа-я\-/]+)",
    re.IGNORECASE,
)
# Служебные конструкции, которые НЕЛЬЗЯ принимать за реквизиты (реальные ловушки выписки)
_NOISE = re.compile(r"Сумма\s+\d+-\d{2}|НДС\s+[\d-]+|реестр\w*\s*№?\s*\d+", re.IGNORECASE)
_RKO_CONTRACT = re.compile(r"договор\w*\s+РКО", re.IGNORECASE)


# START_CONTRACT: extract_payment_details
#   PURPOSE: Назначение → (счета, договор, услуги). Ничего не угадывает: нет реквизита — пусто.
#   INPUTS: { purpose_text: str }
#   OUTPUTS: { PaymentDetails }
#   SIDE_EFFECTS: none
#   LINKS: M-BINDING (потребитель)
# END_CONTRACT: extract_payment_details
def extract_payment_details(purpose_text: str) -> PaymentDetails:
    # START_BLOCK_STRIP_NOISE
    text = _NOISE.sub(" ", purpose_text)  # «Сумма 107500-00», «НДС 6-48», «реестр № 58»
    # END_BLOCK_STRIP_NOISE

    invoices = _extract_invoices(text)
    contract = _extract_contract(text)
    services = _extract_services(purpose_text)  # услуги ищем в исходном тексте
    return PaymentDetails(invoice_numbers=invoices, contract_number=contract, service_stages=services)


def _extract_invoices(text: str) -> list[str]:
    """Поддерживает перечисление: «по счетам № 738, 791 и 792» → ['738','791','792']."""
    numbers: list[str] = []
    for m in _INVOICE_ANCHOR.finditer(text):
        numbers.extend(re.findall(r"\d+", m.group(1)))
    return list(dict.fromkeys(numbers))  # без дублей, порядок сохраняем


def _extract_contract(text: str) -> str | None:
    if _RKO_CONTRACT.search(text):
        return None  # «Договор РКО № 40802…» — служебный договор с банком, не проектный
    m = _CONTRACT_ANCHOR.search(text)
    if not m:
        return None
    value = m.group(1).strip(" .,")
    if not re.search(r"\d", value):  # «договор услуг» без номера
        return None
    return value


def _extract_services(text: str) -> list[str]:
    """Услуг может быть несколько: «сопровождение сайта И услуги наполнения сайта»."""
    found: list[str] = []
    for pattern, name in SERVICE_DICTIONARY:
        if re.search(pattern, text, re.IGNORECASE) and name not in found:
            found.append(name)
    return found
