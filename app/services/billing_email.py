from __future__ import annotations

import re

# Telegram/WebView/mobile keyboards sometimes insert Unicode dash variants
# that look like a regular ASCII hyphen. Payment providers usually validate
# e-mail addresses against ASCII-only rules, so normalize them before checkout.
_EMAIL_DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",  # hyphen
        "\u2011": "-",  # non-breaking hyphen
        "\u2012": "-",  # figure dash
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2212": "-",  # minus sign
    }
)

_EMAIL_RE = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)

_ERROR = "Введите корректный email для чека и платёжной страницы"


def normalize_billing_email(value: str) -> str:
    email = value.strip().translate(_EMAIL_DASH_TRANSLATION).lower()
    if (
        not email
        or len(email) > 254
        or " " in email
        or email.count("@") != 1
        or not _EMAIL_RE.fullmatch(email)
    ):
        raise ValueError(_ERROR)
    return email
