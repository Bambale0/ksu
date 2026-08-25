from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from aiogram.types import User as TelegramUser
from playwright.async_api import BrowserContext, Page, async_playwright, expect

from app.db.session import SessionFactory
from app.services.referrals import ReferralService
from app.services.users import UserService
from app.services.wallet import WalletService

BASE_URL = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
BOT_TOKEN = os.environ["BOT_TOKEN"]
MAIN_TG_ID = 9_000_000_001
REPORT_PATH = Path(os.getenv("E2E_REPORT_PATH", "artifacts/e2e-report.json"))


@dataclass
class Report:
    scenarios: list[dict[str, str]] = field(default_factory=list)
    controls: set[str] = field(default_factory=set)
    page_errors: list[str] = field(default_factory=list)
    http_5xx: list[str] = field(default_factory=list)

    def passed(self, name: str, note: str = "") -> None:
        self.scenarios.append({"name": name, "status": "passed", "note": note})

    def failed(self, name: str, error: BaseException) -> None:
        self.scenarios.append({"name": name, "status": "failed", "note": str(error)})

    def write(self) -> None:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(
                {
                    "scenarios": self.scenarios,
                    "controls": sorted(self.controls),
                    "control_count": len(self.controls),
                    "page_errors": self.page_errors,
                    "http_5xx": self.http_5xx,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def init_data(user_id: int = MAIN_TG_ID) -> tuple[str, dict[str, object]]:
    user: dict[str, object] = {
        "id": user_id,
        "first_name": "ROXY",
        "last_name": "E2E",
        "username": f"roxy_e2e_{user_id}",
        "language_code": "ru",
        "allows_write_to_pm": True,
    }
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": f"AAE2E{user_id}",
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
    }
    data_check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature}), user


def telegram_shim(signed: str, user: dict[str, object]) -> str:
    config = json.dumps({"signed": signed, "user": user}, ensure_ascii=False)
    return f"""
(() => {{
  const cfg = {config};
  const events = new Map();
  const calls = {{opened: [], clipboard: [], popups: [], haptics: []}};
  window.__roxyE2E = calls;
  const onEvent = (name, fn) => {{ const list = events.get(name) || []; list.push(fn); events.set(name, list); }};
  const offEvent = (name, fn) => events.set(name, (events.get(name) || []).filter((item) => item !== fn));
  const BackButton = {{isVisible:false, show(){{this.isVisible=true;}}, hide(){{this.isVisible=false;}}, onClick(fn){{onEvent('backButtonClicked',fn);}}, offClick(fn){{offEvent('backButtonClicked',fn);}}}};
  const MainButton = {{isVisible:false,isActive:true,isProgressVisible:false,
    setParams(p){{Object.assign(this,p||{{}});}},show(){{this.isVisible=true;}},hide(){{this.isVisible=false;}},enable(){{this.isActive=true;}},disable(){{this.isActive=false;}},showProgress(){{this.isProgressVisible=true;}},hideProgress(){{this.isProgressVisible=false;}},onClick(fn){{onEvent('mainButtonClicked',fn);}},offClick(fn){{offEvent('mainButtonClicked',fn);}}}};
  window.Telegram = {{WebApp:{{
    initData: cfg.signed, initDataUnsafe:{{user:cfg.user,query_id:'AAE2E'}}, version:'9.1', platform:'tdesktop', colorScheme:'dark',
    themeParams:{{bg_color:'#0b0b10',text_color:'#fff',hint_color:'#999',button_color:'#6d5dfc',button_text_color:'#fff',secondary_bg_color:'#14141b'}},
    viewportHeight:932, viewportStableHeight:932, isExpanded:true, BackButton, MainButton,
    ready(){{}},expand(){{}},close(){{}},setHeaderColor(){{}},setBackgroundColor(){{}},enableClosingConfirmation(){{}},disableClosingConfirmation(){{}},
    onEvent,offEvent,
    HapticFeedback:{{impactOccurred(k){{calls.haptics.push(['impact',k]);}},notificationOccurred(k){{calls.haptics.push(['notification',k]);}},selectionChanged(){{calls.haptics.push(['selection']);}}}},
    showPopup(p,cb){{calls.popups.push(p);cb?.(p?.buttons?.[0]?.id||'ok');}},showAlert(m,cb){{calls.popups.push({{message:m}});cb?.();}},showConfirm(m,cb){{calls.popups.push({{message:m}});cb?.(true);}},
    openLink(url){{calls.opened.push(url);}},openTelegramLink(url){{calls.opened.push(url);}}
  }}}};
  Object.defineProperty(navigator,'clipboard',{{configurable:true,value:{{async writeText(v){{calls.clipboard.push(String(v));}}}}}});
  navigator.share = async (data) => calls.opened.push(data?.url || 'share');
}})();
"""


