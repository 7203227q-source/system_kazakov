# Страница «OpenRouter: баланс и расход»

## Цель
Добавить в админке отдельную страницу, где видно:
1) баланс/лимиты по текущему `OPENROUTER_API_KEY`;
2) расход по моделям (если доступен OpenRouter **management key**).

## Контекст и ограничения
- В проекте уже есть админ-страница `admin_system.html`, где показывается статус `OPENROUTER_API_KEY` и есть кнопка “проверить соединение / обновить список моделей”.
- По требованиям безопасности ключи хранятся только в ENV, в UI не показываем значение ключа.
- OpenRouter endpoints:
  - **GET** `https://openrouter.ai/api/v1/key` — информация по *текущему ключу* (лимиты/остаток/usage daily/weekly/monthly).
  - **GET** `https://openrouter.ai/api/v1/credits` — total credits purchased/used (**management key required**).
  - **GET** `https://openrouter.ai/api/v1/activity` — usage по дням/моделям за последние 30 UTC дней (**management key required**).

## UX (как будет выглядеть)
### Навигация
В левом меню админки добавить пункт:
- “OpenRouter: баланс”

### Содержимое страницы
**Блок 1: Key status (доступно всегда при наличии OPENROUTER_API_KEY)**
- label ключа (если возвращается)
- limit / limit_remaining (или “unlimited”)
- usage_total, usage_daily, usage_weekly, usage_monthly

**Блок 2: Credits (если есть management key)**
- total_credits
- total_usage
- вычисляем “remaining = total_credits - total_usage”

**Блок 3: Расход по моделям (если есть management key)**
Из `/activity` агрегируем:
- model → суммарный `usage` (кредиты) за 30 дней
- requests / tokens (если полезно)
Сортировка по `usage` desc.

### Поведение при отсутствии management key (текущая ситуация)
Если management key нет:
- показываем блок 1 (key info),
- в блоках 2–3 показываем предупреждение “нужен OPENROUTER_MANAGEMENT_KEY” + короткую инструкцию, где создать ключ в OpenRouter.

## Backend
### Новые ENV
- `OPENROUTER_API_KEY` — уже используется
- `OPENROUTER_MANAGEMENT_KEY` — новый (опционально)

### Новый view
`admin_openrouter_balance(request)`:
- доступ: только `admin`
- GET:
  - если нет `OPENROUTER_API_KEY`: показываем статус missing
  - иначе:
    - запрос `/key` → key_info
  - если есть `OPENROUTER_MANAGEMENT_KEY`:
    - запрос `/credits` → credits
    - запрос `/activity` → raw_activity и агрегаты by_model

### Ошибки/устойчивость
- Любые ошибки сети/JSON парсинга не должны валить страницу: показываем статус “ошибка” и текст исключения коротко.

## Тесты
1) Страница доступна только админу.
2) При отсутствии management key страница отдаёт 200 и отображает блок “нужен OPENROUTER_MANAGEMENT_KEY”.
3) При наличии management key (замокать requests.get) отображаются агрегаты расхода по моделям.

