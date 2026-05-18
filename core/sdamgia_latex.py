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
    s = re.sub(r"гра-\s*дус(?P<suffix>ах|ов|а)?", lambda m: "градус" + (m.group("suffix") or ""), s, flags=re.IGNORECASE)
    s = re.sub(r"граду-\s*с(?P<suffix>ах|ов|а)?", lambda m: "градус" + (m.group("suffix") or ""), s, flags=re.IGNORECASE)
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

_SQRT_SIMPLE_RE = re.compile(
    r"(?:корень\s*из)\s*(?P<arg>-?\d+(?:[.,]\d+)?|[0-9a-zA-Zа-яА-Я]+)",
    flags=re.IGNORECASE,
)

_DEGREE_WORD_RE = re.compile(
    r"(?P<num>-?\d+(?:[.,]\d+)?)\s*(?:градус(?:ов|а)?|градусов|градуса)",
    flags=re.IGNORECASE,
)

_TRIG_WORD_RE = re.compile(
    r"\b(?P<fn>синус|синуса|косинус|косинуса|тангенс|тангенса|котангенс|котангенса|sin|cos|tan|tg|ctg|cot)\s*(?P<arg>[A-Za-zА-Яа-я])\b",
    flags=re.IGNORECASE,
)

_INFINITY_WORD_RE = re.compile(
    r"(?P<sign>[+\-−])?\s*бесконечност[ьи]\b",
    flags=re.IGNORECASE,
)

_GREEK_RU_REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?<!\\)\bальфа\b", flags=re.IGNORECASE), r"\alpha"),
    (re.compile(r"(?<!\\)\bбета\b", flags=re.IGNORECASE), r"\beta"),
    (re.compile(r"(?<!\\)\bгамма\b", flags=re.IGNORECASE), r"\gamma"),
    (re.compile(r"(?<!\\)\bдельта\b", flags=re.IGNORECASE), r"\delta"),
    (re.compile(r"(?<!\\)\bэпсилон\b", flags=re.IGNORECASE), r"\epsilon"),
    (re.compile(r"(?<!\\)\bзета\b", flags=re.IGNORECASE), r"\zeta"),
    (re.compile(r"(?<!\\)\bэта\b", flags=re.IGNORECASE), r"\eta"),
    (re.compile(r"(?<!\\)\bтета\b", flags=re.IGNORECASE), r"\theta"),
    (re.compile(r"(?<!\\)\bйота\b", flags=re.IGNORECASE), r"\iota"),
    (re.compile(r"(?<!\\)\bкаппа\b", flags=re.IGNORECASE), r"\kappa"),
    (re.compile(r"(?<!\\)\bлямбда\b", flags=re.IGNORECASE), r"\lambda"),
    (re.compile(r"(?<!\\)\bламбда\b", flags=re.IGNORECASE), r"\lambda"),
    (re.compile(r"(?<!\\)\bмю\b", flags=re.IGNORECASE), r"\mu"),
    (re.compile(r"(?<!\\)\bню\b", flags=re.IGNORECASE), r"\nu"),
    (re.compile(r"(?<!\\)\bкси\b", flags=re.IGNORECASE), r"\xi"),
    (re.compile(r"(?<!\\)\bомикрон\b", flags=re.IGNORECASE), r"o"),
    (re.compile(r"(?<!\\)\bпи\b", flags=re.IGNORECASE), r"\pi"),
    (re.compile(r"(?<!\\)\bро\b", flags=re.IGNORECASE), r"\rho"),
    (re.compile(r"(?<!\\)\bсигма\b", flags=re.IGNORECASE), r"\sigma"),
    (re.compile(r"(?<!\\)\bтау\b", flags=re.IGNORECASE), r"\tau"),
    (re.compile(r"(?<!\\)\bипсилон\b", flags=re.IGNORECASE), r"\upsilon"),
    (re.compile(r"(?<!\\)\bфи\b", flags=re.IGNORECASE), r"\varphi"),
    (re.compile(r"(?<!\\)\bпси\b", flags=re.IGNORECASE), r"\psi"),
    (re.compile(r"(?<!\\)\bхи\b", flags=re.IGNORECASE), r"\chi"),
    (re.compile(r"(?<!\\)\bомега\b", flags=re.IGNORECASE), r"\omega"),
]

_TRIG_RU_TOKEN_REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?<![A-Za-zА-Яа-я\\])синус(?:а)?\b", flags=re.IGNORECASE), r"\sin"),
    (re.compile(r"(?<![A-Za-zА-Яа-я\\])косинус(?:а)?\b", flags=re.IGNORECASE), r"\cos"),
    (re.compile(r"(?<![A-Za-zА-Яа-я\\])тангенс(?:а)?\b", flags=re.IGNORECASE), r"\tan"),
    (re.compile(r"(?<![A-Za-zА-Яа-я\\])котангенс(?:а)?\b", flags=re.IGNORECASE), r"\cot"),
]

