from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page, expect

from e2e import roxy_browser_e2e as legacy
from e2e.roxy_browser_e2e import *  # noqa: F403

_ORIGINAL_GET_BY_ROLE = Page.get_by_role
_REUSE_PATTERN = "Повторить / изменить|Использовать настройки"


def _get_by_role_compat(self, role, *args, **kwargs):
    name = kwargs.get("name")
    if role == "button" and isinstance(name, re.Pattern) and name.pattern == _REUSE_PATTERN:
        return self.locator("button").filter(has_text=re.compile("Повторить|Использовать настройки"))
    return _ORIGINAL_GET_BY_ROLE(self, role, *args, **kwargs)


async def select_primary(page: Page, route: str) -> None:
    target = page.locator(f'[data-roxy-customer-route="{route}"]:visible').first
    try:
        await expect(target).to_be_visible(timeout=10000)
        await target.click()
        await expect(page).to_have_url(re.compile(rf"[?&]route={re.escape(route)}(?:&|$)"), timeout=8000)
    except Exception:
        await page.goto(f"{legacy.BASE_URL}/mini-app/?route={route}", wait_until="domcontentloaded")
        await expect(page).to_have_url(re.compile(rf"[?&]route={re.escape(route)}(?:&|$)"), timeout=8000)


Page.get_by_role = _get_by_role_compat
legacy.select_primary = select_primary


if __name__ == "__main__":
    raise SystemExit(asyncio.run(legacy.main()))
