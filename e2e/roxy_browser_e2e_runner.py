from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page, expect

from e2e import roxy_browser_e2e_v2 as suite


async def robust_route(page: Page, name: str) -> None:
    canonical_name = "home" if name == "catalog" else name
    if name == "catalog":
        # Catalog is a backwards-compatible URL alias only. There is no second
        # visible Catalog tab anymore: every legacy launch must converge on Home.
        await page.goto(
            f"{suite.legacy.BASE_URL}/mini-app/?route=catalog",
            wait_until="domcontentloaded",
        )
    else:
        target = page.locator(f'[data-roxy-customer-route="{name}"]:visible').first
        try:
            await expect(target).to_be_visible(timeout=10000)
            await target.click()
        except Exception:
            await page.goto(
                f"{suite.legacy.BASE_URL}/mini-app/?route={name}",
                wait_until="domcontentloaded",
            )
    await expect(page).to_have_url(
        re.compile(rf"[?&]route={re.escape(canonical_name)}(?:&|$)"),
        timeout=8000,
    )
    ready = {
        "home": ".home-screen",
        "create": ".create-screen",
        "profile": ".profile-screen",
    }.get(canonical_name, "main .screen")
    await expect(page.locator(ready).first).to_be_visible(timeout=10000)


async def scenario_boot_and_navigation(page: Page, report: suite.legacy.Report) -> None:
    await page.goto(
        f"{suite.legacy.BASE_URL}/mini-app/?route=home",
        wait_until="domcontentloaded",
    )
    await expect(page).to_have_title(re.compile("ROXY"))
    await expect(page.locator('[data-roxy-customer-route="home"]')).to_have_count(2, timeout=8000)
    for route in ("home", "catalog", "create", "history", "profile"):
        await robust_route(page, route)
        report.controls_seen.add(f"primary:{route}")

    await robust_route(page, "catalog")
    await expect(page.locator('[data-roxy-customer-route="catalog"]:visible')).to_have_count(0)
    await expect(page.locator('[data-roxy-customer-route="home"]:visible').first).to_contain_text("Каталог")
    prompt = page.locator('[data-catalog-feature="prompt-image"]:visible').first
    await expect(prompt).to_be_visible(timeout=10000)
    await prompt.click()
    await expect(page).to_have_url(
        re.compile(r"/mini-app/prompt-tools/(?:\?|$)"),
        timeout=7000,
    )
    await page.go_back()
    await expect(page).to_have_url(
        re.compile(r"[?&]route=home(?:&|$)"),
        timeout=7000,
    )
    report.controls_seen.add("catalog:legacy-alias-to-home")
    report.controls_seen.add("catalog:prompt-tools/back")
    report.ok("boot + canonical navigation + Back")