_TRIG_LAT_TOKEN_REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?<![A-Za-z\\])sin\b", flags=re.IGNORECASE), r"\sin"),
    (re.compile(r"(?<![A-Za-z\\])cos\b", flags=re.IGNORECASE), r"\cos"),
    (re.compile(r"(?<![A-Za-z\\])tan\b", flags=re.IGNORECASE), r"\tan"),
    (re.compile(r"(?<![A-Za-z\\])tg\b", flags=re.IGNORECASE), r"\tan"),
    (re.compile(r"(?<![A-Za-z\\])ctg\b", flags=re.IGNORECASE), r"\cot"),
    (re.compile(r"(?<![A-Za-z\\])cot\b", flags=re.IGNORECASE), r"\cot"),
]

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

    s = (
        str(value)
        .replace("\u00ad", "")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\xa0", " ")
    )

    s = s.replace("°", r"^{\circ}")

    s = re.sub(r"\bв\s*степени\b", "степени", s, flags=re.IGNORECASE)
    s = re.sub(r"\bвстепени\b", "степени", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<=[0-9a-zA-Zа-яА-Я\)\]\}])\s*в\s*(?=\^)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<=[0-9a-zA-Zа-яА-Я\)\]\}])в(?=\^)", "", s, flags=re.IGNORECASE)

    for pattern, repl in _GREEK_RU_REPLACEMENTS:
        s = pattern.sub(lambda _m, r=repl: r, s)
    for pattern, repl in _TRIG_RU_TOKEN_REPLACEMENTS:
        s = pattern.sub(lambda _m, r=repl: r, s)
    for pattern, repl in _TRIG_LAT_TOKEN_REPLACEMENTS:
        s = pattern.sub(lambda _m, r=repl: r, s)

    s = _DEGREE_WORD_RE.sub(lambda m: rf"{m.group('num')}^{{\circ}}", s)

    def fix_broken_frac_extra_brace(text: str) -> str:
        out = []
        i = 0
        n = len(text)
        while i < n:
            j = text.find(r"\frac{", i)
            if j == -1:
                out.append(text[i:])
                break
            out.append(text[i:j])
            out.append(r"\frac{")
            k = j + len(r"\frac{")
            depth = 1
            while k < n and depth > 0:
                ch = text[k]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                out.append(ch)
                k += 1
            if k + 1 < n and text[k] == "}" and text[k + 1] == "{":
                k += 1
            i = k
        return "".join(out)

    def fix_tfrac(match: re.Match) -> str:
        digits = match.group(1)
        num = digits[:1]
        den = digits[1:]
        if not den:
            return match.group(0)
        return rf"\frac{{{num}}}{{{den}}}"

    s = fix_broken_frac_extra_brace(s)
    s = _SPACED_TFRAC_RE.sub(lambda m: rf"\frac{{{m.group(1)}}}{{{m.group(2)}}}", s)
    s = _COMPACT_TFRAC_RE.sub(fix_tfrac, s)

    s = _POWER_PAREN_RE.sub(lambda m: rf"({m.group('base')})^{{{m.group('exp')}}}", s)
    s = _POWER_SIMPLE_RE.sub(lambda m: rf"{m.group('base')}^{{{m.group('exp')}}}", s)

    s = s.replace(r"\left(", "(").replace(r"\right)", ")")
    s = s.replace(r"\left[", "[").replace(r"\right]", "]")
    s = s.replace(r"\left\{", r"\{").replace(r"\right\}", r"\}")
    s = s.replace(r"\left.", "").replace(r"\right.", "")
    s = s.replace(r"\left", "").replace(r"\right", "")

    if s.endswith(")") and "(" not in s:
        s = s[:-1].rstrip()

    open_braces = s.count("{")
    close_braces = s.count("}")
    if open_braces > close_braces:
        s = s + ("}" * (open_braces - close_braces))

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

    s = _DEGREE_WORD_RE.sub(lambda m: rf"{m.group('num')}^{{\circ}}", s)
    def _trig(m: re.Match) -> str:
        fn = m.group("fn").lower()
        if fn.startswith("синус") or fn == "sin":
            cmd = r"\sin"
        elif fn.startswith("косинус") or fn == "cos":
            cmd = r"\cos"
        elif fn.startswith("тангенс") or fn in {"tan", "tg"}:
            cmd = r"\tan"
        else:
            cmd = r"\cot"
        return rf"{cmd} {m.group('arg')}"

    s = _TRIG_WORD_RE.sub(_trig, s)
    s = _INFINITY_WORD_RE.sub(lambda m: (r"-\infty" if (m.group("sign") or "").strip() in {"-", "−"} else r"\infty"), s)

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

    depth = max_depth
    while depth > 0 and _SQRT_SIMPLE_RE.search(s):
        s = _SQRT_SIMPLE_RE.sub(replace_sqrt, s)
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
