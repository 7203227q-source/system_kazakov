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

