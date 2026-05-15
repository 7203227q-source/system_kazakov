from collections import Counter


def _normalize_digits_sequence(s: str) -> str:
    """
    Для заданий, где ответ — последовательность цифр без разделителей.
    Принимаем более "человеческий" ввод: пробелы/запятые/точки убираем.
    """
    if s is None:
        return ""
    return "".join(ch for ch in str(s).strip() if ch.isdigit())


def get_max_points_effective(task) -> int:
    """
    В проекте исторически использовались Task.exam_points (под ЕГЭ),
    но корректный максимум по линии заданий хранится в TaskType.max_points.
    """
    try:
        a = int(getattr(task, "exam_points", 0) or 0)
    except Exception:
        a = 0
    try:
        tt = getattr(task, "task_type", None)
        b = int(getattr(tt, "max_points", 0) or 0) if tt else 0
    except Exception:
        b = 0
    return max(a, b)


def is_oge_physics(task) -> bool:
    tt = getattr(task, "task_type", None)
    ef = getattr(tt, "exam_format", None) if tt else None
    subject_name = (getattr(getattr(ef, "subject", None), "name", "") or "").lower()
    fmt_name = (getattr(ef, "name", "") or "").lower()
    return ("физ" in subject_name) and ("огэ" in fmt_name)


def is_ege_physics(task) -> bool:
    tt = getattr(task, "task_type", None)
    ef = getattr(tt, "exam_format", None) if tt else None
    subject_name = (getattr(getattr(ef, "subject", None), "name", "") or "").lower()
    fmt_name = (getattr(ef, "name", "") or "").lower()
    return ("физ" in subject_name) and ("егэ" in fmt_name)


