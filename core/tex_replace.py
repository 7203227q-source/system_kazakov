import re

from bs4 import BeautifulSoup
from bs4.element import NavigableString

from core.sdamgia_latex import latex_from_sdamgia_alt, sanitize_math_latex


_RU_TRIG_RE = re.compile(
    r"\b(?P<fn>синус|синуса|косинус|косинуса|тангенс|тангенса|котангенс|котангенса)\s*(?P<arg>(?:∠)?[A-Za-zА-Яа-я])\b",
    flags=re.IGNORECASE,
)

_LAT_TRIG_RE = re.compile(
    r"(?<![A-Za-z\\])(?P<fn>sin|cos|tan|tg|ctg|cot)\s*(?P<arg>(?:∠)?[A-Za-z])\b",
    flags=re.IGNORECASE,
)

_DEG_WORD_HTML_RE = re.compile(
    r"(?P<num>-?\d+(?:[.,]\d+)?)\s*градус(?:ов|а)?",
    flags=re.IGNORECASE,
)

_INF_WORD_HTML_RE = re.compile(
    r"(?P<sign>[+\-−])?\s*бесконечност[ьи]\b",
    flags=re.IGNORECASE,
)

_DEG_HYPHENATION_RE = re.compile(
    r"гра-\s*дус(?P<suffix>ах|ов|а)?",
    flags=re.IGNORECASE,
)

_DEG_HYPHENATION_RE2 = re.compile(
    r"граду-\s*с(?P<suffix>ах|ов|а)?",
    flags=re.IGNORECASE,
)


def fix_math_words_in_html(html: str) -> tuple[str, int]:
    if not html:
        return html, 0
    lower = html.lower()
    if not any(
        k in lower
        for k in [
            "градус",
            "гра-",
            "граду-",
            "бесконечност",
            "синус",
            "косинус",
            "тангенс",
            "котангенс",
            " sin",
            " cos",
            " tg",
            "ctg",
            " tan",
        ]
    ):
        return html, 0

    soup = BeautifulSoup(html, "html.parser")
    changed = 0

    excluded = {"script", "style", "math", "svg"}
    for node in list(soup.descendants):
        if not isinstance(node, NavigableString):
            continue
        parent = getattr(node, "parent", None)
        if parent is not None and getattr(parent, "name", None) in excluded:
            continue
        text = str(node)
        if not text.strip():
            continue
        if "$" in text or "\\(" in text or "\\[" in text:
            continue

        original = text

        text = (
            text.replace("\u00ad", "")
            .replace("\u200b", "")
            .replace("\ufeff", "")
            .replace("\xa0", " ")
        )
        text = _DEG_HYPHENATION_RE.sub(lambda m: "градус" + (m.group("suffix") or ""), text)
        text = _DEG_HYPHENATION_RE2.sub(lambda m: "градус" + (m.group("suffix") or ""), text)

        def trig_ru(m: re.Match) -> str:
            fn = m.group("fn").lower()
            arg = (m.group("arg") or "").lstrip("∠")
            if fn.startswith("синус"):
                cmd = r"\sin"
            elif fn.startswith("косинус"):
                cmd = r"\cos"
            elif fn.startswith("тангенс"):
                cmd = r"\tan"
            else:
                cmd = r"\cot"
            return rf"${cmd} {arg}$"

        def trig_lat(m: re.Match) -> str:
            fn = m.group("fn").lower()
            arg = (m.group("arg") or "").lstrip("∠")
            if fn in {"sin"}:
                cmd = r"\sin"
            elif fn in {"cos"}:
                cmd = r"\cos"
            elif fn in {"tan", "tg"}:
                cmd = r"\tan"
            else:
                cmd = r"\cot"
            return rf"${cmd} {arg}$"

        def inf(m: re.Match) -> str:
            sign = (m.group("sign") or "").strip()
            if sign in {"-", "−"}:
                return r"$-\infty$"
            return r"$\infty$"

        text = _RU_TRIG_RE.sub(trig_ru, text)
        text = _LAT_TRIG_RE.sub(trig_lat, text)
        text = _DEG_WORD_HTML_RE.sub(lambda m: rf"${m.group('num')}^{{\circ}}$", text)
        text = _INF_WORD_HTML_RE.sub(inf, text)

        if text != original:
            node.replace_with(NavigableString(text))
            changed += 1

    return str(soup), changed


