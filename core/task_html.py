import re

from bs4 import BeautifulSoup

DEFAULT_BR_THRESHOLD = 8


def normalize_task_html(html: str, *, br_threshold: int = DEFAULT_BR_THRESHOLD) -> str:
    if not html:
        return html

    soup = BeautifulSoup(html, "html.parser")
    modified = False

    for block in soup.find_all(["p", "div", "span"]):
        if block.find(["ul", "ol", "li", "table", "tr", "td", "th", "pre", "code"]):
            continue

        brs = block.find_all("br")
        if len(brs) < br_threshold:
            continue

        for br in brs:
            br.replace_with(" ")

        normalized_text = re.sub(r"[ \t\r\n]+", " ", block.get_text(separator=" ", strip=True))
        block.clear()
        block.append(normalized_text)
        modified = True

    return str(soup) if modified else html