async def install(context: BrowserContext, signed: str, user: dict[str, object]) -> None:
    await context.add_init_script(telegram_shim(signed, user))
    await context.route(
        re.compile(r"https://telegram\.org/js/telegram-web-app\.js.*"),
        lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
    )


async def click_visible(locator) -> None:
    for index in range(await locator.count()):
        item = locator.nth(index)
        if await item.is_visible():
            await item.click()
            return
    raise AssertionError(f"No visible target for {locator}")


async def route(page: Page, name: str) -> None:
    if name == "home":
        await click_visible(page.get_by_role("button", name=re.compile("ROXY — главная")))
    else:
        await click_visible(page.locator(f'[data-roxy-customer-route="{name}"]'))
    await expect(page).to_have_url(re.compile(rf"[?&]route={re.escape(name)}(?:&|$)"), timeout=8000)


async def api(page: Page, path: str) -> dict:
    result = await page.evaluate(
        """async (path) => {
          const response = await fetch(path, {headers:{Accept:'application/json','X-Telegram-Init-Data':window.Telegram.WebApp.initData}});
          let data=null; try {data=await response.json();} catch (_) {}
          return {status:response.status,data};
        }""",
        path,
    )
    assert result["status"] < 400, f"GET {path}: {result}"
    return result["data"]


async def wait_generation(page: Page, generation_id: str) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        item = await api(page, f"/api/v1/generations/{generation_id}")
        if item.get("status") in {"succeeded", "failed"}:
            return item
        await asyncio.sleep(0.5)
    raise AssertionError(f"generation {generation_id} timed out")


async def generate(page: Page, media: str, prompt: str, report: Report) -> None:
    await route(page, "create")
    card = page.locator(f'[data-roxy-media="{media}"]')
    await expect(card).to_be_visible(timeout=8000)
    await expect(card).to_be_enabled(timeout=10000)
    await card.click()
    await expect(page.locator("#builderView")).to_be_visible(timeout=8000)
    prompt_input = page.locator("#dynamicForm textarea, #dynamicForm input[type=text]").first
    await expect(prompt_input).to_be_visible(timeout=8000)
    await prompt_input.fill(prompt)
    for index in range(await page.locator('#dynamicForm input[type="number"]').count()):
        field = page.locator('#dynamicForm input[type="number"]').nth(index)
        if not await field.input_value():
            minimum = await field.get_attribute("min")
            await field.fill(str(max(3, int(float(minimum or "1")))))
    create = page.locator("#createButton")
    await expect(create).to_be_enabled(timeout=10000)
    async with page.expect_response(
        lambda response: response.url.rstrip("/").endswith("/api/v1/generations") and response.request.method == "POST",
        timeout=10000,
    ) as pending:
        await create.click()
    response = await pending.value
    assert response.ok, f"create {media}: {response.status} {await response.text()}"
    created = await response.json()
    finished = await wait_generation(page, created["id"])
    assert finished["status"] == "succeeded", finished
    await expect(page.locator("#resultCard h3")).to_have_text("Готово", timeout=10000)
    report.controls.update({f"create:{media}", f"generation:{media}:submit"})
    share = page.get_by_role("button", name="Поделиться")
    if await share.count() and await share.first.is_visible():
        before = await page.evaluate("window.__roxyE2E.opened.length")
        await share.first.click()
        assert await page.evaluate("window.__roxyE2E.opened.length") > before
        report.controls.add("result:share")
    reuse = page.get_by_role("button", name="Повторить / изменить")
    await expect(reuse).to_be_visible()
    await reuse.click()
    await expect(page.locator("#builderView")).to_be_visible()
    report.controls.add("result:reuse")