def replace_svg_images_with_latex(html: str) -> tuple[str, int]:
    if not html:
        return html, 0

    soup = BeautifulSoup(html, "html.parser")
    replaced = 0

    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        classes = img.get("class") or []
        class_joined = " ".join(classes) if isinstance(classes, (list, tuple)) else str(classes)
        if (
            ".svg" not in src
            and "formula/svg" not in src
            and "/formula/" not in src
            and "tex" not in class_joined.split()
        ):
            continue
        alt = img.get("alt") or ""
        latex = latex_from_sdamgia_alt(alt)
        if not latex:
            continue
        img.replace_with(NavigableString(f"${latex}$"))
        replaced += 1

    return str(soup), replaced


def fix_latex_tokens_in_html(html: str) -> tuple[str, int]:
    if not html:
        return html, 0

    soup = BeautifulSoup(html, "html.parser")
    fixed = 0

    def convert_or_sanitize_math(expr: str) -> str:
        lowered = expr.lower()
        if any(
            k in lowered
            for k in [
                "целаячасть",
                "целая часть",
                "дробнаячасть",
                "дробная часть",
                "числитель",
                "знаменатель",
                "больше",
                "меньше",
                "степени",
                "в степени",
                "встепени",
                "кореньиз",
                "корень из",
                "началоаргумента",
                "начало аргумента",
                "конецаргумента",
                "конец аргумента",
            ]
        ):
            converted = latex_from_sdamgia_alt(expr)
            if converted:
                return converted
        return sanitize_math_latex(expr)

    def fix_delimited(text: str) -> tuple[str, int]:
        local_fixed = 0

        def repl_paren(m):
            nonlocal local_fixed
            inner = m.group(1)
            out = convert_or_sanitize_math(inner)
            if out != inner:
                local_fixed += 1
            return rf"\({out}\)"

        def repl_brack(m):
            nonlocal local_fixed
            inner = m.group(1)
            out = convert_or_sanitize_math(inner)
            if out != inner:
                local_fixed += 1
            return rf"\[{out}\]"

        text2 = re.sub(r"\\\((.*?)\\\)", repl_paren, text, flags=re.DOTALL)
        text3 = re.sub(r"\\\[(.*?)\\\]", repl_brack, text2, flags=re.DOTALL)
        return text3, local_fixed

    for node in list(soup.descendants):
        if not isinstance(node, NavigableString):
            continue
        text = str(node)
        if "$" not in text and "\\(" not in text and "\\[" not in text:
            continue

        out = []
        changed = False

        text, fixed_here = fix_delimited(text)
        if fixed_here:
            fixed += fixed_here
            changed = True
        parts = text.split("$")
        for i, part in enumerate(parts):
            if i % 2 == 1:
                sanitized = sanitize_math_latex(part)
                if sanitized != part:
                    out.append(sanitized)
                    fixed += 1
                    changed = True
                    continue
                if "\\tfrac" in part:
                    fixed_part = latex_from_sdamgia_alt(part)
                    if fixed_part and fixed_part != part:
                        out.append(fixed_part)
                        fixed += 1
                        changed = True
                        continue
                if any(
                    k in part.lower()
                    for k in [
                        "целаячасть",
                        "целая часть",
                        "дробнаячасть",
                        "дробная часть",
                        "числитель",
                        "знаменатель",
                        "больше",
                        "меньше",
                        "степени",
                        "в степени",
                        "встепени",
                        "кореньиз",
                        "корень из",
                        "началоаргумента",
                        "начало аргумента",
                        "конецаргумента",
                        "конец аргумента",
                    ]
                ):
                    converted = latex_from_sdamgia_alt(part)
                    if converted:
                        out.append(converted)
                        fixed += 1
                        changed = True
                        continue
            out.append(part)

        if changed:
            node.replace_with(NavigableString("$".join(out)))

    return str(soup), fixed
    return str(soup), fixed
