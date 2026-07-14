# FILE: backend/app/domain/binding.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Связать оплату с проектом. Проекта в выписке НЕТ — он выводится по видимому правилу.
#   SCOPE: Правила привязки + автосоздание проекта-черновика. Ничего не угадывает молча.
#   LAYER: DOMAIN
#   DEPENDS: M-EXTRACT
#   LINKS: M-BINDING, V-M-BINDING, VF-003
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   bind_payment - реквизиты + справочник -> Binding(project?, method, conflict?, draft?)
#   BindingMethod - способ привязки (хранится у оплаты и виден пользователю)
#   Binding - результат привязки
#   ProjectRef - проект из справочника (клиент + договор + услуга)
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-BINDING contract]
# END_CHANGE_SUMMARY
#
# ЦЕНТР АРХИТЕКТУРЫ. Проект — не поле платежа, а выводимая сущность, поэтому правило вывода
# обязано быть ВИДИМЫМ: пользователь всегда знает, почему оплата попала в этот проект.
# Система никогда не угадывает: при неоднозначности — «требует привязки».

import logging
from enum import StrEnum
from typing import NamedTuple

logger = logging.getLogger(__name__)


class BindingMethod(StrEnum):
    BY_CONTRACT = "by_contract"           # совпали номер договора И клиент
    BY_CLIENT_SERVICE = "by_client_service"  # совпали клиент И услуга, кандидат единственный
    MANUAL = "manual"                     # менеджер привязал руками
    UNBOUND = "unbound"                   # требует привязки


class ProjectRef(NamedTuple):
    id: int
    name: str
    client_inn: str
    contract_number: str | None
    service_stage: str | None


class DraftProject(NamedTuple):
    """Проект-черновик: создаётся автоматически по договору, помечен и переименовывается."""
    name: str
    client_inn: str
    contract_number: str
    service_stage: str | None


class Binding(NamedTuple):
    project_id: int | None
    method: BindingMethod
    conflict_reason: str | None = None  # видимая причина, почему не привязали
    stage_mismatch: bool = False        # привязали по договору, но услуга не совпала
    draft_project: DraftProject | None = None  # предложение создать проект-черновик


# START_CONTRACT: bind_payment
#   PURPOSE: Привязать оплату к проекту по видимому правилу; неоднозначное → unbound.
#   INPUTS: { client_inn, client_name, contract_number?, service_stages[], projects[] }
#   OUTPUTS: { Binding }
#   SIDE_EFFECTS: none (создание черновика — решение вызывающего слоя)
#   LINKS: правила и приоритеты зафиксированы контрактом M-BINDING
# END_CONTRACT: bind_payment
def bind_payment(
    client_inn: str,
    client_name: str,
    contract_number: str | None,
    service_stages: list[str],
    projects: list[ProjectRef],
) -> Binding:
    # START_BLOCK_BIND_RULES

    # 1. По договору — но ТОЛЬКО при совпадении клиента.
    #    Номера договоров двух-трёхзначные (№ 61, № 95, № 214), коллизия между клиентами
    #    неизбежна. Тихая привязка чужого договора — худшая из возможных ошибок.
    if contract_number:
        same_contract = [p for p in projects if p.contract_number == contract_number]
        mine = [p for p in same_contract if p.client_inn == client_inn]
        if mine:
            project = mine[0]
            mismatch = bool(
                project.service_stage
                and service_stages
                and project.service_stage not in service_stages
            )
            return Binding(project.id, BindingMethod.BY_CONTRACT, stage_mismatch=mismatch)
        if same_contract:
            # договор есть, но у другого клиента — конфликт показываем, не привязываем
            return Binding(
                None,
                BindingMethod.UNBOUND,
                conflict_reason=f"договор № {contract_number} закреплён за другим клиентом",
            )
        # договора нет в справочнике — предлагаем черновик (иначе первый импорт даст пустой дашборд)
        return Binding(
            None,
            BindingMethod.BY_CONTRACT,
            draft_project=DraftProject(
                name=f"{client_name} / договор № {contract_number}",
                client_inn=client_inn,
                contract_number=contract_number,
                service_stage=service_stages[0] if len(service_stages) == 1 else None,
            ),
        )

    # 2. По клиенту и услуге — только если кандидат ЕДИНСТВЕННЫЙ и услуга одна.
    if len(service_stages) == 1:
        candidates = [
            p for p in projects
            if p.client_inn == client_inn and p.service_stage == service_stages[0]
        ]
        if len(candidates) == 1:
            return Binding(candidates[0].id, BindingMethod.BY_CLIENT_SERVICE)
        if len(candidates) > 1:
            return Binding(
                None,
                BindingMethod.UNBOUND,
                conflict_reason="у клиента несколько проектов с этой услугой — нужен выбор менеджера",
            )
    elif len(service_stages) > 1:
        return Binding(
            None,
            BindingMethod.UNBOUND,
            conflict_reason="в платеже несколько услуг — нужен выбор менеджера",
        )

    # 3. Данных не хватило — честно говорим об этом.
    logger.debug(
        "[Binding][bind_payment][BLOCK_BIND_RULES] unbound",
        extra={"client_inn": client_inn, "has_contract": bool(contract_number)},
    )
    return Binding(
        None,
        BindingMethod.UNBOUND,
        conflict_reason="в платеже нет ни договора, ни однозначной услуги",
    )
    # END_BLOCK_BIND_RULES
