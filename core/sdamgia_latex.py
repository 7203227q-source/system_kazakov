import re


def normalize_sdamgia_alt(value: str) -> str:
    if value is None:
        return ""
    s = (
        str(value)
        .replace("\u00ad", "")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
    )
    s = re.sub(r"(?<=\d),\s+(?=\d)", ",", s)
    s = re.sub(r"конец\s*дроби", "конец дроби", s, flags=re.IGNORECASE)
    s = re.sub(r"конецдроби", "конец дроби", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<=\d)\s*(конец\s+дроби)", r" \1", s, flags=re.IGNORECASE)
    s = re.sub(r"корень\s*из", "корень из", s, flags=re.IGNORECASE)
    s = re.sub(r"кореньиз", "корень из", s, flags=re.IGNORECASE)
    s = re.sub(r"начало\s*аргумента", "начало аргумента", s, flags=re.IGNORECASE)
    s = re.sub(r"началоаргумента", "начало аргумента", s, flags=re.IGNORECASE)
    s = re.sub(r"конец\s*аргумента", "конец аргумента", s, flags=re.IGNORECASE)
    s = re.sub(r"конецаргумента", "конец аргумента", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<=\d)\s*(конец\s+аргумента)", r" \1", s, flags=re.IGNORECASE)
    return s.strip()


_FRACTION_RE = re.compile(
    r"дробь\s*:\s*числитель\s*:\s*(?P<num>.*?)\s*,\s*знаменатель\s*:\s*(?P<den>.*?)\s*конец\s*дроби",
    flags=re.IGNORECASE | re.DOTALL,
)

_MIXED_RE = re.compile(
    r"(?:целая\s*часть|целаячасть)\s*[: ]\s*(?P<whole>-?\d+(?:\s+\d+)*)\s*,\s*(?:дробная\s*часть|дробнаячасть)\s*[: ]\s*(?:дробь\s*:?\s*)?числитель\s*[: ]\s*(?P<num>-?\d+(?:\s+\d+)*)\s*,\s*знаменатель\s*[: ]\s*(?P<den>\d+(?:\s+\d+)*)(?=(?:\s*конец\s*дроби|\s*$|\s*[+\-*/=]))",
    flags=re.IGNORECASE | re.DOTALL,
)

_SQRT_RE = re.compile(
    r"(?:корень\s*из)\s*:\s*(?:начало\s*аргумента)\s*:\s*(?P<arg>.*?)\s*(?:конец\s*аргумента)",
    flags=re.IGNORECASE | re.DOTALL,
)

_SQRT_FALLBACK_RE = re.compile(
    r"(?:корень\s*из)\s*:\s*(?:начало\s*аргумента)\s*:\s*(?P<arg>.*?)(?=(?:\s+умножить\s+на|\s+плюс|\s+минус|\s+равно|,|конец\s+дроби|$))",
    flags=re.IGNORECASE | re.DOTALL,
)

_COMPACT_TFRAC_RE = re.compile(r"\\tfrac\s*([0-9]{2,})")
_SPACED_TFRAC_RE = re.compile(r"\\tfrac\s*([0-9]+)\s+([0-9]+)")
_POWER_PAREN_RE = re.compile(
    r"\((?P<base>[^()]+)\)\s*степени\s*\(?\s*(?P<exp>-?\d+)\s*\)?",
    flags=re.IGNORECASE,
)
_POWER_SIMPLE_RE = re.compile(
    r"(?P<base>[0-9a-zA-Zа-яА-Я]+)\s*степени\s*\(?\s*(?P<exp>-?\d+)\s*\)?",
    flags=re.IGNORECASE,
)

_POWER_RU_RE = re.compile(
    r"(?P<base>[0-9a-zA-Zа-яА-Я]+)\s*в?\s*степени\s*(?:левая\s*круглая\s*скобка\s*)?\s*(?P<exp>-?\d+)\s*(?:конец\s*аргумента\s*)?(?:\s*правая\s*круглая\s*скобка)*",
    flags=re.IGNORECASE,
)


def sanitize_math_latex(value: str) -> str:
    if not value:
        return value

    s = str(value)

    s = re.sub(r"\bв\s*степени\b", "степени", s, flags=re.IGNORECASE)
    s = re.sub(r"\bвстепени\b", "степени", s, flags=re.IGNORECASE)

    def fix_tfrac(match: re.Match) -> str:
        digits = match.group(1)
        num = digits[:1]
        den = digits[1:]
        if not den:
            return match.group(0)
        return rf"\frac{{{num}}}{{{den}}}"

    s = _SPACED_TFRAC_RE.sub(lambda m: rf"\frac{{{m.group(1)}}}{{{m.group(2)}}}", s)
    s = _COMPACT_TFRAC_RE.sub(fix_tfrac, s)

    s = _POWER_PAREN_RE.sub(lambda m: rf"({m.group('base')})^{{{m.group('exp')}}}", s)
    s = _POWER_SIMPLE_RE.sub(lambda m: rf"{m.group('base')}^{{{m.group('exp')}}}", s)

    s = s.replace(r"\left(", "(").replace(r"\right)", ")")
    s = s.replace(r"\left[", "[").replace(r"\right]", "]")
    s = s.replace(r"\left\{", r"\{").replace(r"\right\}", r"\}")
    s = s.replace(r"\left.", "").replace(r"\right.", "")
    s = s.replace(r"\left", "").replace(r"\right", "")

    return s


def _convert_plain_text(value: str) -> str:
    s = normalize_sdamgia_alt(value)
    s = s.replace("−", "-")
    s = s.replace("·", r"\cdot ")
    s = s.replace("⋅", r"\cdot ")

    replacements = [
        ("больше или равно", r"\ge"),
        ("меньше или равно", r"\le"),
        ("не меньше", r"\ge"),
        ("не менее", r"\ge"),
        ("не больше", r"\le"),
        ("не более", r"\le"),
        ("больше", ">"),
        ("меньше", "<"),
        ("левая круглая скобка", "("),
        ("правая круглая скобка", ")"),
        ("левая квадратная скобка", "["),
        ("правая квадратная скобка", "]"),
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
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
    s = sanitize_math_latex(s)
    return s


def latex_from_sdamgia_alt(value: str, *, max_depth: int = 6) -> str | None:
    s = normalize_sdamgia_alt(value)
    if not s:
        return None
    s = sanitize_math_latex(s)

    depth = max_depth
    while depth > 0 and _POWER_RU_RE.search(s):
        s = _POWER_RU_RE.sub(lambda m: rf"{m.group('base')}^{{{m.group('exp')}}}", s)
        depth -= 1

    def replace_sqrt(match: re.Match) -> str:
        arg_raw = match.group("arg").strip()
        arg = latex_from_sdamgia_alt(arg_raw, max_depth=max_depth - 1) or _convert_plain_text(arg_raw)
        return rf"\sqrt{{{arg}}}"

    depth = max_depth
    while depth > 0 and _SQRT_RE.search(s):
        s = _SQRT_RE.sub(replace_sqrt, s)
        depth -= 1

    depth = max_depth
    while depth > 0 and _SQRT_FALLBACK_RE.search(s):
        s = _SQRT_FALLBACK_RE.sub(replace_sqrt, s)
        depth -= 1

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
    return sanitize_math_latex(s)
