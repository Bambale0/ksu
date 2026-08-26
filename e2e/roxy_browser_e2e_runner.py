from __future__ import annotations

import asyncio
import re

from playwright.async_api import Page, expect

from e2e import roxy_browser_e2e_v2 as suite


async def robust_route(page: Page, name: str) -> None:
    """Use visible primary navigation and fall back for canonical deep routes.

    History is a supported customer route, but it is intentionally not present
    in the five-item bottom navigation. Tests should exercise the mounted nav
    when a route has a visible control and otherwise use the canonical URL.
    Wallet is not a route and is tested separately as a sheet.
    """
    target = page.locator(f'[data-roxy-customer-route="{name}"]:visible').first
    if await target.count():
        await target.click()
    else:
        await page.goto(
            f"{suite.legacy.BASE_URL}/mini-app/?route={name}",
            wait_until="domcontentloaded",
        )
    await expect(page).to_have_url(
        re.compile(rf"[?&]route={re.escape(name)}(?:&|$)"),
        timeout=8000,
    )


async def scenario_wallet(page: Page, report: suite.legacy.Report) -> None:
    """Open the current wallet sheet and exercise the real card checkout path.

    Wallet is intentionally an overlay opened from the balance control, not a
    canonical customer route. Older E2E code navigated to ``?route=wallet``;
    the React router correctly treated that unknown route as Home, so the test
    was asserting against the wrong surface.
    """
    await page.goto(f"{suite.legacy.BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")

    balance = page.locator("#balance")
    await expect(balance).to_be_visible(timeout=10000)
    await balance.click()

    sheet = page.locator(".sheet").first
    await expect(sheet).to_be_visible(timeout=8000)
    await expect(sheet).to_contain_text(re.compile(r"ROX|Баланс|Пополн", re.I), timeout=8000)
    report.controls_seen.add("wallet:open")

    # Enhanced payment scripts may expose explicit Lava/Crypto tabs. Exercise
    # them when present, while keeping the core React wallet contract valid on
    # its own as well.
    lava_tab = page.locator('[data-checkout-method="lava"]:visible').first
    if await lava_tab.count():
        await lava_tab.click()
        report.controls_seen.add("wallet:method:lava")

    package = page.locator(
        ".sheet .package:visible, .primary-card-package:visible, #paymentPackageGrid .payment-package:visible"
    ).first
    await expect(package).to_be_visible(timeout=8000)
    await package.click()
    report.controls_seen.add("wallet:package")

    email = page.locator(
        '.sheet input[inputmode="email"]:visible, .primary-card-section input[inputmode="email"]:visible'
    ).first
    await expect(email).to_be_visible(timeout=8000)
    await email.fill("e2e@example.com")

    pay = page.locator("button:visible").filter(
        has_text=re.compile(r"Перейти к оплате|Создать оплату", re.I)
    ).first
    await expect(pay).to_be_enabled(timeout=8000)
    async with page.expect_response(
        lambda response: "/api/v1/payments/card/checkout" in response.url
        and response.request.method == "POST",
        timeout=10000,
    ) as checkout_pending:
        await pay.click()
    checkout_response = await checkout_pending.value
    assert checkout_response.ok, (
        f"card checkout: {checkout_response.status} {await checkout_response.text()}"
    )
    report.controls_seen.add("wallet:card:checkout")

    crypto_tab = page.locator('[data-checkout-method="crypto"]:visible').first
    if await crypto_tab.count():
        await crypto_tab.click()
        report.controls_seen.add("wallet:method:crypto")

    report.ok("wallet sheet + payment checkout")


# roxy_browser_e2e_v2 delegates execution to the legacy module's ``main``;
# patch the globals that ``main`` actually resolves. The previous runner only
# replaced names on the wrapper module, leaving the stale wallet scenario live.
suite.select_primary = robust_route
suite.legacy.select_primary = robust_route
suite.scenario_wallet = scenario_wallet
suite.legacy.scenario_wallet = scenario_wallet


if __name__ == "__main__":
    raise SystemExit(asyncio.run(suite.legacy.main()))
