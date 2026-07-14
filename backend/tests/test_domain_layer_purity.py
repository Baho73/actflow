# FILE: backend/tests/test_domain_layer_purity.py
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: Доказать, что бизнес-логика отделена от данных и транспорта (VF-001).
#   SCOPE: Домен не импортирует ORM, драйвер БД и веб-фреймворк — проверяется по исходникам.
#   LAYER: DOMAIN
#   DEPENDS: none
#   LINKS: VF-001, AGENTS.md (LAYER discipline)
#   ROLE: TEST
#   MAP_MODE: LOCALS
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   test_domain_does_not_import_infrastructure - структурный тест чистоты слоя
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - Initial implementation per module contract]
# END_CHANGE_SUMMARY
#
# Заказчик прямо оценивает: «умеете ли вы отделять данные, бизнес-логику и отображение».
# Это утверждение легко заявить в README и невозможно проверить глазами при росте кода —
# поэтому оно закреплено тестом.

import ast
from pathlib import Path

import pytest

DOMAIN = Path(__file__).resolve().parents[1] / "app" / "domain"

FORBIDDEN = {
    "sqlalchemy": "ORM в бизнес-логике",
    "psycopg": "драйвер БД в бизнес-логике",
    "fastapi": "веб-фреймворк в бизнес-логике",
    "starlette": "веб-фреймворк в бизнес-логике",
    "app.models": "модели БД в бизнес-логике",
    "app.db": "сессии БД в бизнес-логике",
    "app.routers": "транспорт в бизнес-логике",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", sorted(DOMAIN.glob("*.py")), ids=lambda p: p.name)
def test_domain_does_not_import_infrastructure(module: Path):
    for imported in _imports(module):
        for forbidden, why in FORBIDDEN.items():
            assert not imported.startswith(forbidden), (
                f"{module.name} импортирует {imported}: {why}. "
                "Домен обязан оставаться переносимым на любой стек."
            )


def test_domain_modules_exist():
    """Домен непустой — иначе тест чистоты проходит формально."""
    modules = {p.name for p in DOMAIN.glob("*.py")} - {"__init__.py"}
    assert modules >= {"parser.py", "classify.py", "extract.py", "binding.py", "act_status.py", "summary.py"}
