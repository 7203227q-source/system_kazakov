from django import template

from core.datetime_ui import format_ui_datetime

register = template.Library()


@register.filter
def ui_datetime(value):
    return format_ui_datetime(value)

