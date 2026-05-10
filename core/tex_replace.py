from bs4 import BeautifulSoup
from bs4.element import NavigableString

from core.sdamgia_latex import latex_from_sdamgia_alt


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

    for node in list(soup.descendants):
        if not isinstance(node, NavigableString):
            continue
        text = str(node)
        if "$" not in text:
            continue

        out = []
        changed = False
        parts = text.split("$")
        for i, part in enumerate(parts):
            if i % 2 == 1:
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
