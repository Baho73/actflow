# FILE: backend/app/domain/classify.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Определить вид операции: оплата клиента или посторонняя (налог, комиссия, перевод себе…).
#   SCOPE: Только классификация. В дашборд попадают ТОЛЬКО client_payment; остальное отсеивается с причиной.
#   LAYER: DOMAIN
#   DEPENDS: M-PARSER
#   LINKS: M-CLASSIFY, V-M-CLASSIFY, VF-002
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   classify_operation - RawOperation + owner -> (kind, reason)
#   OperationKind - виды операций
#   Reason - (code, text): код для группировки в отчёте, текст для человека
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-CLASSIFY contract]
# END_CHANGE_SUMMARY
#
# ГЛАВНОЕ РЕШЕНИЕ (стоило 322 000 руб выручки в разборе контрактов):
# классификация построена как ЧЁРНЫЙ СПИСОК, а не белый. Оплата клиента — это ЛЮБОЙ приход
# от стороннего контрагента, пока не сработало явное исключение. Требовать слово «оплата»
# в назначении нельзя: реальные оплаты выписки его не содержат («Размещение объявлений…
# по счету № 733»). А правила о СТОРОНАХ сделки идут раньше текстовых: формулировку банк
# может поменять, реквизиты — нет.

import logging
import re
from enum import StrEnum
from typing import NamedTuple

from app.domain.parser import RawOperation, StatementOwner

logger = logging.getLogger(__name__)


class OperationKind(StrEnum):
    CLIENT_PAYMENT = "client_payment"
    TAX = "tax"
    BANK_FEE = "bank_fee"
    BANK_INTEREST = "bank_interest"
    OWN_TRANSFER = "own_transfer"
    SALARY = "salary"
    RENT = "rent"
    CONTRACTOR_PAYMENT = "contractor_payment"
    OTHER = "other"


class Reason(NamedTuple):
    code: str  # для группировки в отчёте импорта
    text: str  # для человека


# Тексты причин отсева: отчёт импорта группируется по коду («Налоги: 4 операции на 256 180 ₽»)
REASONS = {
    OperationKind.CLIENT_PAYMENT: Reason("client_payment", "Оплата от клиента"),
    OperationKind.TAX: Reason("tax", "Налоги и взносы"),
    OperationKind.BANK_FEE: Reason("bank_fee", "Комиссия банка"),
    OperationKind.BANK_INTEREST: Reason("bank_interest", "Проценты банка"),
    OperationKind.OWN_TRANSFER: Reason("own_transfer", "Перевод между своими счетами"),
    OperationKind.SALARY: Reason("salary", "Зарплата и выплаты сотрудникам"),
    OperationKind.RENT: Reason("rent", "Аренда"),
    OperationKind.CONTRACTOR_PAYMENT: Reason("contractor_payment", "Оплата подрядчику или поставщику"),
    OperationKind.OTHER: Reason("other", "Прочая операция"),
}

# Налоговые якоря. Голая подстрока «налог» ЗАПРЕЩЕНА: она ловит хвост «Без налога (НДС)»
# у реальных оплат (парсер его срезает, но правило всё равно не должно на него опираться).
_TAX_ANCHORS = re.compile(r"НДФЛ|ЕНС|страховы[ех]\s+взнос|единый\s+налог|пенсионн", re.IGNORECASE)
_TAX_RECIPIENTS = re.compile(r"УФК|ФНС|Казначейств|налогов", re.IGNORECASE)

_SALARY = re.compile(r"зарплат|заработн|аванс.*сотрудник|под\s*отчет|отпускн", re.IGNORECASE)
_RENT = re.compile(r"аренд|наем помещ|найм помещ", re.IGNORECASE)
_BANK_FEE = re.compile(r"комисси|РКО|расчетно-кассов|валютн\w+ контрол", re.IGNORECASE)
_BANK_INTEREST = re.compile(r"процент", re.IGNORECASE)
_DEPOSIT = re.compile(r"депозит|вклад", re.IGNORECASE)


# START_CONTRACT: classify_operation
#   PURPOSE: Вид операции + причина. Классификация всегда даёт результат.
#   INPUTS: { op: RawOperation, owner: StatementOwner }
#   OUTPUTS: { (OperationKind, Reason) }
#   SIDE_EFFECTS: none
#   LINKS: правила и их порядок зафиксированы контрактом M-CLASSIFY note-2
# END_CONTRACT: classify_operation
def classify_operation(op: RawOperation, owner: StatementOwner) -> tuple[OperationKind, Reason]:
    # START_BLOCK_CLASSIFY_RULES
    kind = _decide(op, owner)
    # END_BLOCK_CLASSIFY_RULES
    reason = REASONS[kind]
    if kind is not OperationKind.CLIENT_PAYMENT:
        logger.debug(
            "[Classify][classify_operation][BLOCK_CLASSIFY_RULES] operation filtered out",
            extra={"kind": str(kind), "line": op.raw_line_no},
        )
    return kind, reason


def _decide(op: RawOperation, owner: StatementOwner) -> OperationKind:
    text = op.purpose_text

    # 1. Операция с самим собой. Идёт ПЕРВОЙ: возврат депозита приходит КРЕДИТОМ (810 000 ₽)
    #    и без этого правила раздул бы выручку на 58%. Реквизиты надёжнее текста.
    if op.counterparty_inn and op.counterparty_inn == owner.inn:
        return OperationKind.OWN_TRANSFER

    # 2. Обслуживающий банк: комиссии (расход) и проценты по депозиту (приход).
    #    Без этого правила проценты банка стали бы «оплатой клиента», а банк — «клиентом».
    if owner.bank_inn and op.counterparty_inn == owner.bank_inn:
        if op.direction == "credit" or _BANK_INTEREST.search(text):
            return OperationKind.BANK_INTEREST
        return OperationKind.BANK_FEE

    # 3. Налоги: по получателю (УФК/ФНС/Казначейство) или по якорным фразам.
    if _TAX_RECIPIENTS.search(op.counterparty_name) or _TAX_ANCHORS.search(text):
        return OperationKind.TAX

    # 4. Расходы (дебет) — детализируем, чтобы отчёт импорта читался как понимание бизнеса,
    #    а не «23 строки прочего».
    if op.direction == "debit":
        if _BANK_FEE.search(text):
            return OperationKind.BANK_FEE
        if _SALARY.search(text):
            return OperationKind.SALARY
        if _RENT.search(text):
            return OperationKind.RENT
        if _DEPOSIT.search(text):
            return OperationKind.OWN_TRANSFER  # размещение во вклад — движение своих денег
        return OperationKind.CONTRACTOR_PAYMENT

    # 5. Любой оставшийся приход — оплата клиента. Это дефолт, а не белый список.
    return OperationKind.CLIENT_PAYMENT
