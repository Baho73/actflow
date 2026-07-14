# FILE: backend/tests/test_api.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: API-тесты (V-M-API): импорт реальной выписки, идемпотентность, фильтры, акты, сводка.
#   SCOPE: Сквозной сценарий менеджера на настоящих данных.
#   LAYER: API
#   DEPENDS: M-API
#   LINKS: V-M-API, VF-002, VF-005, VF-006
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   imported - фикстура: выписка загружена через HTTP
#   test_* - отчёт импорта, идемпотентность, статусы, фильтры, сводка, экспорт
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per module contract]
# END_CHANGE_SUMMARY

from decimal import Decimal
from pathlib import Path

import pytest

STATEMENT = (Path(__file__).resolve().parents[2] / "bank_statement.pdf").read_bytes()

AS_OF = "2026-08-14"  # дата выписки: на неё статусы разнообразны, а не сплошь просрочены
EXPECTED_PAYMENTS = 24
EXPECTED_AMOUNT = Decimal("1405820.00")


def upload(client):
    return client.post(
        "/api/import/statement",
        files={"file": ("bank_statement.pdf", STATEMENT, "application/pdf")},
    )


@pytest.fixture()
def imported(client):
    r = upload(client)
    assert r.status_code == 200, r.text
    return client, r.json()


def test_import_report_matches_reference(imported):
    """Эталон выписки: ровно 24 оплаты клиентов; всё остальное отсеяно с причинами."""
    _, report = imported
    assert report["imported"] == EXPECTED_PAYMENTS
    assert report["already_known"] == 0
    # посторонние операции сгруппированы по осмысленным причинам, а не свалены в «прочее»
    codes = {g["code"] for g in report["skipped"]}
    assert {"tax", "own_transfer", "salary", "contractor_payment"} <= codes
    assert sum(g["count"] for g in report["skipped"]) == 47 - EXPECTED_PAYMENTS


def test_import_creates_draft_projects_so_dashboard_is_not_empty(imported):
    """КУРИЦА-ЯЙЦО: при первом импорте справочник пуст. Черновики спасают демо."""
    client, report = imported
    assert report["created_projects"] > 0
    projects = client.get("/api/projects").json()
    assert projects
    assert any(p["auto_created"] for p in projects)


def test_import_is_idempotent(imported):
    """Повторная загрузка той же выписки не двоит оплаты."""
    client, _ = imported
    second = upload(client).json()
    assert second["imported"] == 0
    assert second["already_known"] == EXPECTED_PAYMENTS
    page = client.get(f"/api/payments?as_of={AS_OF}&limit=500").json()
    assert page["total"] == EXPECTED_PAYMENTS


def test_summary_totals_match_reference(imported):
    client, _ = imported
    s = client.get(f"/api/summary?as_of={AS_OF}").json()
    t = s["totals"]
    assert t["payments_count"] == EXPECTED_PAYMENTS
    assert Decimal(t["total_amount"]) == EXPECTED_AMOUNT
    # инварианты полноты
    assert Decimal(t["closed_amount"]) + Decimal(t["open_amount"]) == Decimal(t["total_amount"])
    assert (
        t["not_sent_count"] + t["awaiting_count"] + t["needs_attention_count"] + t["closed_count"]
        == t["payments_count"]
    )


def test_by_project_sums_to_total(imported):
    client, _ = imported
    s = client.get(f"/api/summary?as_of={AS_OF}").json()
    total = Decimal(s["totals"]["total_amount"])
    assert sum(Decimal(r["total"]) for r in s["by_project"]) == total


def test_act_flags_persist_and_change_status(imported):
    client, _ = imported
    payment = client.get(f"/api/payments?as_of={AS_OF}&limit=1").json()["items"][0]
    pid = payment["id"]

    sent = client.patch(f"/api/payments/{pid}/act?as_of={AS_OF}", json={"is_sent": True}).json()
    assert sent["is_sent"] and sent["sent_at"]
    assert sent["act_status"] in ("awaiting_signature", "needs_attention")

    signed = client.patch(
        f"/api/payments/{pid}/act?as_of={AS_OF}",
        json={"is_signed": True, "manager_comment": "акт подписан клиентом"},
    ).json()
    assert signed["act_status"] == "closed"
    assert signed["manager_comment"] == "акт подписан клиентом"

    # переживает перечитывание
    again = client.get(f"/api/payments?as_of={AS_OF}&limit=500").json()["items"]
    assert next(p for p in again if p["id"] == pid)["act_status"] == "closed"


