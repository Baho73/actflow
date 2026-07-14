# Деплой ActFlow

ТЗ требует ссылку на живой деплой. Ниже три рабочих варианта — выбрать один.

## Вариант 1. Свой Linux-сервер (нужен публичный IP или домен)

```bash
# с локальной машины
scp -r . user@ВАШ_СЕРВЕР:/opt/actflow
ssh user@ВАШ_СЕРВЕР 'cd /opt/actflow && bash deploy/deploy.sh'
```

Дашборд поднимется на `http://ВАШ_СЕРВЕР:8090`. Порт меняется переменной `ACTFLOW_PORT`.

Для домена и HTTPS — поставить перед сервисом Caddy/nginx с сертификатом Let's Encrypt:

```caddy
actflow.example.com {
    reverse_proxy localhost:8090
}
```

## Вариант 2. Cloudflare Tunnel (публичная ссылка без белого IP и проброса портов)

Подходит, если сервер за NAT или это домашняя машина.

```bash
docker compose up -d --build                       # сервис на localhost:8090
cloudflared tunnel --url http://localhost:8090     # выдаст публичный https-адрес
```

Ссылка вида `https://<random>.trycloudflare.com` открывается заказчиком сразу.
Для постоянного адреса — именованный туннель в аккаунте Cloudflare.

## Вариант 3. Render / Railway (бесплатный тариф)

Проект уже упакован в `docker-compose.yml`; на таких платформах разворачиваются
два сервиса (backend + web) и managed PostgreSQL, `DATABASE_URL` подставляется платформой.

---

## Проверка после деплоя (обязательно)

Не считать «задеплоено» по факту успешной команды:

```bash
curl https://ВАШ_АДРЕС/api/health                  # {"status":"ok"}
curl https://ВАШ_АДРЕС/api/payments?limit=1        # total > 0 после импорта выписки
```

И открыть дашборд глазами: должны быть показатели, таблица оплат и статусы актов.
