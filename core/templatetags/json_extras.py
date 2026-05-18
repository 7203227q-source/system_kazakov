import json

from django import template

register = template.Library()


@register.filter
def json_load(value):
    """
    Безопасный json.loads для шаблонов.
    Возвращает list/dict или [] при ошибке/пустом значении.
    """
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return []

