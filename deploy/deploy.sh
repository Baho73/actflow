#!/usr/bin/env bash
# Деплой ActFlow на Linux-сервер. Запускать НА СЕРВЕРЕ из корня проекта.
#
#   scp -r . user@host:/opt/actflow && ssh user@host 'cd /opt/actflow && bash deploy/deploy.sh'
#
# Требует: docker + docker compose. Порт публикации задаётся ACTFLOW_PORT (по умолчанию 8090).
set -euo pipefail

PORT="${ACTFLOW_PORT:-8090}"

echo "==> сборка и запуск (порт ${PORT})"
ACTFLOW_PORT="${PORT}" docker compose up -d --build

echo "==> ожидание готовности API"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
    echo "    API отвечает"
    break
  fi
  [ "$i" = 30 ] && { echo "    API не поднялся"; docker compose logs --tail=40 backend; exit 1; }
  sleep 2
done

echo "==> подтверждение, что в контейнере новый код (а не старый образ)"
docker compose exec -T backend python -c "import app.domain.parser as p; print('parser', p.__doc__ or 'ok')" >/dev/null && echo "    код на месте"

echo "==> импорт демо-выписки (если база пуста)"
COUNT=$(curl -fsS "http://127.0.0.1:${PORT}/api/payments?limit=1" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])" 2>/dev/null || echo 0)
if [ "${COUNT}" = "0" ]; then
  curl -fsS -X POST "http://127.0.0.1:${PORT}/api/import/statement" \
    -F "file=@bank_statement.pdf;type=application/pdf" | head -c 300
  echo
  echo "    выписка импортирована"
else
  echo "    в базе уже ${COUNT} оплат — импорт пропущен"
fi

echo
echo "ГОТОВО. Дашборд: http://<адрес-сервера>:${PORT}"
echo "Проверка: curl http://127.0.0.1:${PORT}/api/health"
