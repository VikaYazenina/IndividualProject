# Content Aggregator

Веб-сервис для персональной агрегации полезного контента, собирающий все новые материалы из выбранных источников в структурированном виде.

## Структура репозитория

```
content_aggregator/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI-приложение: API + веб-страницы + запуск планировщика
│   ├── config.py            # настройки из .env
│   ├── database.py          # подключение к БД, SessionLocal, init_db()
│   ├── deps.py               # FastAPI-зависимость: сессия БД на запрос
│   ├── models.py             # SQLAlchemy-модели: Source, Item
│   ├── schemas.py            # Pydantic-схемы для API
│   ├── parser.py             # сбор новых материалов: RSS (feedparser) + HTML (BeautifulSoup)
│   ├── scheduler.py          # APScheduler — регулярный обход источников + рассылка
│   ├── mailer.py             # рендер и отправка email-дайджеста (Jinja2 + smtplib)
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── sources.py        # REST API: CRUD источников, ручной запуск парсинга
│   │   └── items.py          # REST API: список/поиск/фильтры, статусы, экспорт, статистика
│   ├── templates/
│   │   ├── base.html
│   │   ├── sources.html      # страница управления источниками
│   │   ├── archive.html      # страница архива с поиском и фильтрами
│   │   ├── stats.html        # страница аналитики
│   │   └── email/digest.html # шаблон письма-дайджеста
│   └── static/
│       └── style.css
├── tests/
│   ├── __init__.py
│   ├── sample_feed.xml       # тестовая RSS-лента
│   ├── sample_page.html      # тестовая HTML-страница (для HTML-парсера)
│   ├── test_parser.py        # тесты парсера: RSS + HTML, без внешней сети
│   └── test_api.py           # тесты REST API и веб-страниц (FastAPI TestClient)
├── scripts/
│   └── demo.py                # ручная демонстрация пайплайна целиком
├── docs/
│   └── proposal.md            # исходная заявка на проект
├── .env.example
├── .gitignore
├── Procfile                   # команда запуска для хостинга (Render/Railway/Heroku-подобные)
├── requirements.txt
└── README.md
```

## Быстрый старт

```bash
git clone https://github.com/<ваш-аккаунт>/content_aggregator.git
cd content_aggregator

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env            # при необходимости укажите SMTP и MAIL_TO

uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

Откройте:
- `http://127.0.0.1:8000/sources` — добавить источники
- `http://127.0.0.1:8000/archive` — архив материалов, поиск и фильтры
- `http://127.0.0.1:8000/stats` — аналитика
- `http://127.0.0.1:8000/docs` — автоматическая документация REST API (Swagger UI)

## Тесты и демо

```bash
pytest                # 9 тестов: парсер (RSS + HTML) и API
python -m scripts.demo # прогон пайплайна на тестовых данных, без сервера
```

## Как добавить источник (программно, через API)

```bash
curl -X POST http://127.0.0.1:8000/api/sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Хабр — спортивная аналитика",
    "url": "https://habr.com/ru/rss/hub/sport/all/",
    "type": "rss",
    "category": "tech"
  }'
```

Для источника без RSS (`"type": "html"`) дополнительно укажите CSS-селекторы:
`html_item_selector` (блок одного материала), `html_title_selector`,
`html_link_selector` — их же можно ввести в форме на странице `/sources`.

## Email-рассылка

Если в `.env` не заданы `SMTP_HOST`/`MAIL_TO`, дайджест не отправляется, а
печатается в консоль — удобно для разработки без реального почтового сервера.
Как только SMTP настроен, дайджест уходит на `MAIL_TO` автоматически по
расписанию (`PARSE_INTERVAL_HOURS`, по умолчанию раз в 24 часа) и включает
как новые материалы, так и отложенные (`is_deferred=True`).

## Деплой

Любой хостинг с поддержкой фоновых Python-процессов (Render, Railway, обычный
VPS). Команда запуска — в `Procfile`:

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

На проде поменяйте `DATABASE_URL` в `.env` с SQLite на, например, Postgres —
остальной код не изменится, вся работа с БД идёт через SQLAlchemy ORM.