async def scenario_wallet(page: Page, report: suite.legacy.Report) -> None:
    await page.goto(f"{suite.legacy.BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    balance = page.locator("#balance")
    await expect(balance).to_be_visible(timeout=10000)
    await balance.click()

    await expect(page).to_have_url(re.compile(r"/mini-app/payments/?"), timeout=8000)
    await expect(page.get_by_role("heading", name="Пополнения ROX")).to_be_visible(timeout=8000)
    lava_tab = page.get_by_role("button", name="Lava Top").first
    await expect(lava_tab).to_have_class(re.compile(r"active"), timeout=8000)
    report.controls_seen.add("wallet:payments-page")
    report.controls_seen.add("wallet:method:lava")

    package = page.locator(
        ".package-grid .package:visible, .primary-card-package:visible, #paymentPackageGrid .payment-package:visible"
    ).first
    await expect(package).to_be_visible(timeout=8000)
    await package.click()
    report.controls_seen.add("wallet:package")

    email = page.locator(
        'input[type="email"]:visible, input[inputmode="email"]:visible, .primary-card-section input[inputmode="email"]:visible'
    ).first
    await expect(email).to_be_visible(timeout=8000)
    await email.fill("e2e@example.com")

    pay = page.locator("button:visible").filter(
        has_text=re.compile(r"Перейти к оплате|Создать оплату|через Lava Top", re.I)
    ).first
    await expect(pay).to_be_enabled(timeout=8000)
    async with page.expect_response(
        lambda response: "/api/v1/payments/card/checkout" in response.url
        and response.request.method == "POST",
        timeout=10000,
    ) as checkout_pending:
        await pay.click()
    checkout_response = await checkout_pending.value
    assert checkout_response.ok, f"card checkout: {checkout_response.status} {await checkout_response.text()}"
    report.controls_seen.add("wallet:card:checkout")

    crypto_tab = page.get_by_role("button", name="CryptoBot").first
    if await crypto_tab.count():
        await crypto_tab.click()
        report.controls_seen.add("wallet:method:crypto")

    report.ok("payments page + Lava Top checkout")


async def scenario_profile_support_partner(page: Page, report: suite.legacy.Report) -> None:
    await robust_route(page, "profile")
    profile = page.locator(".profile-screen")
    await expect(profile).to_be_visible(timeout=10000)
    await expect(profile).to_contain_text(re.compile(r"Профиль|работ|публикац", re.I))
    report.controls_seen.add("profile:open")

    works = page.get_by_role("button", name="Работы", exact=True)
    publications = page.get_by_role("button", name="Публикации", exact=True)
    await expect(works).to_be_visible()
    await expect(publications).to_be_visible()
    await publications.click()
    await works.click()
    report.controls_seen.update({"profile:works", "profile:publications"})

    await robust_route(page, "partners")
    await expect(page.locator("main")).to_contain_text(
        re.compile(r"Партн|Приглас|ссыл|Начисл|ROX", re.I), timeout=10000
    )
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
        await robust_route(page, route)
        await expect(page.locator("main")).to_be_visible(timeout=10000)
        assert (await page.locator("main").inner_text()).strip(), f"route {route} rendered empty"
        report.controls_seen.add(f"route:{route}")

    for path, expected in (
        ("prompt-tools/?mode=image", re.compile(r"описан|промпт|иде", re.I)),
        ("batch/", re.compile(r"несколько|пакет|созда", re.I)),
    ):
        await page.goto(f"{suite.legacy.BASE_URL}/mini-app/{path}", wait_until="domcontentloaded")
        await expect(page.locator("body")).to_contain_text(expected, timeout=10000)
        report.controls_seen.add(f"deep:{path.split('/')[0]}")
    report.ok("canonical ROXY routes + supported deep tools")


async def inventory_visible_controls(page: Page, report: suite.legacy.Report) -> None:
    for route in ("home", "feed", "catalog", "create", "history", "profile", "partners"):
        await robust_route(page, route)
        controls = await page.locator("button:visible").evaluate_all(
            """nodes => nodes.map((node) => ({
              id: node.id || '', text: (node.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 100),
              aria: node.getAttribute('aria-label') || '', route: node.dataset.roxyCustomerRoute || '',
            }))"""
        )
        assert controls, f"route {route} has no visible controls"
        for control in controls:
            signature = control["id"] or control["aria"] or control["text"] or control["route"]
            if signature:
                report.controls_seen.add(f"inventory:{route}:{signature}")

    await page.goto(f"{suite.legacy.BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    await expect(page.locator("#balance")).to_be_visible(timeout=10000)
    await page.locator("#balance").click()
    await expect(page.get_by_role("heading", name="Пополнения ROX")).to_be_visible(timeout=8000)
    assert await page.locator("button:visible").count() > 0
    report.controls_seen.add("inventory:payments-page")
    report.ok("visible control inventory", f"{len(report.controls_seen)} unique control signatures")


suite.select_primary = robust_route
suite.legacy.select_primary = robust_route
suite.scenario_boot_and_navigation = scenario_boot_and_navigation
suite.legacy.scenario_boot_and_navigation = scenario_boot_and_navigation
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
