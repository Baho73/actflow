# FILE: backend/app/domain/act_status.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Вычислить статус закрывающего документа. Статус — производная величина, НЕ хранится.
#   SCOPE: Матрица статусов + порог SLA. Чистая функция, «сегодня» приходит извне.
#   LAYER: DOMAIN
#   DEPENDS: none
#   LINKS: M-ACTSTATUS, V-M-ACTSTATUS, VF-004
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   compute_act_status - (флаги, дата оплаты, today, sla_days) -> ActStatus
#   ActStatus - not_sent | awaiting_signature | closed | needs_attention
#   DEFAULT_SLA_DAYS - порог «требует внимания» по умолчанию
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-ACTSTATUS contract]
# END_CHANGE_SUMMARY
#
# Статус не хранится в БД: он производная от флагов и возраста оплаты. Хранить его значило бы
# держать две версии правды и ловить рассинхрон. «Сегодня» инжектируется — иначе тесты
# недетерминированы, а часовой пояс сервера двигает границу просрочки.

from datetime import date
from enum import StrEnum

DEFAULT_SLA_DAYS = 14


class ActStatus(StrEnum):
    NOT_SENT = "not_sent"                    # акт не отправлен, срок ещё есть
    AWAITING_SIGNATURE = "awaiting_signature"  # отправлен, ждём подпись
    CLOSED = "closed"                        # подписан — документооборот закрыт
    NEEDS_ATTENTION = "needs_attention"      # срок вышел, а акт не закрыт


# START_CONTRACT: compute_act_status
#   PURPOSE: Матрица статусов. closed окончателен; просрочка приоритетнее любого незакрытого.
#   INPUTS: { is_sent: bool, is_signed: bool, payment_date: date, today: date, sla_days: int }
#   OUTPUTS: { ActStatus }
#   SIDE_EFFECTS: none
#   ERRORS: ValueError — подписан, но не отправлен (недопустимое состояние)
# END_CONTRACT: compute_act_status
def compute_act_status(
    *,
    is_sent: bool,
    is_signed: bool,
    payment_date: date,
    today: date,
    sla_days: int = DEFAULT_SLA_DAYS,
) -> ActStatus:
    if is_signed and not is_sent:
        raise ValueError("акт не может быть подписан, не будучи отправленным")

    # closed окончателен: просрочка его не отменяет — деньги закрыты документом
    if is_signed:
        return ActStatus.CLOSED

    age = (today - payment_date).days  # может быть отрицательным (оплата будущей датой)
    overdue = age > sla_days  # строго больше: ровно sla_days — ещё в срок

    if overdue:
        return ActStatus.NEEDS_ATTENTION
    return ActStatus.AWAITING_SIGNATURE if is_sent else ActStatus.NOT_SENT
