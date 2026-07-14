# FILE: backend/app/schemas.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Pydantic-схемы запросов и ответов API.
#   SCOPE: Форма данных на границе. Никаких бизнес-правил.
#   LAYER: API
#   DEPENDS: none
#   LINKS: M-API
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   ImportReportOut / SkippedGroupOut - отчёт импорта (принято / уже было / отсеяно)
#   PaymentOut / PaymentPage - оплаты
#   ActPatch / BulkActIn / ProjectPatch - команды менеджера
#   TotalsOut / ProjectSummaryOut / DashboardOut - сводка
#   ProjectOut / ClientOut - справочники
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per M-API contract]
# END_CHANGE_SUMMARY

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SkippedGroupOut(BaseModel):
    code: str
    text: str
    count: int
    amount: Decimal


class ImportReportOut(BaseModel):
    imported: int
    already_known: int
    skipped: list[SkippedGroupOut]
    created_projects: int
    unbound: int


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    payment_date: date
    amount: Decimal
    client_id: int
    client_name: str
    client_inn: str
    project_id: int | None
    project_name: str | None
    binding_method: str          # by_contract | by_client_service | manual | unbound
    conflict_reason: str | None  # видимая причина, почему не привязали
    stage_mismatch: bool
    service_stages: list[str]
    invoice_numbers: list[str]
    contract_number: str | None
    doc_number: str
    purpose_text: str
    is_sent: bool
    sent_at: date | None
    is_signed: bool
    signed_at: date | None
    manager_comment: str
    act_status: str              # вычислен доменом, в БД не хранится


class PaymentPage(BaseModel):
    items: list[PaymentOut]
    total: int


class ActPatch(BaseModel):
    is_sent: bool | None = None
    is_signed: bool | None = None
    manager_comment: str | None = Field(default=None, max_length=2000)


class BulkActIn(BaseModel):
    payment_ids: list[int] = Field(min_length=1, max_length=1000)
    is_sent: bool | None = None
    is_signed: bool | None = None


class ProjectPatch(BaseModel):
    project_id: int | None  # None = снять привязку


class ProjectRename(BaseModel):
    name: str = Field(min_length=1, max_length=300)


class TotalsOut(BaseModel):
    total_amount: Decimal
    payments_count: int
    projects_count: int
    closed_amount: Decimal
    open_amount: Decimal
    needs_attention_amount: Decimal
    closed_count: int
    not_sent_count: int
    awaiting_count: int
    needs_attention_count: int


class ProjectSummaryOut(BaseModel):
    project_id: int | None
    project_name: str
    payments_count: int
    total: Decimal
    sent_count: int
    signed_count: int
    closed_ratio: Decimal | None


class DashboardOut(BaseModel):
    totals: TotalsOut
    by_project: list[ProjectSummaryOut]


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    client_id: int
    client_name: str
    contract_number: str | None
    service_stage: str | None
    auto_created: bool


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    inn: str
