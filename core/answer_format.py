import re
from math import gcd


_EXACT_FRACTION_RE = re.compile(r"^\s*([+-]?\d+)\s*/\s*([+-]?\d+)\s*$")
_NOTES_EXACT_RE = re.compile(r"(?:^|\s)exact_fraction\s*=\s*([+-]?\d+\s*/\s*[+-]?\d+)(?:\s|$)")


def _strip_trailing_zeros_decimal(s: str) -> str:
    if "." not in s:
        return s
    s = s.rstrip("0").rstrip(".")
    return s or "0"


def extract_exact_fraction(notes: str) -> str:
    m = _NOTES_EXACT_RE.search(notes or "")
    if not m:
        raise ValueError("exact_fraction not found in notes")
    return m.group(1)


def exact_fraction_to_decimal_str(frac: str) -> str:
    m = _EXACT_FRACTION_RE.match(frac or "")
    if not m:
        raise ValueError("Invalid exact_fraction format")

    a = int(m.group(1))
    b = int(m.group(2))
    if b == 0:
        raise ValueError("Division by zero")
    if b < 0:
        a = -a
        b = -b

    g = gcd(abs(a), b)
    a //= g
    b //= g

    if b == 1:
        return str(a)

    bb = b
    while bb % 2 == 0:
        bb //= 2
    while bb % 5 == 0:
        bb //= 5
    if bb != 1:
        raise ValueError("Non-terminating decimal")

    k2 = 0
    bb2 = b
    while bb2 % 2 == 0:
        bb2 //= 2
        k2 += 1

    k5 = 0
    bb5 = b
    while bb5 % 5 == 0:
        bb5 //= 5
        k5 += 1

    k = max(k2, k5)
    mul = (2 ** (k - k2)) * (5 ** (k - k5))
    num = a * mul
    den = b * mul

    sign = "-" if num < 0 else ""
    num_abs = abs(num)

    int_part = num_abs // den
    frac_part = num_abs % den

    frac_str = str(frac_part).rjust(k, "0")
    out = f"{sign}{int_part}.{frac_str}"
    return _strip_trailing_zeros_decimal(out)


def normalize_regen_correct_answer(*, notes: str) -> str:
    frac = extract_exact_fraction(notes)
    return exact_fraction_to_decimal_str(frac)

