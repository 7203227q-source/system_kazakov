## Контекст

Нужно добавить срок выполнения для вариантов (Assignment), автоматическое закрытие по истечении срока (с выставлением 0 за нерешённые задачи) и механизм продления срока по просьбе ученика с подтверждением репетитора. Вариант после просрочки остаётся в истории.

Пожелания:
- Дедлайн задаётся датой (до 23:59).
- Просрочка влияет на мастерство/прогноз: нерешённые задачи учитываются как 0.
- При продлении после просрочки вариант переоткрывается.

## Модель данных

### Assignment

Добавить поля:
- `due_date` (DateField, null=True, blank=True) — дедлайн “до конца дня”.
- `is_expired` (BooleanField, default=False) — признак автозакрытия из‑за дедлайна.
- `expired_at` (DateTimeField, null=True, blank=True) — когда был просрочен и закрыт.

### AssignmentExtensionRequest

Новая модель запроса на продление:
- `assignment` (FK Assignment)
- `student` (FK User)
- `tutor` (FK User)
- `requested_days` (PositiveIntegerField)
- `comment` (TextField, blank=True, null=True)
- `status` (choices: pending/approved/rejected)
- `created_at` (DateTimeField auto_now_add)
- `resolved_at` (DateTimeField null=True, blank=True)

Ограничения:
- один активный `pending` запрос на вариант (unique constraint на assignment+status=pending или enforced in code).

## Бизнес-логика

### Автозакрытие по дедлайну

Триггер: при заходе ученика/репетитора на связанные страницы (дашборды, страница решения варианта) проверяем:
- если `due_date` задан и `due_date < today` (UTC, до конца дня) и `is_completed=False`,
  - ставим `is_completed=True`, `is_expired=True`, `expired_at=now()`,
  - для каждой задачи варианта гарантируем наличие `Submission`:
    - если submission отсутствует — создаём с `score=0`, `is_correct=False`, `user_answer=''`,
    - если задача 2-й части (`exam_points>1`) — также `primary_score=0` (если null).
  - записываем `record_task_log` по всем задачам (time_spent=0), чтобы влияние “0” попадало в аналитику/прогноз.

### Переоткрытие при продлении

Если репетитор одобряет продление:
- увеличиваем `due_date` на `requested_days` (от max(today, old_due_date) + requested_days),
- если вариант был просрочен (`is_expired=True`) — переоткрываем:
  - `is_completed=False`, `is_expired=False`, `expired_at=NULL`.

Важно: ранее созданные “нулевые” submission’ы остаются — ученик сможет их перезаписать (система уже позволяет обновлять ответы до завершения варианта).

## UI/UX

### Репетитор

Где задаётся дедлайн:
- На публикации варианта (publish) добавить поле “Срок (дата)” — опционально.

Где обрабатывать запросы:
- В просмотре варианта показывать блок “Запрос на продление” (если pending) с кнопками “Одобрить / Отклонить”.

### Ученик

На странице решения варианта:
- Показывать “Срок: DD.MM.YYYY” если задан.
- Кнопка “Попросить продление”:
  - ввод “+N дней” и комментария,
  - создаёт `AssignmentExtensionRequest(status=pending)`.

Если вариант просрочен и был автозакрыт:
- На странице итогов показывать, что “Закрыто по дедлайну”.

## API/URLs (Django views)

- `POST /tutor/assignment/<id>/set-deadline/` — сохранить due_date (только tutor-owner).
- `POST /student/assignment/<id>/extension-request/` — создать/обновить pending request.
- `POST /tutor/assignment/<id>/extension-request/<req_id>/approve/` — одобрить и продлить.
- `POST /tutor/assignment/<id>/extension-request/<req_id>/reject/` — отклонить.

## Критерии готовности

- Репетитор может поставить дату дедлайна на вариант.
- По истечении дедлайна вариант автоматически закрывается, нерешённые задачи получают 0, и это влияет на аналитику.
- Ученик может запросить продление “+N дней”, репетитор одобряет — вариант переоткрывается.

