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
        if not brs:
            continue

        if len(brs) < br_threshold:
            block_modified = False

            for br in brs:
                prev_text = ""
                cur = br.previous_sibling
                while cur is not None and not prev_text:
                    prev_text = cur.strip() if isinstance(cur, str) else cur.get_text(" ", strip=True)
                    cur = cur.previous_sibling

                next_text = ""
                cur = br.next_sibling
                while cur is not None and not next_text:
                    next_text = cur.strip() if isinstance(cur, str) else cur.get_text(" ", strip=True)
                    cur = cur.next_sibling

                if not prev_text or not next_text:
                    continue

                if re.match(r"^(?:[0-9]+|[a-zа-я])\)", next_text, flags=re.IGNORECASE):
                    continue

                if prev_text.rstrip().endswith(","):
                    br.replace_with(" ")
                    block_modified = True

            if block_modified:
                if not any(tag.name != "br" for tag in block.find_all(True)):
                    normalized_text = re.sub(r"[ \t\r\n]+", " ", block.get_text(separator=" ", strip=True))
                    block.clear()
                    block.append(normalized_text)
                modified = True
            continue

        for br in brs:
            br.replace_with(" ")

        normalized_text = re.sub(r"[ \t\r\n]+", " ", block.get_text(separator=" ", strip=True))
        block.clear()
        block.append(normalized_text)
        modified = True

    return str(soup) if modified else html
