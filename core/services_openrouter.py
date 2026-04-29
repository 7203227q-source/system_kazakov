import json
import re


def parse_openrouter_json(text):
    if text is None:
        raise ValueError("Empty response")

    if isinstance(text, dict):
        data = text
    else:
        raw = str(text).strip()
        try:
            data = json.loads(raw)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                raise ValueError("No JSON object found in response")
            data = json.loads(match.group(0))

    content_html = data.get("content_html")
    solution_html = data.get("solution_html")
    correct_answer = data.get("correct_answer")

    if content_html is None and solution_html is None and correct_answer is None:
        raise ValueError("JSON does not contain expected fields")

    return {
        "content_html": content_html or "",
        "solution_html": solution_html or "",
        "correct_answer": correct_answer or "",
        "notes": data.get("notes", "") or "",
    }

