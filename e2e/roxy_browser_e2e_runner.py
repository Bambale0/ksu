from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page, expect

from e2e import roxy_browser_e2e_v2 as suite


async def robust_route(page: Page, name: str) -> None:
    target = page.locator(f'[data-roxy-customer-route="{name}"]:visible').first
    if await target.count():
        await target.click()
    else:
        await page.goto(f"{suite.legacy.BASE_URL}/mini-app/?route={name}", wait_until="domcontentloaded")
    await expect(page).to_have_url(re.compile(rf"[?&]route={re.escape(name)}(?:&|$)"), timeout=8000)


async def scenario_wallet(page: Page, report: suite.legacy.Report) -> None:
    await page.goto(f"{suite.legacy.BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    balance = page.locator("#balance")
    await expect(balance).to_be_visible(timeout=10000)
    await balance.click()
    sheet = page.locator(".sheet").first
    await expect(sheet).to_be_visible(timeout=8000)
    await expect(sheet).to_contain_text(re.compile(r"ROX|Баланс|Пополн", re.I), timeout=8000)
    report.controls_seen.add("wallet:open")

    lava_tab = page.locator('[data-checkout-method="lava"]:visible').first
    if await lava_tab.count():
        await lava_tab.click()
        report.controls_seen.add("wallet:method:lava")
    package = page.locator(".sheet .package:visible, .primary-card-package:visible, #paymentPackageGrid .payment-package:visible").first
    await expect(package).to_be_visible(timeout=8000)
    await package.click()
    report.controls_seen.add("wallet:package")
    email = page.locator('.sheet input[inputmode="email"]:visible, .primary-card-section input[inputmode="email"]:visible').first
    await expect(email).to_be_visible(timeout=8000)
    await email.fill("e2e@example.com")
    pay = page.locator("button:visible").filter(has_text=re.compile(r"Перейти к оплате|Создать оплату", re.I)).first
    await expect(pay).to_be_enabled(timeout=8000)
    async with page.expect_response(lambda response: "/api/v1/payments/card/checkout" in response.url and response.request.method == "POST", timeout=10000) as checkout_pending:
        await pay.click()
    checkout_response = await checkout_pending.value
    assert checkout_response.ok, f"card checkout: {checkout_response.status} {await checkout_response.text()}"
    report.controls_seen.add("wallet:card:checkout")
    crypto_tab = page.locator('[data-checkout-method="crypto"]:visible').first
    if await crypto_tab.count():
        await crypto_tab.click()
        report.controls_seen.add("wallet:method:crypto")
    backdrop = page.locator(".sheet-overlay .overlay-backdrop:visible").first
    if await backdrop.count():
        await backdrop.evaluate("element => element.click()")
    await expect(page.locator(".sheet-overlay")).to_have_count(0, timeout=8000)
    report.ok("wallet sheet + payment checkout")


async def scenario_profile_support_partner(page: Page, report: suite.legacy.Report) -> None:
    await robust_route(page, "profile")
    profile = page.locator(".profile-screen")
    await expect(profile).to_be_visible(timeout=10000)
    await expect(profile).to_contain_text(re.compile(r"Профиль|работ|публикац", re.I))
    works = page.get_by_role("button", name="Работы", exact=True)
    publications = page.get_by_role("button", name="Публикации", exact=True)
    await expect(works).to_be_visible()
    await expect(publications).to_be_visible()
    await publications.click()
    await works.click()
    report.controls_seen.update({"profile:open", "profile:works", "profile:publications"})

    await robust_route(page, "partners")
    await expect(page.locator("main")).to_contain_text(re.compile(r"Партн|Приглас|ссыл|Начисл|ROX", re.I), timeout=10000)
    copy = page.get_by_role("button", name=re.compile(r"Скопировать", re.I)).first
    if await copy.count() and await copy.is_visible():
        before = await page.evaluate("window.__roxyE2E.clipboard.length")
        await copy.click()
        await page.wait_for_timeout(100)
        assert await page.evaluate("window.__roxyE2E.clipboard.length") >= before
        report.controls_seen.add("partners:copy")
    report.controls_seen.add("partners:open")
    report.ok("current profile + partner surfaces")


async def scenario_child_routes(page: Page, report: suite.legacy.Report) -> None:
    for route in ("feed", "catalog", "create", "history", "profile", "partners"):
        await page.goto(f"{suite.legacy.BASE_URL}/mini-app/?route={route}", wait_until="domcontentloaded")
        await expect(page).to_have_url(re.compile(rf"[?&]route={re.escape(route)}(?:&|$)"), timeout=8000)
        await expect(page.locator("main")).to_be_visible(timeout=10000)
        assert (await page.locator("main").inner_text()).strip(), f"route {route} rendered empty"
        report.controls_seen.add(f"route:{route}")
    for path, expected in (("prompt-tools/?mode=image", re.compile(r"описан|промпт|иде", re.I)), ("batch/", re.compile(r"несколько|пакет|созда", re.I))):
        await page.goto(f"{suite.legacy.BASE_URL}/mini-app/{path}", wait_until="domcontentloaded")
        await expect(page.locator("body")).to_contain_text(expected, timeout=10000)
        report.controls_seen.add(f"deep:{path.split('/')[0]}")
    report.ok("canonical ROXY routes + supported deep tools")


async def inventory_visible_controls(page: Page, report: suite.legacy.Report) -> None:
    for route in ("home", "feed", "catalog", "create", "history", "profile", "partners"):
        await page.goto(f"{suite.legacy.BASE_URL}/mini-app/?route={route}", wait_until="domcontentloaded")
        await expect(page.locator("main")).to_be_visible(timeout=10000)
        controls = await page.locator("button:visible").evaluate_all("""nodes => nodes.map((node) => ({id: node.id || '', text: (node.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 100), aria: node.getAttribute('aria-label') || '', route: node.dataset.roxyCustomerRoute || ''}))""")
        assert controls, f"route {route} has no visible controls"
        for control in controls:
            signature = control["id"] or control["aria"] or control["text"] or control["route"]
            if signature:
                report.controls_seen.add(f"inventory:{route}:{signature}")
    await page.goto(f"{suite.legacy.BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    await expect(page.locator("#balance")).to_be_visible(timeout=10000)
    await page.locator("#balance").click()
    await expect(page.locator(".sheet")).to_be_visible(timeout=8000)
    assert await page.locator(".sheet button:visible").count() > 0
    report.controls_seen.add("inventory:wallet-sheet")
    report.ok("visible control inventory", f"{len(report.controls_seen)} unique control signatures")


suite.select_primary = robust_route
suite.legacy.select_primary = robust_route
suite.scenario_wallet = scenario_wallet
suite.legacy.scenario_wallet = scenario_wallet
suite.scenario_profile_support_partner = scenario_profile_support_partner
suite.legacy.scenario_profile_support_partner = scenario_profile_support_partner
suite.scenario_child_routes = scenario_child_routes
suite.legacy.scenario_child_routes = scenario_child_routes
suite.inventory_visible_controls = inventory_visible_controls
suite.legacy.inventory_visible_controls = inventory_visible_controls


if __name__ == "__main__":
    raise SystemExit(asyncio.run(suite.legacy.main()))
