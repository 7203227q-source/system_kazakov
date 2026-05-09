## Контекст

В системе есть два вида «очков», которые важны для пользователя:

1) **XP/уровень** (геймификация) — фактически сейчас начисляется в `StudentSubjectProfile.xp` (по предметам).  
2) **Баллы за решение** (оценка решения) — хранится как:
   - `Submission.score` (0 или `task.exam_points` для части 1),
   - `Submission.primary_score` (0..`task.exam_points` для части 2).

Проблема: часть экранов показывает `user.xp/user.level`, которые сейчас не синхронизируются с `StudentSubjectProfile`, поэтому в некоторых местах XP может отображаться как 0. Также в «Журнале решений» не отображаются баллы за конкретное решение.

## Цель

- Во всех ключевых экранах ученика и репетитора показывать корректные **суммарные XP/уровень**.
- В экранах истории/результата показывать **баллы за конкретное решение** в формате `X/Y`.

## Решение

### 1) XP/уровень — суммарно по предметам

Считаем:
- `total_xp = sum(profile.xp for profile in StudentSubjectProfile where student=...)`
- `total_level = total_xp // 100 + 1`

Показываем `total_level` и `total_xp` вместо `user.level/user.xp` в следующих местах:
- `student_dashboard` (шапка/блок уровня),
- `student_practice` и `student_practice_result` (шапка),
- `student_history` (шапка),
- `tutor_dashboard` (в списке учеников у репетитора).

При этом предметные графики/прогресс на `student_dashboard` остаются привязанными к `active_profile`.

### 2) Баллы за решение — отображение `X/Y`

Добавить вывод баллов:
- В `student_practice_result`: `Баллы: 1/1` (или `0/1`) на основе `is_correct` и `task.exam_points`.
- В `student_history`: для каждой записи показывать `Баллы: X/Y`, где:
  - `Y = sub.task.exam_points`,
  - `X = (sub.primary_score если Y>1, иначе (1 если sub.is_correct else 0))`.

## Критерии готовности

- XP/уровень не «обнуляется» на экранах practice/history/tutor_dashboard.
- В истории и результатах тренажёра видно, сколько баллов получено за решение (`X/Y`).