def test_signing_implies_sending(imported):
    """Недопустимое состояние «подписан, но не отправлен» не создаётся."""
    client, _ = imported
    pid = client.get(f"/api/payments?as_of={AS_OF}&limit=1").json()["items"][0]["id"]
    r = client.patch(f"/api/payments/{pid}/act?as_of={AS_OF}", json={"is_signed": True}).json()
    assert r["is_sent"] is True
    assert r["act_status"] == "closed"


def test_bulk_mark_acts(imported):
    client, _ = imported
    ids = [p["id"] for p in client.get(f"/api/payments?as_of={AS_OF}&limit=5").json()["items"]]
    r = client.post(f"/api/payments/bulk-act?as_of={AS_OF}", json={"payment_ids": ids, "is_sent": True})
    assert r.json()["updated"] == len(ids)
    items = client.get(f"/api/payments?as_of={AS_OF}&limit=500").json()["items"]
    assert all(p["is_sent"] for p in items if p["id"] in ids)


def test_manual_project_binding(imported):
    client, _ = imported
    unbound = [
        p for p in client.get(f"/api/payments?as_of={AS_OF}&limit=500").json()["items"]
        if p["project_id"] is None
    ]
    assert unbound, "в эталонной выписке есть оплаты без реквизитов — им нужна ручная привязка"
    project_id = client.get("/api/projects").json()[0]["id"]
    r = client.patch(
        f"/api/payments/{unbound[0]['id']}/project?as_of={AS_OF}", json={"project_id": project_id}
    ).json()
    assert r["project_id"] == project_id
    assert r["binding_method"] == "manual"


def test_binding_method_is_always_visible(imported):
    """Пользователь всегда видит, ПОЧЕМУ оплата оказалась в этом проекте."""
    client, _ = imported
    items = client.get(f"/api/payments?as_of={AS_OF}&limit=500").json()["items"]
    for p in items:
        assert p["binding_method"] in ("by_contract", "by_client_service", "manual", "unbound")
        if p["binding_method"] == "unbound":
            assert p["conflict_reason"], "непривязанная оплата обязана объяснить причину"


def test_filters_combine_and_summary_respects_them(imported):
    client, _ = imported
    all_items = client.get(f"/api/payments?as_of={AS_OF}&limit=500").json()["items"]
    client_id = all_items[0]["client_id"]

    filtered = client.get(f"/api/payments?as_of={AS_OF}&limit=500&client_id={client_id}").json()
    assert all(p["client_id"] == client_id for p in filtered["items"])

    # сводка под фильтром считает только отфильтрованное, а не всю базу
    s = client.get(f"/api/summary?as_of={AS_OF}&client_id={client_id}").json()
    assert s["totals"]["payments_count"] == filtered["total"]
    assert Decimal(s["totals"]["total_amount"]) == sum(Decimal(p["amount"]) for p in filtered["items"])


def test_filter_by_status_and_search(imported):
    client, _ = imported
    by_status = client.get(f"/api/payments?as_of={AS_OF}&limit=500&act_status=not_sent").json()
    assert all(p["act_status"] == "not_sent" for p in by_status["items"])

    found = client.get(f"/api/payments?as_of={AS_OF}&limit=500&search=SEO").json()
    assert found["total"] >= 1
    assert all("SEO" in p["purpose_text"] or "SEO" in p["client_name"] for p in found["items"])


def test_unbound_only_filter(imported):
    client, _ = imported
    r = client.get(f"/api/payments?as_of={AS_OF}&limit=500&unbound_only=true").json()
    assert all(p["project_id"] is None for p in r["items"])


def test_rename_draft_project_clears_auto_flag(imported):
    client, _ = imported
    draft = next(p for p in client.get("/api/projects").json() if p["auto_created"])
    r = client.patch(f"/api/projects/{draft['id']}", json={"name": "Редизайн сайта"}).json()
    assert r["name"] == "Редизайн сайта"
    assert r["auto_created"] is False


def test_export_csv_respects_filters(imported):
    client, _ = imported
    r = client.get(f"/api/export.csv?as_of={AS_OF}&act_status=not_sent")
    assert r.status_code == 200
    body = r.content.decode("utf-8")
    assert body.startswith("﻿")  # BOM: Excel открывает без плясок с кодировкой
    assert "Дата;Клиент;ИНН" in body
    rows = [ln for ln in body.splitlines() if ln.strip()]
    expected = client.get(f"/api/payments?as_of={AS_OF}&limit=500&act_status=not_sent").json()["total"]
    assert len(rows) - 1 == expected  # минус заголовок


def test_not_a_pdf_is_rejected(client):
    r = client.post("/api/import/statement", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
