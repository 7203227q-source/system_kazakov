from django import template

from core.greetings import get_time_greeting

register = template.Library()


@register.simple_tag
def time_greeting():
    return get_time_greeting()
