from __future__ import annotations

from typing import Any


def primary_from_percent(pct: float | int | None, max_primary: int) -> int:
    """
    Перевод значения 0–100 (проценты) в первичный балл экзамена 0..max_primary.
    """
    try:
        v = float(pct or 0.0)
    except Exception:
        v = 0.0
    v = max(0.0, min(100.0, v))
    mp = int(max_primary or 0)
    if mp <= 0:
        return 0
    return int(round(v / 100.0 * mp))


def estimate_geometry_primary(*, total_primary: int, geometry_share: float) -> int:
    """
    MVP-оценка геометрических баллов как доли от общего первичного балла.
    """
    share = float(geometry_share or 0.0)
    share = max(0.0, min(1.0, share))
    return int(round(int(total_primary or 0) * share))


def grade_from_primary(total_primary: int, *, geometry_primary: int, grade_rules: list[dict[str, Any]]) -> int:
    """
    Перевод первичных баллов в оценку по правилам шкалы.
    Поддерживает условие min_geometry для некоторых оценок (ОГЭ математика).
    """
    total = int(total_primary or 0)
    geom = int(geometry_primary or 0)

    matched = None
    for r in grade_rules or []:
        try:
            lo = int(r.get("min_total"))
            hi = int(r.get("max_total"))
        except Exception:
            continue
        if lo <= total <= hi:
            matched = r
            break

    if not matched:
        return 0

    grade = int(matched.get("grade") or 0)
    min_geom = matched.get("min_geometry", None)
    if min_geom is not None:
        try:
            if geom < int(min_geom):
                return 2
        except Exception:
            return 2
    return grade

