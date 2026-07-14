# GRACE Framework - Project Engineering Protocol

## Keywords
actflow, payments, projects, legal-entity, acts, closing-documents, bank-statement, pdf-parsing, dashboard, fastapi, react, postgresql

## Annotation
ActFlow — мини-система учёта оплат, проектов и закрывающих документов для digital-агентства: банковская выписка (PDF) → распознанные оплаты клиентов → привязка к проектам и этапам → контроль статусов актов → дашборд со сводкой и фильтрами. Стек: FastAPI + PostgreSQL, React SPA, nginx, docker compose.

## Core Principles

### 1. Never Write Code Without a Contract
Before generating or editing any module, create or update its MODULE_CONTRACT with PURPOSE, SCOPE, INPUTS, and OUTPUTS. The contract is the source of truth.

### 2. Semantic Markup Is Load-Bearing Structure
Markers `// START_BLOCK_<NAME>` / `// END_BLOCK_<NAME>` are navigation anchors: uniquely named, paired, proportionally sized.

### 3. Knowledge Graph Is Always Current
`docs/knowledge-graph.xml` is the project map. Adding/moving/renaming a module updates the graph in the same commit.

### 4. Verification Is a First-Class Artifact
`docs/verification-plan.xml` is part of the architecture. Logs are evidence. Tests are executable contracts.

### 5. Top-Down Synthesis
`RequirementsAnalysis -> TechnologyStack -> DevelopmentPlan -> VerificationPlan -> Code + Tests`

### 6. Governed Autonomy
Freedom in HOW to implement, not in WHAT to build.

## Layer Discipline (ключевое требование ТЗ)

Заказчик прямо оценивает «умеете ли вы отделять данные, бизнес-логику и отображение». Слои:

- **DATA** (`app/models.py`, `app/db.py`) — только хранение. Никакой бизнес-логики.
- **DOMAIN** (`app/domain/`) — чистая бизнес-логика без БД и HTTP: парсер выписки, классификация операций, привязка к проекту, статусы актов, агрегация. Тестируется без базы.
- **API** (`app/routers/`, `app/schemas.py`) — транспорт: валидация запроса, вызов домена, форма ответа. Без бизнес-правил.
- **UI** (`frontend/`) — только отображение и команды. Никаких расчётов статусов и сумм на клиенте.

Нарушение слоя (например, расчёт статуса акта во фронте или SQL в домене) — дефект ревью.

## Semantic Markup Reference

### Module Level
```
# FILE: path/to/file.ext
# VERSION: 1.0.0
# START_MODULE_CONTRACT
#   PURPOSE: [What this module does - one sentence]
#   SCOPE: [What operations are included]
#   LAYER: [DATA | DOMAIN | API | UI]
#   DEPENDS: [List of module dependencies]
#   LINKS: [Knowledge graph references]
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   exportedSymbol - one-line description
# END_MODULE_MAP
#
# START_CHANGE_SUMMARY
#   LAST_CHANGE: [v1.0.0 - What changed and why]
# END_CHANGE_SUMMARY
```

### Function Level
```
# START_CONTRACT: functionName
#   PURPOSE: [What it does]
#   INPUTS: { paramName: Type - description }
#   OUTPUTS: { ReturnType - description }
#   SIDE_EFFECTS: [External state changes or "none"]
# END_CONTRACT: functionName
```

### Block Level
```
# START_BLOCK_VALIDATE_INPUT
# ... code ...
# END_BLOCK_VALIDATE_INPUT
```

## Logging Convention
```
logger.info("[Module][function][BLOCK_NAME] message", extra={"key": value})
```
Не логировать: полные реквизиты счетов, персональные данные контрагентов сверх ИНН/названия.

## File Structure
```
docs/                  requirements, technology, development-plan, knowledge-graph, verification-plan
backend/app/domain/    чистая бизнес-логика (парсер, классификация, привязка, статусы, агрегаты)
backend/app/routers/   HTTP
backend/tests/         pytest
frontend/src/          React SPA
bank_statement.pdf     исходная выписка (мок-данные из ТЗ)
```

## Documentation Artifacts - Unique Tag Convention

В `docs/*.xml` повторяющиеся сущности используют уникальный ID как имя тега:
`<M-PARSER NAME="..." TYPE="...">`, `<UC-001>`, `<Phase-1>`, `<V-M-PARSER>`, `<DF-IMPORT>`.

## Rules for Modifications

1. Read MODULE_CONTRACT before editing.
2. Update MODULE_MAP after changing exports.
3. Update `docs/knowledge-graph.xml` after adding/removing modules.
4. Update `docs/verification-plan.xml` after changing tests/commands/markers.
5. Bug fix → CHANGE_SUMMARY + регрессионный тест.
6. Не удалять семантические якоря.

## Scope Completion Rule

Никогда не отчитываться «готово» без успешного выхода обоих:
- `pytest` в `backend/`
- сборка фронта `npm run build`

«Код выглядит правильно» — не доказательство. «Тесты прошли» — доказательство.
