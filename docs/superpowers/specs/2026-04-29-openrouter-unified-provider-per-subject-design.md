## Цель
Перейти на единый провайдер OpenRouter для всех ИИ-сценариев и дать администратору возможность выбирать модели по предмету для разных задач: анализ фото, проверка решения, генерация изображения, регенерация задачи (текст), регенерация задачи (изображение).

## Требования
- Удалить отдельные Gemini/OpenAI статусы из “Система и Интеграции”; заменить на OpenRouter.
- Ключ хранить только в ENV: `OPENROUTER_API_KEY` (и опц. `OPENROUTER_HTTP_REFERER`, `OPENROUTER_APP_NAME`).
- Подгружать “все модели” из OpenRouter; отмечать важные ⭐.
- Настройки выбора моделей — по предмету (Subject).
- Для каждого сценария показывать выпадающий список моделей с группировкой:
  - сначала ⭐ (featured),
  - затем остальные (включая неактивные), визуально помечая неактивные.
- Кнопка “Обновить список моделей” в админке.
- Автоопределение endpoint списка моделей (пробуем оба):
  - `https://openrouter.ai/api/v1/models`
  - `https://openrouter.ai/models`

## Модели данных
### OpenRouterModel
- `code` (unique): строка модели (например `openai/gpt-4o-mini`)
- `label`: отображаемое имя
- `capabilities`: `text|vision|image` (multi)
- `is_active`: bool
- `is_featured`: bool (⭐)
- `updated_at`

### SubjectAIConfig
1 запись на Subject:
- `subject` (unique FK)
- `photo_analysis_model` (FK -> OpenRouterModel)
- `solution_check_model` (FK -> OpenRouterModel)
- `image_generate_model` (FK -> OpenRouterModel)
- `task_regen_text_model` (FK -> OpenRouterModel)
- `task_regen_image_model` (FK -> OpenRouterModel)

## UI: /platform-admin/system/
- Карточка OpenRouter: статус ключа + кнопка “Проверить”
- Секция “Модели”: кнопки “Обновить список” и “Показать все/только активные” (оставляем “все”)
- Секция “Настройки по предметам”: таблица предметов и 5 выпадающих списков

## Использование в коде
- Все вызовы ИИ идут через `openrouter_client`.
- В зависимости от сценария выбирается модель из `SubjectAIConfig` по предмету, извлеченному из сущности:
  - task/submission -> task.topic.subject
  - fallback: первый Subject или дефолтная конфигурация (если SubjectAIConfig нет)

## Ошибки/валидация
- Если нет ключа: понятная ошибка в UI + запрет на “Обновить список моделей”
- Если endpoint модели недоступен: показывать ошибку и логировать
