# FILE: backend/app/domain/parser.py
# VERSION: 2.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Извлечь из PDF-выписки владельца счёта и список сырых операций.
#   SCOPE: Только извлечение фактов. Никакой интерпретации бизнес-смысла (это делает classify).
#   LAYER: DOMAIN
#   DEPENDS: none (pypdf — внешняя библиотека, спрятана за портом parse_statement)
#   LINKS: M-PARSER, V-M-PARSER, DF-IMPORT
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   parse_statement - bytes -> (StatementOwner, list[RawOperation]); самопроверка по подвалу
#   RawOperation - сырая операция выписки
#   StatementOwner - владелец счёта + обслуживающий банк
#   StatementFormatError - файл не выписка / контрольная сумма не сошлась
#   clean_purpose - снятие налогового хвоста и колонтитулов с назначения
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v2.0.0 - pdfplumber терял часть текстового слоя (ИНН и названия сторон
#                не извлекались). Перешли на pypdf; направление определяется по позиции счёта
#                владельца среди сторон операции — это правило из контракта и оно не зависит
#                от координат макета.]
# END_CHANGE_SUMMARY

import io
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple

import pypdf

logger = logging.getLogger(__name__)

_DATE_LINE = re.compile(r"^\s*(\d{2})\.(\d{2})\.(\d{4})\s*$")
_ACCOUNT = re.compile(r"\b\d{20}\b")
# ВАЖЕН ПОРЯДОК: 12 пробуем раньше 10, иначе у ИП (12-значный ИНН) отрежутся первые 10 цифр
# и в справочнике клиентов появится фантом. Дефект найден разбором контрактов до кода.
_INN_LABELED = re.compile(r"ИНН\s*(\d{12}|\d{10})")
_MONEY = re.compile(r"^\s*(\d[\d\s ]*,\d{2})\s*$")
_DOC_NUMBER = re.compile(r"^\s*(\d{1,10})\s*$")
_BIK_LINE = re.compile(r"^\s*БИК\b")
# Налоговый хвост срезается ДО классификации: иначе слово «налог» в «Без налога (НДС)»
# отправило бы реальные оплаты клиентов в налоги.
_TAX_TAIL = re.compile(
    r"\s*(Без налога \(НДС\)|НДС не облагается|Без НДС|в т\.?\s*ч\.?\s*НДС.*?)\.?\s*$",
    re.IGNORECASE,
)
_PAGE_MARK = re.compile(r"\s*\d+\s*/\s*\d+\s*$")
_FOOTER = re.compile(r"Количество\s+операций\s+(\d+)\s+(\d+)\s+(\d+)")
_ORG_HINT = re.compile(r"(ООО|АО|ЗАО|ПАО|ИП|УФК|ФНС|Казначейств)", re.IGNORECASE)


class StatementFormatError(Exception):
    """Файл не похож на выписку, нет текстового слоя, или контрольная сумма не сошлась."""


class StatementOwner(NamedTuple):
    account: str
    inn: str
    bank_name: str
    bank_inn: str | None  # нужен классификации: комиссии и проценты банка — не оплаты клиентов


@dataclass(frozen=True)
class RawOperation:
    date: date
    amount: Decimal
    direction: str  # "debit" (расход) | "credit" (приход)
    doc_number: str
    counterparty_name: str
    counterparty_inn: str | None
    purpose_text: str
    raw_line_no: int


# START_CONTRACT: parse_statement
#   PURPOSE: PDF → (владелец, операции). Парсер доказывает сам себя контрольной суммой подвала.
#   INPUTS: { content: bytes (PDF с текстовым слоем) }
#   OUTPUTS: { (StatementOwner, list[RawOperation]) }
#   SIDE_EFFECTS: none
#   LINKS: M-CLASSIFY (потребитель)
# END_CONTRACT: parse_statement
def parse_statement(content: bytes) -> tuple[StatementOwner, list[RawOperation]]:
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        raw_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:  # noqa: BLE001 — любая ошибка чтения = файл непригоден
        raise StatementFormatError("не удалось прочитать PDF") from e

    if "ВЫПИСКА" not in raw_text.upper():
        raise StatementFormatError("файл не похож на банковскую выписку")

    lines = [ln.rstrip() for ln in raw_text.splitlines()]
    owner_account = _owner_account(lines)

    # START_BLOCK_EXTRACT_OPERATIONS
    blocks = _split_into_operation_blocks(lines)
    operations = [op for op in (_parse_block(b, owner_account) for b in blocks) if op]
    # END_BLOCK_EXTRACT_OPERATIONS

    owner = _build_owner(owner_account, lines, operations)

    # START_BLOCK_SELF_CHECK
    _verify_against_footer(raw_text, operations)
    # END_BLOCK_SELF_CHECK

    logger.info(
        "[Parser][parse_statement][BLOCK_EXTRACT_OPERATIONS] parsed",
        extra={"operations": len(operations), "owner_inn": owner.inn},
    )
    return owner, operations


def _owner_account(lines: list[str]) -> str:
    """Счёт владельца — первый 20-значный счёт в шапке (до первой операции)."""
    for ln in lines[:40]:
        m = _ACCOUNT.search(ln)
        if m:
            return m.group(0)
    raise StatementFormatError("в шапке не найден счёт владельца — это не выписка")


def _split_into_operation_blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Операция начинается со строки-даты и тянется до следующей даты.
    Шапка (до первой операции) и подвал отбрасываются естественным образом."""
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] | None = None
    start = 0
    for i, ln in enumerate(lines):
        if _DATE_LINE.match(ln):
            if current:
                blocks.append((start, current))
            current, start = [ln], i
        elif current is not None:
            current.append(ln)
    if current:
        blocks.append((start, current))
    return blocks


def _parse_block(block: tuple[int, list[str]], owner_account: str) -> RawOperation | None:
    """Блок операции: дата, две стороны (счёт+ИНН+название), сумма, № документа, назначение."""
    line_no, lines = block
    m = _DATE_LINE.match(lines[0])
    if not m:
        return None
    op_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    parties = _split_parties(lines)
    if len(parties) < 2:
        return None  # шапка/подвал, а не операция

    amount = _find_amount(lines)
    if amount is None:
        return None

    # START_BLOCK_DIRECTION
    # Первая сторона — плательщик (дебет), вторая — получатель (кредит).
    # Счёт владельца во второй стороне ⇒ деньги пришли нам.
    payer, payee = parties[0], parties[1]
    is_income = owner_account in payee["accounts"]
    direction = "credit" if is_income else "debit"
    counterparty = payer if is_income else payee
    # END_BLOCK_DIRECTION

    return RawOperation(
        date=op_date,
        amount=amount,
        direction=direction,
        doc_number=_find_doc_number(lines),
        counterparty_name=counterparty["name"],
        counterparty_inn=counterparty["inn"],
        purpose_text=clean_purpose(_find_purpose(lines)),
        raw_line_no=line_no,
    )


def _split_parties(lines: list[str]) -> list[dict]:
    """Стороны идут подряд: счёт → ИНН → ОГРН → название. Новый счёт = новая сторона."""
    parties: list[dict] = []
    for ln in lines:
        acc = _ACCOUNT.search(ln)
        if acc:
            parties.append({"accounts": [acc.group(0)], "inn": None, "name": ""})
            continue
        if not parties:
            continue
        current = parties[-1]
        inn = _INN_LABELED.search(ln)
        if inn and current["inn"] is None:
            current["inn"] = inn.group(1)
            continue
        if re.match(r"^\s*(ОГРНИП|ОГРН)\b", ln):
            continue
        if not current["name"] and _ORG_HINT.search(ln) and not _BIK_LINE.match(ln):
            current["name"] = ln.strip()
    return parties


def _find_amount(lines: list[str]) -> Decimal | None:
    for ln in lines:
        m = _MONEY.match(ln)
        if m:
            return Decimal(m.group(1).replace(" ", "").replace(" ", "").replace(",", "."))
    return None


def _find_doc_number(lines: list[str]) -> str:
    """№ документа — короткое число сразу после суммы."""
    seen_amount = False
    for ln in lines:
        if _MONEY.match(ln):
            seen_amount = True
            continue
        if seen_amount:
            m = _DOC_NUMBER.match(ln)
            if m:
                return m.group(1)
    return ""


def _find_purpose(lines: list[str]) -> str:
    """Назначение — хвост блока после строки БИК (она разделяет реквизиты и текст платежа)."""
    idx = next((i for i, ln in enumerate(lines) if _BIK_LINE.match(ln)), None)
    if idx is None:
        return ""
    tail = lines[idx + 1 :]
    # первая строка после БИК — продолжение названия банка, назначение идёт следом;
    # берём всё и отсекаем банковскую строку по признаку «//» или «Банка России»
    text = " ".join(t.strip() for t in tail if t.strip())
    text = re.sub(r"^[^.]*?(//|Банка\s+России)[^.]*?\s", "", text)
    return text


# START_CONTRACT: clean_purpose
#   PURPOSE: Снять налоговый хвост и колонтитулы — иначе они ломают классификацию.
#   INPUTS: { text: str }
#   OUTPUTS: { str }
#   SIDE_EFFECTS: none
# END_CONTRACT: clean_purpose
def clean_purpose(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = _PAGE_MARK.sub("", text).strip()
    while True:
        stripped = _TAX_TAIL.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    return text.strip(" .,")


def _build_owner(account: str, lines: list[str], operations: list[RawOperation]) -> StatementOwner:
    """ИНН владельца в шапке отсутствует, но он есть в каждой операции — берём самый частый."""
    all_inns = _INN_LABELED.findall("\n".join(lines))
    if not all_inns:
        raise StatementFormatError("в выписке не найдено ни одного ИНН")
    owner_inn = Counter(all_inns).most_common(1)[0][0]

    bank_match = re.search(r'(АО|ООО|ПАО)\s+"[^"]+"', "\n".join(lines[:20]))
    bank_name = bank_match.group(0) if bank_match else ""
    bank_inn = _find_bank_inn(bank_name, operations)
    return StatementOwner(account=account, inn=owner_inn, bank_name=bank_name, bank_inn=bank_inn)


def _find_bank_inn(bank_name: str, operations: list[RawOperation]) -> str | None:
    """ИНН обслуживающего банка: он контрагент в комиссиях и процентах по депозиту."""
    if not bank_name:
        return None
    key = re.sub(r"[^а-яa-z]", "", bank_name.lower())
    for op in operations:
        name = re.sub(r"[^а-яa-z]", "", op.counterparty_name.lower())
        if op.counterparty_inn and key and key in name:
            return op.counterparty_inn
    return None


def _verify_against_footer(raw_text: str, operations: list[RawOperation]) -> None:
    """Контрольная сумма подвала («Количество операций 21 26 47») — выписка проверяет парсер.
    Расхождение значит, что операции потеряны или направление определено неверно."""
    m = _FOOTER.search(raw_text)
    if not m:
        logger.warning("[Parser][_verify_against_footer][BLOCK_SELF_CHECK] подвал не найден")
        return
    exp_debit, exp_credit, exp_total = (int(m.group(i)) for i in (1, 2, 3))
    got_debit = sum(1 for o in operations if o.direction == "debit")
    got_credit = sum(1 for o in operations if o.direction == "credit")
    if (got_debit, got_credit, got_debit + got_credit) != (exp_debit, exp_credit, exp_total):
        raise StatementFormatError(
            f"контрольная сумма выписки не сошлась: подвал {exp_debit}/{exp_credit}/{exp_total}, "
            f"разобрано {got_debit}/{got_credit}/{len(operations)}"
        )
    logger.info(
        "[Parser][_verify_against_footer][BLOCK_SELF_CHECK] контрольная сумма сошлась",
        extra={"debit": got_debit, "credit": got_credit},
    )
