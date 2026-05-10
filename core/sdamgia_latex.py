import re


def normalize_sdamgia_alt(value: str) -> str:
    if value is None:
        return ""
    return (
        str(value)
        .replace("\u00ad", "")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
        .strip()
    )


_FRACTION_RE = re.compile(
    r"дробь:\s*числитель:\s*(?P<num>[^,]+?),\s*знаменатель:\s*(?P<den>[^,]+?)\s*конец\s*дроби",
    flags=re.IGNORECASE,
)

_MIXED_RE = re.compile(
    r"(?:целая\s*часть|целаячасть)\s*[: ]\s*(?P<whole>[^,]+?)\s*,\s*(?:дробная\s*часть|дробнаячасть)\s*[: ]\s*(?:дробь\s*:?\s*)?числитель\s*[: ]\s*(?P<num>[^,]+?)\s*,\s*знаменатель\s*[: ]\s*(?P<den>[^,]+?)(?:\s*конец\s*дроби)?",
    flags=re.IGNORECASE,
)


def _convert_plain_text(value: str) -> str:
    s = normalize_sdamgia_alt(value)
    s = s.replace("−", "-")

    replacements = [
        ("левая круглая скобка", r"\left("),
        ("правая круглая скобка", r"\right)"),
        ("левая квадратная скобка", r"\left["),
        ("правая квадратная скобка", r"\right]"),
        ("умножить на", r"\cdot "),
        ("плюс", "+"),
        ("минус", "-"),
        ("равно", "="),
        ("в квадрате", r"^2"),
        ("в кубе", r"^3"),
    ]

    lower = s.lower()
    for needle, repl in replacements:
        if needle in lower:
            s = re.sub(re.escape(needle), lambda _m, r=repl: r, s, flags=re.IGNORECASE)
            lower = s.lower()

    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(" .")
    return s


def latex_from_sdamgia_alt(value: str, *, max_depth: int = 6) -> str | None:
    s = normalize_sdamgia_alt(value)
    if not s:
        return None

    def replace_mixed(match: re.Match) -> str:
        whole_raw = match.group("whole").strip()
        num_raw = match.group("num").strip()
        den_raw = match.group("den").strip()
        whole = latex_from_sdamgia_alt(whole_raw, max_depth=max_depth - 1) or _convert_plain_text(whole_raw)
        num = latex_from_sdamgia_alt(num_raw, max_depth=max_depth - 1) or _convert_plain_text(num_raw)
        den = latex_from_sdamgia_alt(den_raw, max_depth=max_depth - 1) or _convert_plain_text(den_raw)

        try:
            w_int = int(re.sub(r"[^0-9\-]+", "", whole_raw))
            n_int = int(re.sub(r"[^0-9\-]+", "", num_raw))
            d_int = int(re.sub(r"[^0-9\-]+", "", den_raw))
            if d_int:
                top = w_int * d_int + n_int
                return rf"\frac{{{top}}}{{{d_int}}}"
        except Exception:
            pass

        return rf"{whole}+\frac{{{num}}}{{{den}}}"

    def replace_fraction(match: re.Match) -> str:
        num_raw = match.group("num").strip()
        den_raw = match.group("den").strip()
        num = latex_from_sdamgia_alt(num_raw, max_depth=max_depth - 1) or _convert_plain_text(num_raw)
        den = latex_from_sdamgia_alt(den_raw, max_depth=max_depth - 1) or _convert_plain_text(den_raw)
        return rf"\frac{{{num}}}{{{den}}}"

    depth = max_depth
    while depth > 0 and _MIXED_RE.search(s):
        s = _MIXED_RE.sub(replace_mixed, s)
        depth -= 1

    depth = max_depth
    while depth > 0 and _FRACTION_RE.search(s):
        s = _FRACTION_RE.sub(replace_fraction, s)
        depth -= 1

    s = _convert_plain_text(s)
    if not s:
        return None

    s = re.sub(r"\s*([+\-=])\s*", r"\1", s)
    s = re.sub(r"\s*\\cdot\s*", r"\\cdot ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s
