from __future__ import annotations

import re
import unicodedata

EMAIL_ERROR = "Введите корректный email латинскими символами, без пробелов и эмодзи"

_INVISIBLE_EMAIL_CHARS = dict.fromkeys(
    map(ord, "\u200b\u200c\u200d\ufeff\u2060"),
    None,
)
_EMAIL_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2043": "-",
        "\u2212": "-",
        "\ufe58": "-",
        "\ufe63": "-",
        "\uff0d": "-",
        "\u3002": ".",
        "\uff0e": ".",
        "\uff61": ".",
        "\ufe6b": "@",
        "\uff20": "@",
    }
)
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def normalize_billing_email(value: str) -> str:
    """Normalize mobile-keyboard Unicode lookalikes before Lava checkout."""
    email = unicodedata.normalize("NFKC", value or "")
    email = email.translate(_EMAIL_TRANSLATION)
    email = email.translate(_INVISIBLE_EMAIL_CHARS)
    return email.strip().lower()


def validate_billing_email(value: str) -> str:
    email = normalize_billing_email(value)
    if not email or len(email) > 254 or email.count("@") != 1:
        raise ValueError(EMAIL_ERROR)
    if any(char.isspace() for char in email):
        raise ValueError(EMAIL_ERROR)
    try:
        email.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(EMAIL_ERROR) from exc
    if not _EMAIL_RE.fullmatch(email):
        raise ValueError(EMAIL_ERROR)
    return email