def score_short_answer(task, user_answer: str) -> int:


    """

    Поддержана официальная система оценивания ОГЭ физика 2026:
    - №3, 5–11, 15: 1 балл при полном совпадении с эталоном.
    - №1, 2, 4, 12, 13: 2 балла при полном совпадении; 1 балл при одной ошибке в позиции; иначе 0.
    - №14, 16: порядок символов не важен; 1 балл при одной ошибке/одном пропуске; иначе 0. Лишние символы → 0.
    """
    max_points = int(get_max_points_effective(task) or 0)
    if max_points <= 0:
        return 0

    correct_raw = (getattr(task, "correct_answer", "") or "").strip()
    # Общая нормализация "как раньше" для чисел/строк
    ans_raw = (user_answer or "").strip()

    # Специальные правила только для ОГЭ физика (2026 без изменений к 2025).
    if is_oge_physics(task):
        tt = getattr(task, "task_type", None)
        try:
            num = int(getattr(tt, "number", 0) or 0)
        except Exception:
            num = 0

        # Задания, где ответ — последовательность цифр
        if max_points == 2 and num in {1, 2, 4, 12, 13, 14, 16}:
            correct = _normalize_digits_sequence(correct_raw)
            ans = _normalize_digits_sequence(ans_raw)

            # Лишние символы всегда 0
            if len(ans) > len(correct):
                return 0

            if num in {1, 2, 4, 12, 13}:
                # порядок важен, 1 балл при ровно одной ошибке в позиции
                if len(ans) != len(correct):
                    return 0
                mismatches = sum(1 for a, b in zip(ans, correct) if a != b)
                if mismatches == 0:
                    return 2
                if mismatches == 1:
                    return 1
                return 0

            if num in {14, 16}:
                # порядок не важен; 1 балл: один неверный символ ИЛИ один отсутствует
                # (при условии отсутствия лишних символов)
                c = Counter(correct)
                a = Counter(ans)
                common = sum(min(c[k], a.get(k, 0)) for k in c.keys())
                missing = len(correct) - common
                extra = len(ans) - common

                if missing == 0 and extra == 0 and len(ans) == len(correct):
                    return 2

                # один неверный символ: длины равны, missing==1 и extra==1
                if len(ans) == len(correct) and missing == 1 and extra == 1:
                    return 1

                # один пропуск: missing==1, extra==0, длина на 1 меньше
                if len(ans) == len(correct) - 1 and missing == 1 and extra == 0:
                    return 1

                return 0

        # 1-балльные задания: полное совпадение с эталоном
        if max_points == 1:
            norm_user = ans_raw.lower().replace(",", ".")
            norm_correct = correct_raw.lower().replace(",", ".")
            return 1 if norm_user == norm_correct else 0

        # fallback
        norm_user = ans_raw.lower().replace(",", ".")
        norm_correct = correct_raw.lower().replace(",", ".")
        return max_points if norm_user == norm_correct else 0

    # ЕГЭ физика 2026: правила частичного балла для некоторых заданий с кратким ответом.
    # Источник: спецификация КИМ ЕГЭ 2026 (раздел "Система оценивания выполнения отдельных заданий").
    if is_ege_physics(task):
        tt = getattr(task, "task_type", None)
        try:
            num = int(getattr(tt, "number", 0) or 0)
        except Exception:
            num = 0

        # Группа 1 балл (строгое совпадение), кроме №20 (порядок не важен)
        one_point_exact = {1, 2, 3, 4, 7, 8, 11, 12, 13, 16, 19}
        if max_points == 1 and num in one_point_exact:
            norm_user = ans_raw.lower().replace(",", ".")
            norm_correct = correct_raw.lower().replace(",", ".")
            return 1 if norm_user == norm_correct else 0

        # №20 (1 балл): порядок символов не важен (обычно последовательность цифр)
        if max_points == 1 and num == 20:
            correct = _normalize_digits_sequence(correct_raw)
            ans = _normalize_digits_sequence(ans_raw)
            return 1 if Counter(correct) == Counter(ans) and len(correct) == len(ans) else 0

        # Группа 2 балла, порядок важен: 6, 10, 15, 17
        # 2 балла: полное совпадение (каждый символ на своём месте, без лишних).
        # 1 балл: одна ошибка в одной позиции. Иначе 0. Лишние символы => 0.
        if max_points == 2 and num in {6, 10, 15, 17}:
            correct = _normalize_digits_sequence(correct_raw)
            ans = _normalize_digits_sequence(ans_raw)
            if len(ans) > len(correct):
                return 0
            if len(ans) != len(correct):
                return 0
            mismatches = sum(1 for a, b in zip(ans, correct) if a != b)
            if mismatches == 0:
                return 2
            if mismatches == 1:
                return 1
            return 0

        # Множественный выбор (2 или 3 верных ответа): 5, 9, 14, 18
        # 2 балла: все нужные символы, без лишних, порядок не важен
        # 1 балл: один символ неверный (в т.ч. один лишний при остальных верных) ИЛИ один отсутствует
        # иначе 0
        if max_points == 2 and num in {5, 9, 14, 18}:
            correct = _normalize_digits_sequence(correct_raw)
            ans = _normalize_digits_sequence(ans_raw)

            c = Counter(correct)
            a = Counter(ans)
            common = sum(min(c[k], a.get(k, 0)) for k in c.keys())
            missing = len(correct) - common
            extra = len(ans) - common

            if missing == 0 and extra == 0 and len(ans) == len(correct):
                return 2

            if (missing == 1 and extra == 0 and len(ans) == len(correct) - 1) or (
                missing == 0 and extra == 1 and len(ans) == len(correct) + 1
            ) or (
                missing == 1 and extra == 1 and len(ans) == len(correct)
            ):
                return 1

            return 0

        # На всякий случай: строгий fallback
        norm_user = ans_raw.lower().replace(",", ".")
        norm_correct = correct_raw.lower().replace(",", ".")
        return max_points if norm_user == norm_correct else 0

    # Общий fallback для остальных экзаменов
    norm_user = ans_raw.lower().replace(",", ".")
    norm_correct = correct_raw.lower().replace(",", ".")
    return max_points if norm_user == norm_correct else 0
