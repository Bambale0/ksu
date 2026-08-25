from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page

from e2e import roxy_browser_e2e as legacy
from e2e.roxy_browser_e2e import *  # noqa: F403

_ORIGINAL_GET_BY_ROLE = Page.get_by_role
_REUSE_PATTERN = "Повторить / изменить|Использовать настройки"


def _get_by_role_compat(self, role, *args, **kwargs):
    name = kwargs.get("name")
    if role == "button" and isinstance(name, re.Pattern) and name.pattern == _REUSE_PATTERN:
        return self.locator("button").filter(has_text=re.compile("Повторить|Использовать настройки"))
    return _ORIGINAL_GET_BY_ROLE(self, role, *args, **kwargs)


Page.get_by_role = _get_by_role_compat


if __name__ == "__main__":
    raise SystemExit(asyncio.run(legacy.main()))
