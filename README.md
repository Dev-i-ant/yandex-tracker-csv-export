# tracker-report

Скрипт для формирования CSV-отчёта по задачам [Яндекс Трекера](https://tracker.yandex.ru/) через API.

Отчёт содержит название задачи, ключ, дату создания, даты первого перехода в заданные статусы и дедлайн. Подходит для SLA-аналитики и отчётности по этапам прохождения задач.

## Возможности

- Поиск задач по [языку запросов](https://yandex.ru/support/tracker/ru/user/query-filter) (очередь, проект, период создания)
- Получение дат смены статусов из истории изменений (`changelog`)
- Экспорт в CSV с кодировкой `utf-8-sig` (корректно открывается в Excel)
- Пагинация списка задач и истории изменений
- Проверка подключения к API (`--check`)
- Настройка через `.env` и аргументы командной строки

## Структура отчёта

| Колонка | Описание |
| --- | --- |
| Ключ | Ключ задачи, например `ITDIG-123` |
| Название | Заголовок задачи |
| Дата создания | Дата создания задачи |
| Дата перехода в В работе | Первая дата перехода в статус «В работе» |
| Дата перехода в Демонстрация заказчику | Первая дата перехода в статус «Демонстрация заказчику» |
| Дедлайн | Дедлайн задачи |

Если задача ни разу не переходила в указанный статус, соответствующая ячейка остаётся пустой.

## Требования

- Python 3.10+
- Доступ к API Яндекс Трекера
- OAuth-токен с правом `tracker:read`
- Права на чтение задач в нужной очереди

## Установка

```bash
git clone <url-репозитория>
cd tracker

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> **Важно:** запускайте скрипт из виртуального окружения (`.venv`), иначе получите ошибку `ModuleNotFoundError: No module named 'requests'`.

## Настройка

### 1. Создайте файл `.env`

```bash
cp .env.example .env
```

### 2. Заполните переменные

```env
TRACKER_OAUTH_TOKEN=ваш_oauth_токен
TRACKER_ORG_ID=ваш_id_организации
TRACKER_QUEUE=ITDIG
TRACKER_PROJECT=tickets.fcdm.ru
```

| Переменная | Обязательная | Описание |
| --- | --- | --- |
| `TRACKER_OAUTH_TOKEN` | Да | OAuth-токен для API |
| `TRACKER_ORG_ID` | Да* | ID организации (Yandex 360) |
| `TRACKER_CLOUD_ORG_ID` | Да* | ID организации (Yandex Cloud) |
| `TRACKER_QUEUE` | Нет** | Ключ очереди |
| `TRACKER_PROJECT` | Нет** | Название проекта в Трекере |

\* Укажите **только один** ID организации — в зависимости от типа вашей организации.  
\** Нужна хотя бы одна из переменных: `TRACKER_QUEUE` или `TRACKER_PROJECT` (можно обе).

### 3. Получение OAuth-токена

1. Перейдите на [oauth.yandex.ru](https://oauth.yandex.ru/).
2. Создайте приложение: **Для доступа к API или отладки**.
3. Добавьте право **«Чтение из трекера»** (`tracker:read`).
4. Создайте токен для аккаунта, у которого есть доступ к нужной очереди.
5. Скопируйте токен в `TRACKER_OAUTH_TOKEN`.

Подробнее: [доступ к API через OAuth 2.0](https://yandex.ru/support/tracker/ru/concepts/access.html).

### 4. ID организации

ID берётся в Трекере: **Администрирование → Организации → ID**.

| Тип организации | Переменная в `.env` | HTTP-заголовок |
| --- | --- | --- |
| Yandex 360 для бизнеса | `TRACKER_ORG_ID` | `X-Org-ID` |
| Yandex Cloud Organization | `TRACKER_CLOUD_ORG_ID` | `X-Cloud-Org-ID` |

**Пример для Yandex 360:**

```env
TRACKER_OAUTH_TOKEN=AQAAAAA...
TRACKER_ORG_ID=12345678
TRACKER_QUEUE=ITDIG
```

**Пример для Yandex Cloud:**

```env
TRACKER_OAUTH_TOKEN=AQAAAAA...
TRACKER_CLOUD_ORG_ID=bpfxxxxxxxx
TRACKER_QUEUE=ITDIG
```

Не задавайте оба ID одновременно — при наличии `TRACKER_CLOUD_ORG_ID` он имеет приоритет.

## Использование

### Проверка подключения

Перед формированием отчёта убедитесь, что токен и ID организации настроены верно:

```bash
source .venv/bin/activate
python tracker_report.py --check
```

Ожидаемый вывод:

```
Авторизация OK: Иван Иванов (ivan.ivanov)
Заголовок организации: X-Org-ID
Проверка пройдена. Запустите без --check для формирования отчёта.
```

### Формирование отчёта

```bash
python tracker_report.py
```

По умолчанию:

- очередь и проект — из `.env`;
- период создания задач: `2025-07-01` … `2026-06-17`;
- выходной файл: `tracker_report.csv`.

### Запуск без активации venv

```bash
.venv/bin/python tracker_report.py
```

### Параметры командной строки

```bash
python tracker_report.py --help
```

| Параметр | По умолчанию | Описание |
| --- | --- | --- |
| `--queue` | `TRACKER_QUEUE` | Ключ очереди |
| `--project` | `TRACKER_PROJECT` | Название проекта |
| `--date-from` | `2025-07-01` | Начало периода (дата создания) |
| `--date-to` | `2026-06-17` | Конец периода (дата создания) |
| `--status-in-progress` | `В работе` | Статус «в работе» |
| `--status-demo` | `Демонстрация заказчику` | Статус «демонстрация» |
| `-o`, `--output` | `tracker_report.csv` | Путь к выходному CSV |
| `--per-page` | `100` | Задач на страницу при поиске |
| `--delay` | `0.1` | Пауза между запросами к API (сек) |
| `--check` | — | Только проверить авторизацию |

### Примеры

Отчёт по очереди за другой период:

```bash
python tracker_report.py \
  --queue ITDIG \
  --date-from 2025-01-01 \
  --date-to 2025-12-31 \
  -o report_2025.csv
```

Отчёт по очереди и проекту:

```bash
python tracker_report.py \
  --queue ITDIG \
  --project "tickets.fcdm.ru" \
  -o itdig_report.csv
```

Другие названия статусов:

```bash
python tracker_report.py \
  --status-in-progress "In Progress" \
  --status-demo "Ready for demo"
```

Названия статусов должны **точно совпадать** с отображаемым именем в интерфейсе Трекера.

## Эквивалентный запрос в интерфейсе Трекера

Для проверки списка задач в UI (страница **Задачи → Язык запросов**):

```
Queue: ITDIG
Project: "tickets.fcdm.ru"
Created: "2025-07-01".."2026-06-17"
"Sort By": Created ASC
```

## Пример результата

```csv
Ключ,Название,Дата создания,Дата перехода в В работе,Дата перехода в Демонстрация заказчику,Дедлайн
ITDIG-123,Реализовать API,2025-09-10,2025-09-12,2025-09-20,2025-09-25
```

## Как это работает

```
1. POST /v3/issues/_search     → список задач по фильтру
2. GET  /v3/issues/{key}/changelog?field=status  → история статусов
3. Анализ changelog            → первая дата каждого статуса
4. Запись CSV                  → utf-8-sig
```

Скрипт для каждой задачи запрашивает историю изменений, потому что стандартный экспорт CSV в Трекере **не содержит даты смены статусов**.

## Регулярный запуск (cron)

```cron
0 9 * * 1 cd /path/to/tracker && .venv/bin/python tracker_report.py -o reports/$(date +\%Y-\%m-\%d).csv
```

## Устранение неполадок

### `ModuleNotFoundError: No module named 'requests'`

Зависимости не установлены или скрипт запущен вне venv:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python tracker_report.py
```

### HTTP 401 Unauthorized

- Неверный или просроченный `TRACKER_OAUTH_TOKEN`
- У OAuth-приложения нет права `tracker:read`
- Перевыпустите токен на [oauth.yandex.ru](https://oauth.yandex.ru/)

### HTTP 403 Forbidden

Токен принят, но нет прав. Проверьте:

1. **Тип ID организации** — `TRACKER_ORG_ID` для Yandex 360, `TRACKER_CLOUD_ORG_ID` для Cloud
2. **Не заданы оба ID** в `.env` одновременно
3. **Доступ к очереди** — аккаунт токена видит очередь в интерфейсе Трекера
4. Запустите диагностику: `python tracker_report.py --check`

| Симптом | Вероятная причина |
| --- | --- |
| 403 на `--check` | Неверный ID организации или тип заголовка |
| `--check` OK, 403 на поиске | Нет прав на поиск / очередь |
| 401 | Неверный токен |

### Пустой отчёт или мало задач

- Проверьте фильтр в интерфейсе Трекера тем же запросом
- Убедитесь, что `TRACKER_PROJECT` совпадает с названием проекта в Трекере
- Проверьте диапазон дат `--date-from` / `--date-to`

### HTTP 429 Too Many Requests

Скрипт автоматически ждёт и повторяет запрос. При большом числе задач увеличьте паузу:

```bash
python tracker_report.py --delay 0.5
```

## Структура репозитория

```
tracker/
├── tracker_report.py   # основной скрипт
├── requirements.txt    # зависимости Python
├── .env.example        # шаблон настроек
├── .gitignore
└── README.md
```

## Ограничения

- Для каждой задачи выполняется отдельный запрос истории — при большом объёме отчёт формируется долго
- Берётся **первая** (самая ранняя) дата перехода в статус, повторные переходы не учитываются
- Требуется доступ к API; без него даты статусов получить автоматически нельзя

## Полезные ссылки

- [Язык запросов в Трекере](https://yandex.ru/support/tracker/ru/user/query-filter)
- [Доступ к API](https://yandex.ru/support/tracker/ru/concepts/access.html)
- [Поиск задач (API)](https://yandex.ru/support/tracker/ru/concepts/issues/search-issues.html)
- [История изменений задачи (API)](https://yandex.ru/support/tracker/ru/api-ref/issues/get-changelog.html)
