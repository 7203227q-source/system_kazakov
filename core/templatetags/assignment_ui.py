from django import template

register = template.Library()

_PALETTE = [
    ("#EEF2FF", "#4F46E5"),
    ("#ECFDF5", "#10B981"),
    ("#FFF7ED", "#F97316"),
    ("#FDF2F8", "#DB2777"),
    ("#EFF6FF", "#2563EB"),
    ("#F5F3FF", "#7C3AED"),
    ("#FFFBEB", "#D97706"),
    ("#F0FDFA", "#0D9488"),
]


@register.filter
def assignment_code(student_seq):
    try:
        n = int(student_seq or 0)
    except Exception:
        n = 0
    if n <= 0:
        return ""
    return f"#{n:03d}"


@register.filter
def assignment_color(student_seq):
    try:
        n = int(student_seq or 0)
    except Exception:
        n = 0
    if n <= 0:
        return {"bg": "#E5E7EB", "fg": "#6B7280"}
    bg, fg = _PALETTE[n % len(_PALETTE)]
    return {"bg": bg, "fg": fg}
