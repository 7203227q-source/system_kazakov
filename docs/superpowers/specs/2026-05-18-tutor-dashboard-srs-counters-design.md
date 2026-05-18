## Цель

Добавить в кабинете репетитора на карточке ученика:

- Сколько задач ученик должен повторить сегодня (SRS due today).
- Сколько задач из SRS ученик повторил сегодня (SRS reviewed today).

Показать метрики:

- В карточке ученика в списке (левая колонка).
- В шапке выбранного ученика (правая часть, профиль).

## Термины и определения

- SRS due today: количество записей SpacedRepetition, у которых next_review_date <= today.
- SRS reviewed today: количество уникальных задач SRS, которые были повторены сегодня. Считается как количество записей SpacedRepetition, у которых last_reviewed_at__date == today.

Ограничение: если ученик повторит одну и ту же задачу несколько раз в один день, она считается как 1 (по записи SpacedRepetition).

## Изменения данных

### Модель

Добавить поле в SpacedRepetition:

- last_reviewed_at: DateTimeField(null=True, blank=True, db_index=True)

Назначение: фиксировать факт “задача была повторена” в момент обработки SRS-ответа.

### Миграция

- Добавить поле last_reviewed_at с индексом.
- Данных для бэкфилла нет (раньше факт повторения не фиксировался), поэтому поле по умолчанию пустое.

## Изменения логики SRS

### Где обновлять last_reviewed_at

В функции process_srs_review(srs_record, grade) при каждом обновлении записи:

- last_reviewed_at = timezone.now()
- сохранить вместе с остальными изменениями SM-2 (next_review_date, interval, repetitions, easiness_factor, last_grade)

Это гарантирует, что “reviewed today” фиксируется как часть канонического обновления SRS.

## Подсчёт метрик в tutor_dashboard

### Требования к производительности

Не делать N+1 запросов “на ученика” в цикле шаблона. Подсчёты должны выполняться одним-двумя агрегирующими запросами по всем student_ids текущего репетитора.

### Вычисления

Пусть today = timezone.localdate().

Сформировать отображения:

- srs_due_today_map: student_id -> Count(SpacedRepetition where next_review_date <= today)
- srs_reviewed_today_map: student_id -> Count(SpacedRepetition where last_reviewed_at__date == today)

Затем навесить на объекты students:

- student.srs_due_today = int(map.get(student.id, 0))
- student.srs_reviewed_today = int(map.get(student.id, 0))

Для selected_student использовать те же поля (он берётся из queryset students), чтобы шаблон мог выводить значения без отдельных запросов.

## Изменения UI (tutor_dashboard.html)

### Карточка ученика в списке (левая колонка)

В блоке, где сейчас выводится:

- “Сегодня: +XP”
- бейдж “Вопросы: N” (если есть)

Добавить 1–2 компактных бейджа/строки:

- “Повтор сегодня: {{ student.srs_due_today }}”
- “Повторил: {{ student.srs_reviewed_today }}”

### Шапка выбранного ученика (правая колонка)

Рядом с бейджем “Сегодня: +XP” добавить:

- “Повтор сегодня: {{ selected_student.srs_due_today }}”
- “Повторил: {{ selected_student.srs_reviewed_today }}”

## Тестирование

### Юнит/интеграционные тесты

- process_srs_review устанавливает last_reviewed_at (и обновляет его при повторном вызове).
- tutor_dashboard считает:
  - due today корректно по next_review_date__lte=today
  - reviewed today корректно по last_reviewed_at__date=today

### Шаблон

- В ответе tutor_dashboard присутствуют строки “Повтор сегодня” и “Повторил” (минимально через assertContains).

## Риски и ограничения

- Исторические “повторил сегодня” за прошлые дни до внедрения невозможны (нет данных).
- reviewed today считает уникальные задачи, а не количество попыток.
