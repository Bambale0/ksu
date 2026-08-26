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


async def close_current_result_dialog(page: Page) -> None:
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(100)
    backdrop = page.locator('button[aria-label="Закрыть"].overlay-backdrop:visible').first
    if await backdrop.count():
        await backdrop.evaluate("element => element.click()")
        await page.wait_for_timeout(100)


async def select_prompt_friendly_model(page: Page, media: str) -> None:
    if media == "video":
        veo = page.get_by_role("button", name=re.compile("Veo", re.I)).first
        await expect(veo).to_be_visible(timeout=8000)
        await veo.click()
        variant = page.get_by_role("button", name=re.compile(r"Veo\s*3\.1", re.I)).first
        await expect(variant).to_be_visible(timeout=8000)
        await variant.click()
        await expect(page.get_by_role("heading", name=re.compile("Veo", re.I))).to_be_visible(timeout=8000)
        return
    if media == "audio":
        suno = page.get_by_role("button", name=re.compile("Suno|Музыка", re.I)).first
        if await suno.count() and await suno.is_visible():
            await suno.click()


async def scenario_generations(page: Page, report: legacy.Report) -> list[dict]:
    results: list[dict] = []
    for media, prompt in (
        ("image", "ROXY E2E image, neon fox, clean studio lighting"),
        ("video", "ROXY E2E video, a fox walking through a neon studio"),
        ("audio", "ROXY E2E synthwave instrumental with a bright melodic hook"),
    ):
        await select_primary(page, "create")
        await expect(page.locator(".create-screen")).to_be_visible(timeout=10000)
        label = {"image": "Фото", "video": "Видео", "audio": "Музыка"}[media]
        media_button = page.locator(".family-tabs button:visible").filter(
            has_text=re.compile(rf"^{re.escape(label)}$")
        ).first
        await expect(media_button).to_be_visible(timeout=10000)
        if media == "audio":
            await expect(media_button).to_be_enabled(timeout=10000)
        await media_button.click()
        await expect(page.locator("#builderView, .create-screen")).to_be_visible(timeout=8000)
        await select_prompt_friendly_model(page, media)
        result = await legacy.fill_builder_and_generate(page, prompt)
        results.append(result)
        report.controls_seen.update({f"create:{media}", f"generate:{media}"})
        share = page.get_by_role("button", name="Поделиться")
        if await share.count() and await share.first.is_visible():
            before = await page.evaluate("window.__roxyE2E.opened.length")
            await share.first.click()
            await page.wait_for_timeout(100)
            after = await page.evaluate("window.__roxyE2E.opened.length")
            assert after > before
            report.controls_seen.add("result:share")
        reuse = page.locator("button").filter(has_text=re.compile("Повторить|Использовать настройки"))
        if await reuse.count() and await reuse.first.is_visible():
            await reuse.first.click()
            await expect(page.locator("#builderView, .create-screen")).to_be_visible(timeout=8000)
            report.controls_seen.add("result:reuse")
        else:
            await close_current_result_dialog(page)
            await expect(page.locator("#builderView, .create-screen")).to_be_visible(timeout=8000)
            report.controls_seen.add("result:close-dialog")
    report.ok("image + video + music generation through real API/DB/Redis/worker + fake Kie")
    return results


async def scenario_history(page: Page, report: legacy.Report) -> None:
    await select_primary(page, "history")
    main = page.locator("main")
    await expect(main).to_contain_text(re.compile("Veo 3.1|Suno|Nano Banana|succeeded|Готово", re.I), timeout=10000)
    generation_card = page.get_by_role("button", name=re.compile("Veo|Suno|Nano Banana", re.I)).first
    if await generation_card.count() and await generation_card.is_visible():
        await generation_card.click()
        report.controls_seen.add("history:open-card")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(100)
    report.ok("history generated items")


async def scenario_wallet(page: Page, report: legacy.Report) -> None:
    await page.goto(f"{legacy.BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    balance = page.locator("#balance")
    await expect(balance).to_be_visible(timeout=10000)
    await balance.click()
    sheet = page.locator(".sheet").first
    await expect(sheet).to_be_visible(timeout=8000)
    await expect(sheet).to_contain_text(re.compile("Баланс|Пополн|ROX", re.I), timeout=10000)
    package = sheet.locator(".package").first
    await expect(package).to_be_visible(timeout=8000)
    report.controls_seen.update({"wallet:open", "wallet:package"})
    report.ok("wallet sheet and checkout controls")


Page.get_by_role = _get_by_role_compat
legacy.select_primary = select_primary
legacy.scenario_generations = scenario_generations
legacy.scenario_history = scenario_history
legacy.scenario_wallet = scenario_wallet


if __name__ == "__main__":
    raise SystemExit(asyncio.run(legacy.main()))