async def seed_partner() -> None:
    async with SessionFactory() as session:
        inviter = await UserService.get_by_telegram_id(session, MAIN_TG_ID)
        assert inviter is not None
        first = await UserService.get_or_create(
            session,
            TelegramUser(id=MAIN_TG_ID + 1, is_bot=False, first_name="First", username="roxy_first"),
            inviter_telegram_id=MAIN_TG_ID,
        )
        second = await UserService.get_or_create(
            session,
            TelegramUser(id=MAIN_TG_ID + 2, is_bot=False, first_name="Second", username="roxy_second"),
            inviter_telegram_id=MAIN_TG_ID + 1,
        )
        for user, amount, key in ((first, "20000", "first"), (second, "10000", "second")):
            tx = await WalletService.credit(
                session,
                user_id=user.id,
                amount=Decimal(amount),
                kind="payment",
                reference_type="e2e",
                reference_id=key,
                idempotency_key=f"e2e-referral-{key}",
            )
            await ReferralService.accrue_from_payment(
                session,
                source_user_id=user.id,
                source_transaction_id=tx.id,
                payment_amount=Decimal(amount),
            )
        await session.commit()


async def scenario_concurrent_boot(context: BrowserContext, report: Report) -> None:
    pages = [await context.new_page() for _ in range(4)]
    try:
        await asyncio.gather(*(page.goto(f"{BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded") for page in pages))
        await asyncio.gather(*(expect(page.locator("#brandBalanceButton")).to_be_visible(timeout=10000) for page in pages))
        report.controls.add("bootstrap:parallel-auth")
        report.passed("parallel fresh-user bootstrap")
    finally:
        for page in pages:
            await page.close()


