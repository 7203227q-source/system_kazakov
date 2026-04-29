def sanitize_header_value(value):
    if value is None:
        return ""
    s = str(value)
    return s.encode("ascii", "ignore").decode("ascii")

