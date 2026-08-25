from __future__ import annotations

import asyncio
import re

from playwright.async_api import BrowserContext, Page, expect

from e2e import roxy_browser_e2e_v2 as suite


async def robust_route(page: Page, name: str) -> None:
    # Canonical ROXY navigation is mounted by the runtime after the static shell.
    # DOMContentLoaded alone does not guarantee those buttons exist yet.
    target = page.locator(f'[data-roxy-customer-route="{name}"]:visible').first
    await expect(target).to_be_visible(timeout=10000)
    await target.click()
    await expect(page).to_have_url(
        re.compile(rf"[?&]route={re.escape(name)}(?:&|$)"),
        timeout=8000,
    )


async def scenario_concurrent_boot(context: BrowserContext, report: suite.Report) -> None:
    pages = [await context.new_page() for _ in range(4)]
    try:
        await asyncio.gather(
            *(page.goto(f"{suite.BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded") for page in pages)
        )
        await asyncio.gather(
            *(expect(page.locator("#balance")).to_be_visible(timeout=10000) for page in pages)
        )
        # Every concurrent page must complete authenticated bootstrap, not merely
        # render static HTML.
        payloads = await asyncio.gather(*(suite.api(page, "/api/v1/me") for page in pages))
        assert len({str(item.get("id")) for item in payloads}) == 1
        report.controls.add("bootstrap:parallel-auth")
        report.passed("parallel fresh-user bootstrap")
    finally:
        for page in pages:
            await page.close()


async def scenario_navigation(page: Page, report: suite.Report) -> None:
    await page.goto(f"{suite.BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    await expect(page.locator("#balance")).to_be_visible(timeout=10000)
    for name in ("home", "catalog", "create", "history", "profile"):
        await suite.route(page, name)
        report.controls.add(f"nav:{name}")
    await suite.route(page, "catalog")
    prompt = page.get_by_role("button", name=re.compile("Prompt", re.I))
    if await prompt.count():
        await suite.click_visible(prompt)
        await expect(page).to_have_url(re.compile(r"[?&]route=prompt-tools(?:&|$)"), timeout=8000)
        await page.go_back()
        await expect(page).to_have_url(re.compile(r"[?&]route=catalog(?:&|$)"), timeout=8000)
        report.controls.add("nav:browser-back")
    report.passed("canonical navigation and Back")


async def scenario_wallet(page: Page, report: suite.Report) -> None:
    await page.goto(f"{suite.BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    await page.locator("#balance").click()
    await expect(page).to_have_url(re.compile(r"[?&]route=wallet(?:&|$)"), timeout=8000)

    lava_tab = page.locator('[data-checkout-method="lava"]')
    crypto_tab = page.locator('[data-checkout-method="crypto"]')
    await expect(lava_tab).to_be_visible(timeout=8000)
    await expect(crypto_tab).to_be_visible(timeout=8000)
    await lava_tab.click()
    report.controls.add("wallet:method:lava")
    await expect(page.locator(".primary-card-section")).to_be_visible(timeout=8000)
    email = page.locator('.primary-card-section input[type="email"]')
    await email.fill("e2e@example.com")
    await page.locator(".primary-card-package").first.click()
    pay = page.get_by_role("button", name="Создать оплату")
    await expect(pay).to_be_enabled(timeout=8000)
    async with page.expect_response(
        lambda response: "/api/v1/payments/card/checkout" in response.url
        and response.request.method == "POST",
        timeout=10000,
    ) as card_pending:
        await pay.click()
    card_response = await card_pending.value
    assert card_response.ok, f"card checkout: {card_response.status} {await card_response.text()}"
    await expect(page.get_by_role("button", name="Открыть оплату")).to_be_visible(timeout=8000)
    report.controls.add("wallet:lava:create")
    refresh_card = page.locator(".primary-card-actions").get_by_role("button", name="Обновить статус")
    await refresh_card.click()
    report.controls.add("wallet:lava:refresh")

    await crypto_tab.click()
    report.controls.add("wallet:method:crypto")
    package = page.locator("#paymentPackageGrid .payment-package").first
    await expect(package).to_be_visible(timeout=8000)
    await package.click()
    crypto_provider = page.locator('[data-payment-provider="cryptobot"]')
    await expect(crypto_provider).to_be_visible(timeout=8000)
    await crypto_provider.click()
    report.controls.add("wallet:crypto:provider")
    checkout = page.locator("#paymentCheckoutButton")
    await expect(checkout).to_be_enabled(timeout=8000)
    async with page.expect_response(
        lambda response: response.url.rstrip("/").endswith("/api/v1/payments")
        and response.request.method == "POST",
        timeout=10000,
    ) as crypto_pending:
        await checkout.click()
    crypto_response = await crypto_pending.value
    assert crypto_response.ok, f"crypto checkout: {crypto_response.status} {await crypto_response.text()}"
    await expect(page.get_by_role("button", name="Обновить статус")).to_be_visible(timeout=8000)
    await suite.click_visible(page.get_by_role("button", name="Обновить статус"))
    reopen = page.get_by_role("button", name="Открыть оплату")
    if await reopen.count():
        await suite.click_visible(reopen)
        report.controls.add("wallet:crypto:reopen")
    report.controls.update({"wallet:crypto:checkout", "wallet:crypto:refresh"})
    report.passed("Lava/card + CryptoBot checkout controls")


suite.route = robust_route
suite.scenario_concurrent_boot = scenario_concurrent_boot
suite.scenario_navigation = scenario_navigation
suite.scenario_wallet = scenario_wallet


if __name__ == "__main__":
    raise SystemExit(asyncio.run(suite.main()))
