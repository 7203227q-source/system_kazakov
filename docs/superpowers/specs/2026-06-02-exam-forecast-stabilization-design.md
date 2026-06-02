# Exam Forecast Stabilization (predicted_exam_score) — Design

**Цель:** снизить волатильность и “нереалистичную” тенденцию прогноза к 100/максимуму, сохранив текущий формат отображения в UI (одно значение), при этом показывать **оба значения**: проценты (/100) и пересчёт в первичные баллы.

## Контекст (как сейчас)

- Прогноз хранится в `DailySnapshot.predicted_exam_score` (0–100): [models.py](file:///workspace/core/models.py#L484-L499).
- Расчёт делается в [update_student_analytics](file:///workspace/core/analytics.py#L110-L214):
  - `current_mastery` — EMA по логам решения задач (учитывает `trust_factor`).
  - `recent_perf` — среднее по последним 30 логам с весом 1.0 для verified и 0.8 для unverified.
  - `blended_mastery = 0.7*current_mastery + 0.3*recent_perf`.
  - `predicted_score = blended_mastery * learning_velocity` + (опционально) тренд по 14 дням до `exam_date`.
  - Затем clamp в [0..100].
- `learning_velocity` обновляется по завершённым вариантам в [calibrate_learning_velocity_for_assignment](file:///workspace/core/analytics.py#L262-L390), диапазон сейчас `[0.5..1.5]`.
- UI:
  - У ученика прогноз и график берутся из `DailySnapshot.predicted_exam_score`: [student_dashboard](file:///workspace/core/views.py#L1144-L1207), [student_dashboard.html](file:///workspace/core/templates/core/student_dashboard.html#L123-L189).
  - У репетитора и родителя прогноз также отображается как `predicted_exam_score`: [tutor_dashboard.html](file:///workspace/core/templates/core/tutor_dashboard.html#L351-L421), [parent_dashboard.html](file:///workspace/core/templates/core/parent_dashboard.html#L81-L99).

## Требования

1) Прогноз должен быть менее “прыгающим” при единичных событиях (1–3 решения, случайно высокая серия).
2) Прогноз не должен “легко” упираться в 100 за счёт механики тренда/learning_velocity, пока данных мало.
3) Сохранить обратную совместимость:
   - `DailySnapshot.predicted_exam_score` остаётся в шкале 0–100.
   - График и прогресс-бар продолжают работать от процентов.
4) Отображение: в UI показывать оба значения — проценты (/100) + первичные баллы (через `core.exam_scoring.primary_from_percent`).

## Решение

### 1) Shrinkage для “текущего перформанса” (recent_perf)

Идея: если “веса” последних попыток мало, не давать `recent_perf` резко сдвигать прогноз от `current_mastery`.

В [update_student_analytics](file:///workspace/core/analytics.py#L110-L214) вместо прямого смешивания `recent_perf` используем shrinkage:

- Считаем:
  - `recent_perf` как и сейчас
  - `recent_weight = sum(w)` по тем же логам (w=1.0 verified, w=0.8 unverified)
- Константа: `RECENT_SHRINK_K = 10.0`
- Коэффициент доверия недавнему перформансу:
  - `w_shrink = recent_weight / (recent_weight + RECENT_SHRINK_K)`
- “Сжатый” перформанс:
  - `recent_adj = current_mastery + w_shrink * (recent_perf - current_mastery)`
- Дальше используем:
  - `blended_mastery = 0.7*current_mastery + 0.3*recent_adj`

Эффект: при маленьком `recent_weight` прогноз ближе к EMA, при большом — реагирует на устойчивую текущую серию.

### 2) Ограничение горизонта и силы тренда до exam_date

Проблема: если `exam_date` далеко, `slope * days_left` может слишком разгонять/ронять прогноз, после чего он упирается в clamp.

Правило:
- Тренд проецируем не на весь `days_left`, а только на ограниченный горизонт:
  - `TREND_HORIZON_DAYS = 30`
  - `h = min(days_left, TREND_HORIZON_DAYS)`
- Ограничиваем вклад тренда:
  - `TREND_MAX_DELTA = 20.0` (в пунктах мастерства на горизонте)
  - `trend_delta = clamp(slope * h, -TREND_MAX_DELTA, +TREND_MAX_DELTA)`
- Тогда:
  - `projected_mastery = blended_mastery + trend_delta`
  - `raw_pred = projected_mastery * learning_velocity`

### 3) Инерция прогноза (сглаживание по предыдущему снэпшоту)

Чтобы “цифра прогноза” не менялась резко из-за одиночных событий, после расчёта `raw_pred` применяем сглаживание по предыдущему значению:

- Константа: `PRED_SMOOTH_BETA = 0.35`
- Берём `prev_pred` из последнего `DailySnapshot.predicted_exam_score` строго до `today`.
- Если `prev_pred` существует:
  - `pred = PRED_SMOOTH_BETA * raw_pred + (1 - PRED_SMOOTH_BETA) * prev_pred`
- Если `prev_pred` отсутствует:
  - `pred = raw_pred`

Дополнительно вводим ограничитель дневного шага (включён по умолчанию), применяемый после сглаживания:
- `PRED_MAX_STEP_UP = 6.0`
- `PRED_MAX_STEP_DOWN = 8.0`
- `pred = clamp(pred, prev_pred - PRED_MAX_STEP_DOWN, prev_pred + PRED_MAX_STEP_UP)`

### 4) Стабилизация learning_velocity (калибровка по вариантам)

Цель: убрать сценарии, когда velocity становится источником “разгона к 100”.

Изменения в [calibrate_learning_velocity_for_assignment](file:///workspace/core/analytics.py#L262-L390):

- Сузить допустимый диапазон:
  - было: `[0.5..1.5]`
  - станет: `[0.7..1.3]`
- Смягчить шаг адаптации:
  - `k`: было `0.25` → станет `0.15`
  - `delta clamp`: было `[-0.10..0.10]` → станет `[-0.06..0.06]`

Это сохраняет адаптацию, но делает её менее “нервной” и уменьшает вероятность разгона.

## Изменения UI

### Student dashboard

- Оставляем текущее отображение прогноза “как сейчас” (одно значение), но гарантируем, что рядом выводятся оба значения:
  - проценты (0–100) — как есть
  - первичные баллы — через `core.exam_scoring.primary_from_percent` (это уже используется в [student_dashboard](file:///workspace/core/views.py#L1148-L1184))

### Tutor / Parent dashboards

- Привести к тому же формату “оба значения” (проценты + первичные баллы) по аналогии со student dashboard.

## Тестирование (минимум)

1) Shrinkage:
   - при `recent_weight` маленьком `recent_adj` близко к `current_mastery`
   - при `recent_weight` большом `recent_adj` близко к `recent_perf`
2) Сглаживание:
   - при наличии `prev_pred` итоговый `pred` меняется плавнее `raw_pred`
3) Тренд:
   - при большом `days_left` вклад тренда ограничен горизонтом и `TREND_MAX_DELTA`
4) learning_velocity:
   - `new_lv` всегда в `[0.7..1.3]`, шаг ограничен

## Риски и настройка

- Константы (`RECENT_SHRINK_K`, `TREND_HORIZON_DAYS`, `TREND_MAX_DELTA`, `PRED_SMOOTH_BETA`, шаги) предполагаются “стартовыми”; их нужно будет подстроить по реальным данным (в идеале — по логам/истории и ощущениям репетиторов).
- Все константы держим рядом с `ALPHA` в [analytics.py](file:///workspace/core/analytics.py#L7-L7), чтобы настройка была централизованной.
