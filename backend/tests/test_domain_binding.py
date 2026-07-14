# FILE: backend/tests/test_domain_binding.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Проверка правил привязки к проекту (V-M-BINDING, VF-003).
#   SCOPE: Все четыре способа + отказ угадывать + курица-яйцо пустого справочника.
#   LAYER: DOMAIN
#   DEPENDS: M-BINDING
#   LINKS: V-M-BINDING
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   PROJECTS - справочник-фикстура
#   test_* - правила привязки, конфликты, черновик
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per module contract]
# END_CHANGE_SUMMARY

from app.domain.binding import BindingMethod, ProjectRef, bind_payment

CLIENT_A = "7710000001"
CLIENT_B = "7720000002"

PROJECTS = [
    ProjectRef(1, "Сайт клиента А", CLIENT_A, "214", "Разработка сайта"),
    ProjectRef(2, "SEO клиента А", CLIENT_A, None, "SEO"),
    ProjectRef(3, "Сайт клиента Б", CLIENT_B, "95", "Разработка сайта"),
]


def test_bind_by_contract():
    b = bind_payment(CLIENT_A, "Клиент А", "214", ["Разработка сайта"], PROJECTS)
    assert b.project_id == 1
    assert b.method is BindingMethod.BY_CONTRACT
    assert not b.stage_mismatch


def test_contract_of_another_client_is_conflict_not_silent_bind():
    """Договор № 95 принадлежит клиенту Б. Привязать его платёж клиента А — худшая ошибка."""
    b = bind_payment(CLIENT_A, "Клиент А", "95", ["Разработка сайта"], PROJECTS)
    assert b.project_id is None
    assert b.method is BindingMethod.UNBOUND
    assert "другим клиентом" in b.conflict_reason


def test_contract_wins_over_service_but_mismatch_is_visible():
    """Договор сильнее услуги, но расхождение показываем флагом, а не перезаписью."""
    b = bind_payment(CLIENT_A, "Клиент А", "214", ["SEO"], PROJECTS)
    assert b.project_id == 1
    assert b.method is BindingMethod.BY_CONTRACT
    assert b.stage_mismatch is True


def test_bind_by_client_and_service():
    b = bind_payment(CLIENT_A, "Клиент А", None, ["SEO"], PROJECTS)
    assert b.project_id == 2
    assert b.method is BindingMethod.BY_CLIENT_SERVICE


def test_several_candidates_do_not_guess():
    projects = PROJECTS + [ProjectRef(4, "SEO клиента А (второй)", CLIENT_A, None, "SEO")]
    b = bind_payment(CLIENT_A, "Клиент А", None, ["SEO"], projects)
    assert b.method is BindingMethod.UNBOUND
    assert "несколько проектов" in b.conflict_reason


def test_two_services_do_not_guess():
    """Реальный случай выписки: «сопровождение сайта и услуги наполнения» — две услуги."""
    b = bind_payment(CLIENT_A, "Клиент А", None, ["Сопровождение сайта", "Наполнение сайта"], PROJECTS)
    assert b.method is BindingMethod.UNBOUND
    assert "несколько услуг" in b.conflict_reason


def test_no_requisites_is_unbound():
    b = bind_payment(CLIENT_A, "Клиент А", None, [], PROJECTS)
    assert b.method is BindingMethod.UNBOUND
    assert b.conflict_reason


def test_empty_catalog_creates_draft_project():
    """КУРИЦА-ЯЙЦО: при первом импорте справочник пуст. Без черновика дашборд был бы пустым."""
    b = bind_payment(CLIENT_A, "ООО «Ромашка»", "777", ["Дизайн"], projects=[])
    assert b.method is BindingMethod.BY_CONTRACT
    assert b.draft_project is not None
    assert b.draft_project.contract_number == "777"
    assert "договор № 777" in b.draft_project.name
    assert b.draft_project.service_stage == "Дизайн"


def test_draft_without_single_service_has_no_stage():
    b = bind_payment(CLIENT_A, "ООО «Ромашка»", "777", ["Дизайн", "SEO"], projects=[])
    assert b.draft_project.service_stage is None
