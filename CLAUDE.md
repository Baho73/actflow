# ActFlow — Claude Code Project Context

<CRITICAL>
THIS PROJECT IS MANAGED BY GRACE (Graph-RAG Anchored Code Engineering).

Before editing ANY code, you MUST:

1. Read `AGENTS.md` — conventions, LAYER discipline, semantic-markup rules.
2. Read `docs/knowledge-graph.xml` — source of truth for the module graph.
3. Invoke the appropriate `grace-*` skill:
   - Bug / error → `grace-fix`
   - New feature / architectural change → `grace-plan` then `grace-execute`
   - Rename / move / split → `grace-refactor`
   - Question about the project → `grace-ask`
   - Review / audit → `grace-reviewer`

Do NOT bypass semantic markup (`START_BLOCK_*`, `MODULE_CONTRACT`, `CHANGE_SUMMARY`).
</CRITICAL>

## Project Summary

ActFlow — тестовое задание (digital-агентство): мини-система учёта оплат, проектов и закрывающих документов. Банковская выписка (PDF) → распознанные оплаты клиентов → привязка к проектам и этапам → статусы актов (не отправлен / ожидает подписи / закрыт / требует внимания) → дашборд со сводкой и фильтрами.

Исходное ТЗ: см. `docs/requirements.xml`. Мок-данные: `bank_statement.pdf` (реальная структура выписки ИП, содержит не только оплаты клиентов — см. риски в requirements).

## Ключевое требование заказчика

Оценивают **бизнес-логику и структуру данных**, а не верстку. Прямая цитата ТЗ: «умеете ли вы отделять данные, бизнес-логику и отображение». Поэтому LAYER-дисциплина (DATA / DOMAIN / API / UI) — не украшение, а предмет оценки. Домен (`app/domain/`) не знает ни про БД, ни про HTTP и тестируется отдельно.

## Keywords

actflow, payments, projects, legal-entity, acts, closing-documents, bank-statement, pdf-parsing, dashboard, fastapi, react, postgresql

## Окружение и деплой

- Разработка: Windows 11, Docker Desktop.
- Стек: FastAPI + PostgreSQL, React SPA, nginx (единый origin), docker compose.
  Выбор стека обоснован в README (ТЗ предпочитает Laravel+Vue, но прямо разрешает другой с объяснением).
- Деплой: свой Linux-сервер через docker compose, публичная ссылка (реквизиты сервера — см. ниже, заполнить перед деплоем).
- Python: UTF-8 явно, `Decimal` для денег, никакого float.

## Primary Artifacts

| File | Purpose |
|---|---|
| `AGENTS.md` | Протокол разработки, LAYER-дисциплина, разметка |
| `docs/requirements.xml` | Use cases, допущения, риски (в т.ч. «проекта в выписке нет») |
| `docs/technology.xml` | Стек, тестирование, наблюдаемость |
| `docs/development-plan.xml` | Модули, контракты, порядок реализации |
| `docs/knowledge-graph.xml` | Карта модулей и зависимостей |
| `docs/verification-plan.xml` | Тесты, маркеры, гейты |

## Working Rules

- Каждый модуль имеет MODULE_CONTRACT и объявленный LAYER.
- Домен не импортирует SQLAlchemy и FastAPI. Проверяется ревью.
- Деньги — Decimal. Статус акта — производная величина, не хранится.
- Каждое исправление бага → регрессионный тест в verification-plan.
