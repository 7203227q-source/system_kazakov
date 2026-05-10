import re

from bs4 import BeautifulSoup
from bs4.element import NavigableString

from core.sdamgia_latex import latex_from_sdamgia_alt, sanitize_math_latex


def replace_svg_images_with_latex(html: str) -> tuple[str, int]:
    if not html:
        return html, 0

    soup = BeautifulSoup(html, "html.parser")
    replaced = 0

    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if ".svg" not in src:
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
