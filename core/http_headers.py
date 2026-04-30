def sanitize_header_value(value):
    if value is None:
        return ""
    s = str(value)
    return s.encode("ascii", "ignore").decode("ascii")


def require_ascii(value, name):
    try:
        str(value).encode("ascii")
    except Exception:
        raise ValueError(f"{name} must contain only ASCII characters")