async def scenario_navigation(page: Page, report: Report) -> None:
    await page.goto(f"{BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    await expect(page.locator("#brandBalanceButton")).to_be_visible(timeout=10000)
    for name in ("home", "catalog", "create", "history", "profile"):
        await route(page, name)
        report.controls.add(f"nav:{name}")
    await route(page, "catalog")
    prompt = page.get_by_role("button", name=re.compile("Prompt", re.I))
    if await prompt.count():
        await click_visible(prompt)
        await expect(page).to_have_url(re.compile(r"/mini-app/prompt-tools/(?:\?|$)"), timeout=8000)
        await page.go_back()
        await expect(page).to_have_url(re.compile(r"[?&]route=catalog(?:&|$)"), timeout=8000)
        report.controls.add("nav:browser-back")
    report.passed("canonical navigation and Back")


async def scenario_generation(page: Page, report: Report) -> None:
    await generate(page, "image", "ROXY E2E image neon fox studio", report)
    await generate(page, "video", "ROXY E2E video neon fox walking", report)
    await generate(page, "audio", "ROXY E2E synthwave instrumental", report)
    report.passed("image + video + music end-to-end")


async def scenario_history(page: Page, report: Report) -> None:
    await route(page, "history")
    await expect(page.locator("#historyMount")).to_contain_text(re.compile("ROXY E2E|Готово|Suno", re.I), timeout=10000)
    open_button = page.get_by_role("button", name="Открыть")
    if await open_button.count():
        await click_visible(open_button)
        report.controls.add("history:open")
        close = page.get_by_role("button", name=re.compile("Закрыть|Назад"))
        if await close.count():
            await click_visible(close)
            report.controls.add("history:close")
    repeat = page.get_by_role("button", name=re.compile("Повторить"))
    if await repeat.count():
        await click_visible(repeat)
        await expect(page.locator("#builderView")).to_be_visible(timeout=8000)
        report.controls.add("history:repeat")
    report.passed("history open/reuse")


async def scenario_wallet(page: Page, report: Report) -> None:
    await page.goto(f"{BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    await click_visible(page.locator("#brandBalanceButton"))
    await expect(page).to_have_url(re.compile(r"[?&]route=wallet(?:&|$)"), timeout=8000)

    lava_tab = page.locator('[data-checkout-method="lava"]')
    crypto_tab = page.locator('[data-checkout-method="crypto"]')
    await expect(lava_tab).to_be_visible(timeout=8000)
    await expect(crypto_tab).to_be_visible(timeout=8000)
    await lava_tab.click()
    report.controls.add("wallet:method:lava")
    await expect(page.locator(".primary-card-section")).to_be_visible()
    email = page.locator('.primary-card-section input[type="email"]')
    await email.fill("e2e@example.com")
    await page.locator(".primary-card-package").first.click()
    pay = page.get_by_role("button", name="Создать оплату")
    await expect(pay).to_be_enabled(timeout=8000)
    async with page.expect_response(
        lambda response: "/api/v1/payments/card/checkout" in response.url and response.request.method == "POST",
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
    await expect(crypto_provider).to_be_visible()
    await crypto_provider.click()
    report.controls.add("wallet:crypto:provider")
    checkout = page.locator("#paymentCheckoutButton")
    await expect(checkout).to_be_enabled(timeout=8000)
    async with page.expect_response(
        lambda response: response.url.rstrip("/").endswith("/api/v1/payments") and response.request.method == "POST",
        timeout=10000,
    ) as crypto_pending:
        await checkout.click()
    crypto_response = await crypto_pending.value
    assert crypto_response.ok, f"crypto checkout: {crypto_response.status} {await crypto_response.text()}"
    await expect(page.get_by_role("button", name="Обновить статус")).to_be_visible(timeout=8000)
    await click_visible(page.get_by_role("button", name="Обновить статус"))
    reopen = page.get_by_role("button", name="Открыть оплату")
    if await reopen.count():
        await click_visible(reopen)
        report.controls.add("wallet:crypto:reopen")
    report.controls.update({"wallet:crypto:checkout", "wallet:crypto:refresh"})
    report.passed("Lava/card + CryptoBot checkout controls")


async def scenario_profile_support_partner(page: Page, report: Report) -> None:
    await route(page, "profile")
    await expect(page.locator("#profileTools")).to_be_visible(timeout=8000)
    language = page.locator("#profileUiLanguage")
    if await language.count():
        await language.select_option("en")
    await page.get_by_role("button", name="Сохранить настройки").click()
    await expect(page.locator(".profile-settings .profile-message")).to_contain_text("Настройки сохранены", timeout=8000)
    report.controls.add("profile:save")

    await page.get_by_label("Тема обращения").fill("ROXY E2E support")
    await page.get_by_label("Сообщение в поддержку").fill("Автоматическая E2E проверка")
    await page.get_by_role("button", name="Создать обращение").click()
    await expect(page.locator("#profileSupportDetail")).to_be_visible(timeout=8000)
    await page.get_by_label("Ответ в поддержку").fill("E2E reply")
    await page.get_by_role("button", name="Отправить").click()
    await expect(page.locator("#profileSupportDetail")).to_contain_text("E2E reply", timeout=8000)
    await page.get_by_role("button", name="Закрыть обращение").click()
    await expect(page.get_by_role("button", name="Переоткрыть")).to_be_visible(timeout=8000)
    await page.get_by_role("button", name="Переоткрыть").click()
    await expect(page.get_by_role("button", name="Закрыть обращение")).to_be_visible(timeout=8000)
    report.controls.update({"support:create", "support:reply", "support:close", "support:reopen"})

    await seed_partner()
    await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("#partnerPreview")).to_be_visible(timeout=10000)
    await click_visible(page.get_by_role("button", name="Скопировать"))
    assert await page.evaluate("window.__roxyE2E.clipboard.length") > 0
    await click_visible(page.get_by_role("button", name="Пригласить"))
    for tab in ("Начисления", "Партнёры", "Деньги"):
        await click_visible(page.get_by_role("tab", name=tab))
        report.controls.add(f"partner:tab:{tab}")
    transfer = page.locator(".partner-transfer-form")
    await expect(transfer).to_be_visible(timeout=8000)
    await transfer.locator('input[type="number"]').fill("100")
    await transfer.get_by_role("button", name="Перевести в ROX").click()
    await expect(page.locator("#partnerMessage")).to_contain_text("переведён", timeout=8000)
    report.controls.update({"partner:copy", "partner:invite", "partner:transfer"})

    payout = page.locator(".partner-withdrawal-form:not(.partner-transfer-form)")
    if await payout.count():
        form = payout.first
        inputs = form.locator("input")
        if await inputs.count() >= 2:
            await inputs.nth(0).fill("3000")
            await inputs.nth(1).fill("E2E CARD 0000")
            submit = form.get_by_role("button", name=re.compile("вывод", re.I))
            if await submit.count() and await submit.first.is_enabled():
                await submit.first.click()
                report.controls.add("partner:withdraw")
                cancel = page.get_by_role("button", name="Отменить")
                if await cancel.count():
                    await click_visible(cancel)
                    report.controls.add("partner:cancel-withdraw")
    report.passed("profile + support lifecycle + partner cabinet")


async def scenario_child_routes(page: Page, report: Report) -> None:
    expected = {
        "notifications": "Уведом",
        "support": "Поддерж",
        "creator": "Creator",
        "subscriptions": "Подпис",
        "references": "Референ",
        "presets": "Пресет",
        "batch": "Batch",
        "trends": "Тренд",
        "prompt-tools": "Prompt",
    }
    for name, needle in expected.items():
        await page.goto(f"{BASE_URL}/mini-app/?route={name}", wait_until="domcontentloaded")
        await page.wait_for_timeout(400)
        assert needle.lower() in (await page.locator("body").inner_text()).lower(), name
        report.controls.add(f"child:{name}")
        back = page.locator(".roxy-child-screen-back")
        if await back.count() and await back.first.is_visible():
            await back.first.click()
            report.controls.add(f"child:{name}:back")
    report.passed("embedded child routes and Back")


async def scenario_inventory(page: Page, report: Report) -> None:
    for name in ("home", "catalog", "create", "history", "profile", "wallet"):
        await page.goto(f"{BASE_URL}/mini-app/?route={name}", wait_until="domcontentloaded")
        await page.wait_for_timeout(500)
        rows = await page.locator("button:visible").evaluate_all(
            "nodes => nodes.map(n => ({id:n.id||'', text:(n.innerText||'').trim().replace(/\\s+/g,' ').slice(0,90), aria:n.getAttribute('aria-label')||'', route:n.dataset.roxyCustomerRoute||n.dataset.checkoutMethod||''}))"
        )
        assert rows, f"no visible buttons on {name}"
        for row in rows:
            signature = row["id"] or row["aria"] or row["route"] or row["text"]
            if signature:
                report.controls.add(f"inventory:{name}:{signature}")
    report.passed("visible button inventory", f"{len(report.controls)} unique signatures")


async def main() -> int:
    report = Report()
    signed, user = init_data()
    failures: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 430, "height": 932})
        await install(context, signed, user)
        page = await context.new_page()

        def page_error(error: BaseException) -> None:
            report.page_errors.append(str(error))

        def response_seen(response) -> None:
            if response.status >= 500 and response.url.startswith(BASE_URL):
                report.http_5xx.append(f"{response.status} {response.request.method} {response.url}")

        context.on("page", lambda created: created.on("pageerror", page_error))
        context.on("response", response_seen)
        page.on("pageerror", page_error)

        scenarios = [
            ("parallel-bootstrap", lambda: scenario_concurrent_boot(context, report)),
            ("navigation", lambda: scenario_navigation(page, report)),
            ("generation", lambda: scenario_generation(page, report)),
            ("history", lambda: scenario_history(page, report)),
            ("wallet", lambda: scenario_wallet(page, report)),
            ("profile-support-partner", lambda: scenario_profile_support_partner(page, report)),
            ("child-routes", lambda: scenario_child_routes(page, report)),
            ("inventory", lambda: scenario_inventory(page, report)),
        ]
        for name, scenario in scenarios:
            try:
                await scenario()
            except Exception as exc:
                report.failed(name, exc)
                failures.append(f"{name}: {exc}")
                await page.screenshot(path=str(REPORT_PATH.parent / f"failure-{name}.png"), full_page=True)
                break
        await context.close()
        await browser.close()

    if report.page_errors:
        failures.extend(f"pageerror: {error}" for error in report.page_errors)
    if report.http_5xx:
        failures.extend(f"http5xx: {error}" for error in report.http_5xx)
    report.write()
    print(json.dumps({"scenarios": report.scenarios, "control_count": len(report.controls)}, ensure_ascii=False, indent=2))
    if failures:
        print("E2E FAILURES:\n" + "\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
