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

- Разработка: Windows 11, Docker Desktop. Локально: `docker compose up -d --build` → http://localhost:8090
- Стек: FastAPI + PostgreSQL, React SPA, nginx (единый origin), docker compose.
  Выбор стека обоснован в README (ТЗ предпочитает Laravel+Vue, но прямо разрешает другой с объяснением).
- Python: UTF-8 явно, `Decimal` для денег, никакого float.

### Прод-сервер (деплой выполнен)

- **Публичная ссылка: http://46.149.69.151:8090**
- SSH: `ssh foxear-vps` (хост 46.149.69.151, root; ключ `D:/Python/Fox_Ear/.ssh/deploy_key`, запись уже в `~/.ssh/config`).
- Путь на сервере: `/opt/actflow`. Деплой: `bash deploy/deploy.sh` (см. `deploy/README.md`).
- **ВНИМАНИЕ: сервер боевой** — на нём живут foxear (Caddy на 80/443, api, bot, postgres, redis, minio, воркеры)
  и defectmaster. ActFlow намеренно занял свободный порт 8090 и НЕ трогает Caddy и чужие сервисы.
- Известная чужая проблема (не наша): контейнер `defectmaster-minio` в вечном рестарте (6213 перезапусков
  с 20.06) — не может писать в свой `/data` (права). К ActFlow отношения не имеет.
- HTTPS-домен не подключён: wildcard `*.foxear.ru` отсутствует, нужна A-запись `actflow.foxear.ru → 46.149.69.151`,
  после чего добавить в Caddyfile `reverse_proxy localhost:8090`.

### Обновление кода на сервере

```
git archive --format=tar.gz -o %TEMP%\actflow.tar.gz HEAD
scp %TEMP%\actflow.tar.gz foxear-vps:/tmp/actflow.tar.gz
ssh foxear-vps 'tar xzf /tmp/actflow.tar.gz -C /opt/actflow && cd /opt/actflow && ACTFLOW_PORT=8090 bash deploy/deploy.sh'
```
Код попадает в образ через `COPY`, поэтому обновление всегда с `--build` (это внутри deploy.sh).

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
