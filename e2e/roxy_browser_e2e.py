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
    page_errors: list[str] = field(default_factory=list)
    http_5xx: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    controls_seen: set[str] = field(default_factory=set)

    def ok(self, name: str, note: str = "") -> None:
        self.scenarios.append({"name": name, "status": "passed", "note": note})

    def fail(self, name: str, error: BaseException) -> None:
        self.scenarios.append({"name": name, "status": "failed", "note": str(error)})

    def write(self) -> None:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(
                {
                    "scenarios": self.scenarios,
                    "page_errors": self.page_errors,
                    "http_5xx": self.http_5xx,
                    "console_errors": self.console_errors,
                    "controls_seen": sorted(self.controls_seen),
                    "control_count": len(self.controls_seen),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def telegram_init_data(user_id: int = MAIN_TG_ID) -> tuple[str, dict[str, object]]:
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


def telegram_shim(init_data: str, user: dict[str, object]) -> str:
    payload = json.dumps({"initData": init_data, "user": user}, ensure_ascii=False)
    return f"""
(() => {{
  const cfg = {payload};
  const listeners = new Map();
  const calls = {{ opened: [], popups: [], clipboard: [], haptics: [], mainButton: [] }};
  window.__roxyE2E = calls;
  const eventApi = {{
    onEvent(name, fn) {{ const items = listeners.get(name) || []; items.push(fn); listeners.set(name, items); }},
    offEvent(name, fn) {{ listeners.set(name, (listeners.get(name) || []).filter((item) => item !== fn)); }},
  }};
  const BackButton = {{
    isVisible: false,
    show() {{ this.isVisible = true; return this; }},
    hide() {{ this.isVisible = false; return this; }},
    onClick(fn) {{ eventApi.onEvent('backButtonClicked', fn); return this; }},
    offClick(fn) {{ eventApi.offEvent('backButtonClicked', fn); return this; }},
  }};
  const MainButton = {{
    isVisible: false, isActive: true, isProgressVisible: false,
    setParams(params) {{ Object.assign(this, params || {{}}); calls.mainButton.push(['setParams', params]); return this; }},
    show() {{ this.isVisible = true; return this; }}, hide() {{ this.isVisible = false; return this; }},
    enable() {{ this.isActive = true; return this; }}, disable() {{ this.isActive = false; return this; }},
    showProgress() {{ this.isProgressVisible = true; return this; }}, hideProgress() {{ this.isProgressVisible = false; return this; }},
    onClick(fn) {{ eventApi.onEvent('mainButtonClicked', fn); return this; }},
    offClick(fn) {{ eventApi.offEvent('mainButtonClicked', fn); return this; }},
  }};
  window.Telegram = {{ WebApp: {{
    initData: cfg.initData,
    initDataUnsafe: {{ user: cfg.user, query_id: 'AAE2E' }},
    version: '9.1', platform: 'tdesktop', colorScheme: 'dark',
    themeParams: {{ bg_color:'#0b0b10', text_color:'#ffffff', hint_color:'#999999', button_color:'#6d5dfc', button_text_color:'#ffffff', secondary_bg_color:'#14141b' }},
    viewportHeight: 900, viewportStableHeight: 900, isExpanded: true,
    ready() {{}}, expand() {{}}, close() {{}}, setHeaderColor() {{}}, setBackgroundColor() {{}},
    enableClosingConfirmation() {{}}, disableClosingConfirmation() {{}},
    BackButton, MainButton,
    HapticFeedback: {{
      impactOccurred(kind) {{ calls.haptics.push(['impact', kind]); }},
      notificationOccurred(kind) {{ calls.haptics.push(['notification', kind]); }},
      selectionChanged() {{ calls.haptics.push(['selection']); }},
    }},
    showPopup(params, cb) {{ calls.popups.push(params); if (cb) cb((params?.buttons?.[0]?.id) || 'ok'); }},
    showAlert(message, cb) {{ calls.popups.push({{message}}); if (cb) cb(); }},
    showConfirm(message, cb) {{ calls.popups.push({{message}}); if (cb) cb(true); }},
    openLink(url) {{ calls.opened.push(url); }}, openTelegramLink(url) {{ calls.opened.push(url); }},
    ...eventApi,
  }} }};
  Object.defineProperty(navigator, 'clipboard', {{ configurable: true, value: {{
    async writeText(value) {{ calls.clipboard.push(String(value)); }},
  }} }});
  navigator.share = async (data) => {{ calls.opened.push(data?.url || 'share'); }};
}})();
"""


async def visible(locator):
    for index in range(await locator.count()):
        item = locator.nth(index)
        if await item.is_visible():
            return item
    raise AssertionError(f"No visible element for locator {locator}")


async def click_visible(locator) -> None:
    await (await visible(locator)).click()


async def api_json(page: Page, path: str, method: str = "GET", body: dict | None = None) -> dict:
    result = await page.evaluate(
        """async ({path, method, body}) => {
          const headers = {Accept: 'application/json', 'X-Telegram-Init-Data': window.Telegram.WebApp.initData};
          if (body !== null) headers['Content-Type'] = 'application/json';
          const response = await fetch(path, {method, headers, body: body === null ? undefined : JSON.stringify(body)});
          let data = null; try { data = await response.json(); } catch (_) {}
          return {status: response.status, data};
        }""",
        {"path": path, "method": method, "body": body},
    )
    if result["status"] >= 400:
        raise AssertionError(f"{method} {path} -> {result['status']}: {result['data']}")
    return result["data"]


async def wait_generation(page: Page, generation_id: str, timeout: float = 25.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = await api_json(page, f"/api/v1/generations/{generation_id}")
        if last.get("status") in {"succeeded", "failed"}:
            return last
        await asyncio.sleep(0.5)
    raise AssertionError(f"Generation {generation_id} did not finish: {last}")


async def select_primary(page: Page, route: str) -> None:
    await click_visible(page.locator(f'[data-roxy-customer-route="{route}"]'))
    await expect(page).to_have_url(re.compile(rf"[?&]route={re.escape(route)}(?:&|$)"), timeout=7000)


async def fill_builder_and_generate(page: Page, prompt: str) -> dict:
    prompt_input = page.locator("#dynamicForm textarea, #dynamicForm input[type=text]").first
    await expect(prompt_input).to_be_visible(timeout=7000)
    await prompt_input.fill(prompt)

    required = page.locator("#dynamicForm .field")
    for index in range(await required.count()):
        field = required.nth(index)
        label = field.locator(".field-label.required")
        if await label.count() == 0:
            continue
        number = field.locator('input[type="number"]')
        if await number.count() and not await number.first.input_value():
            minimum = await number.first.get_attribute("min")
            value = max(3, int(float(minimum or "1")))
            await number.first.fill(str(value))
    billing = page.locator('#dynamicForm input[type="number"]')
    for index in range(await billing.count()):
        item = billing.nth(index)
        if not await item.input_value():
            minimum = await item.get_attribute("min")
            if minimum is not None:
                await item.fill(str(max(3, int(float(minimum)))))

    await expect(page.locator("#createButton")).to_be_enabled(timeout=10000)
    async with page.expect_response(
        lambda response: response.url.rstrip("/").endswith("/api/v1/generations")
        and response.request.method == "POST",
        timeout=10000,
    ) as response_info:
        await page.locator("#createButton").click()
    response = await response_info.value
    assert response.ok, f"generation create failed: {response.status} {await response.text()}"
    created = await response.json()
    generation = await wait_generation(page, created["id"])
    assert generation["status"] == "succeeded", generation
    await expect(page.locator("#resultCard h3")).to_have_text("Готово", timeout=10000)
    return generation


async def seed_partner_earnings() -> None:
    async with SessionFactory() as session:
        inviter = await UserService.get_by_telegram_id(session, MAIN_TG_ID)
        if inviter is None:
            raise AssertionError("E2E inviter was not created by browser authentication")
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
        tx1 = await WalletService.credit(
            session,
            user_id=first.id,
            amount=Decimal("20000"),
            kind="payment",
            reference_type="e2e",
            reference_id="first",
            idempotency_key="e2e-referral-first",
        )
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=first.id,
            source_transaction_id=tx1.id,
            payment_amount=Decimal("20000"),
        )
        tx2 = await WalletService.credit(
            session,
            user_id=second.id,
            amount=Decimal("10000"),
            kind="payment",
            reference_type="e2e",
            reference_id="second",
            idempotency_key="e2e-referral-second",
        )
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=second.id,
            source_transaction_id=tx2.id,
            payment_amount=Decimal("10000"),
        )
        await session.commit()


async def scenario_boot_and_navigation(page: Page, report: Report) -> None:
    await page.goto(f"{BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    await expect(page).to_have_title(re.compile("ROXY"))
    await expect(page.locator('[data-roxy-customer-route="home"]')).to_have_count(2, timeout=8000)
    labels = ["home", "catalog", "create", "history", "profile"]
    for route in labels:
        await select_primary(page, route)
        report.controls_seen.add(f"primary:{route}")
    await select_primary(page, "home")
    await select_primary(page, "catalog")
    prompt = page.get_by_role("button", name=re.compile("Prompt", re.I))
    if await prompt.count():
        await click_visible(prompt)
        await expect(page).to_have_url(re.compile(r"[?&]route=prompt-tools(?:&|$)"), timeout=7000)
        await page.go_back()
        await expect(page).to_have_url(re.compile(r"[?&]route=catalog(?:&|$)"), timeout=7000)
        report.controls_seen.add("catalog:prompt-tools/back")
    report.ok("boot + canonical navigation + Back")


async def scenario_generations(page: Page, report: Report) -> list[dict]:
    results: list[dict] = []
    for media, prompt in (
        ("image", "ROXY E2E image, neon fox, clean studio lighting"),
        ("video", "ROXY E2E video, a fox walking through a neon studio"),
        ("audio", "ROXY E2E synthwave instrumental with a bright melodic hook"),
    ):
        await select_primary(page, "create")
        card = page.locator(f'[data-roxy-media="{media}"]')
        await expect(card).to_be_visible(timeout=8000)
        if media == "audio":
            await expect(card).to_be_enabled(timeout=10000)
        await card.click()
        await expect(page.locator("#builderView")).to_be_visible(timeout=8000)
        result = await fill_builder_and_generate(page, prompt)
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
        reuse = page.get_by_role("button", name="Повторить / изменить")
        await expect(reuse).to_be_visible()
        await reuse.click()
        await expect(page.locator("#builderView")).to_be_visible()
        report.controls_seen.add("result:reuse")
    report.ok("image + video + music generation through real API/DB/Redis/worker + fake Kie")
    return results


async def scenario_history(page: Page, report: Report) -> None:
    await select_primary(page, "history")
    await expect(page.locator("#historyMount")).to_contain_text(re.compile("ROXY E2E|Готово|Suno", re.I), timeout=10000)
    open_button = page.get_by_role("button", name="Открыть")
    if await open_button.count():
        await click_visible(open_button)
        report.controls_seen.add("history:open")
        close = page.get_by_role("button", name=re.compile("Закрыть|Назад"))
        if await close.count():
            await click_visible(close)
            report.controls_seen.add("history:close")
    repeat = page.get_by_role("button", name=re.compile("Повторить"))
    if await repeat.count():
        await click_visible(repeat)
        await expect(page.locator("#builderView")).to_be_visible(timeout=8000)
        report.controls_seen.add("history:repeat")
    report.ok("history open/reuse controls")


async def scenario_wallet(page: Page, report: Report) -> None:
    await page.goto(f"{BASE_URL}/mini-app/?route=home", wait_until="domcontentloaded")
    await click_visible(page.locator("#balance, [data-shell-nav=wallet]"))
    await expect(page).to_have_url(re.compile(r"[?&]route=wallet(?:&|$)"), timeout=8000)
    package = page.locator("#paymentPackageGrid button").first
    await expect(package).to_be_visible(timeout=8000)
    await package.click()
    for provider in ("cryptobot", "tbank", "yookassa"):
        button = page.locator(f'[data-payment-provider="{provider}"]')
        await button.click()
        assert await button.get_attribute("aria-checked") == "true"
        report.controls_seen.add(f"wallet:provider:{provider}")
    crypto = page.locator('[data-payment-provider="cryptobot"]')
    await crypto.click()
    pay = page.locator("#paymentCheckoutButton")
    await expect(pay).to_be_enabled(timeout=5000)
    async with page.expect_response(
        lambda response: "/api/v1/payments" in response.url and response.request.method == "POST",
        timeout=10000,
    ) as response_info:
        await pay.click()
    response = await response_info.value
    assert response.ok, f"payment create failed: {response.status} {await response.text()}"
    await page.wait_for_timeout(300)
    assert await page.evaluate("window.__roxyE2E.opened.length") > 0
    report.controls_seen.add("wallet:checkout")
    refresh = page.get_by_role("button", name=re.compile("Обновить"))
    if await refresh.count():
        await click_visible(refresh)
        report.controls_seen.add("wallet:refresh-payment")
    reopen = page.get_by_role("button", name=re.compile("Открыть оплату|Перейти к оплате"))
    if await reopen.count():
        item = await visible(reopen)
        if await item.is_enabled():
            await item.click()
            report.controls_seen.add("wallet:reopen-payment")
    report.ok("wallet packages + all payment provider selectors + CryptoPay checkout/status")


async def scenario_profile_support_partner(page: Page, report: Report) -> None:
    await select_primary(page, "profile")
    await expect(page.locator("#profileTools")).to_be_visible(timeout=8000)
    await page.locator("#profileUiLanguage").select_option("en")
    notifications = page.locator("#profileNotificationsEnabled")
    if not await notifications.is_checked():
        await notifications.check()
    await page.get_by_role("button", name="Сохранить настройки").click()
    await expect(page.locator(".profile-settings .profile-message")).to_contain_text("Настройки сохранены", timeout=5000)
    report.controls_seen.add("profile:save-settings")

    await page.get_by_label("Тема обращения").fill("ROXY E2E support")
    await page.get_by_label("Сообщение в поддержку").fill("Автоматическая проверка создания обращения")
    await page.get_by_role("button", name="Создать обращение").click()
    await expect(page.locator("#profileSupportDetail")).to_be_visible(timeout=7000)
    await page.get_by_label("Ответ в поддержку").fill("E2E reply")
    await page.get_by_role("button", name="Отправить").click()
    await expect(page.locator("#profileSupportDetail")).to_contain_text("E2E reply", timeout=7000)
    await page.get_by_role("button", name="Закрыть обращение").click()
    await expect(page.get_by_role("button", name="Переоткрыть")).to_be_visible(timeout=7000)
    await page.get_by_role("button", name="Переоткрыть").click()
    await expect(page.get_by_role("button", name="Закрыть обращение")).to_be_visible(timeout=7000)
    await page.get_by_role("button", name="Назад").click()
    report.controls_seen.update({"support:create", "support:reply", "support:close", "support:reopen", "support:back"})

    await seed_partner_earnings()
    await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("#partnerPreview")).to_be_visible(timeout=8000)
    copy = page.get_by_role("button", name="Скопировать")
    await click_visible(copy)
    assert await page.evaluate("window.__roxyE2E.clipboard.length") >= 1
    await click_visible(page.get_by_role("button", name="Пригласить"))
    tabs = ["Начисления", "Партнёры", "Деньги"]
    for tab in tabs:
        await click_visible(page.get_by_role("tab", name=tab))
        report.controls_seen.add(f"partner:tab:{tab}")
    transfer = page.locator(".partner-transfer-form")
    await expect(transfer).to_be_visible(timeout=7000)
    amount = transfer.locator('input[type="number"]')
    await amount.fill("100")
    await transfer.get_by_role("button", name="Перевести в ROX").click()
    await expect(page.locator("#partnerMessage")).to_contain_text("переведён", timeout=7000)
    report.controls_seen.update({"partner:copy", "partner:invite", "partner:transfer-rox"})

    payout = page.locator(".partner-withdrawal-form").filter(has_not=page.locator(".partner-transfer-form"))
    if await payout.count():
        form = payout.first
        inputs = form.locator("input")
        if await inputs.count() >= 2:
            await inputs.nth(0).fill("3000")
            await inputs.nth(1).fill("E2E CARD 0000")
            submit = form.get_by_role("button", name=re.compile("вывод", re.I))
            if await submit.count() and await submit.first.is_enabled():
                await submit.first.click()
                report.controls_seen.add("partner:withdraw")
                cancel = page.get_by_role("button", name="Отменить")
                if await cancel.count():
                    await click_visible(cancel)
                    report.controls_seen.add("partner:cancel-withdraw")
    report.ok("profile settings + support lifecycle + partner copy/invite/tabs/ROX transfer/withdrawal")


async def scenario_child_routes(page: Page, report: Report) -> None:
    routes = {
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
    for route, text in routes.items():
        await page.goto(f"{BASE_URL}/mini-app/?route={route}", wait_until="domcontentloaded")
        await expect(page).to_have_url(re.compile(rf"[?&]route={re.escape(route)}(?:&|$)"))
        await page.wait_for_timeout(350)
        body = await page.locator("body").inner_text()
        assert text.lower() in body.lower(), f"child route {route} did not render expected content"
        report.controls_seen.add(f"child:{route}")
        back = page.locator(".roxy-child-screen-back")
        if await back.count() and await back.first.is_visible():
            await back.first.click()
            report.controls_seen.add(f"child:{route}:back")
    report.ok("embedded notifications/support/creator/subscriptions/references/presets/batch/trends/prompt-tools + Back")


async def inventory_visible_controls(page: Page, report: Report) -> None:
    for route in ("home", "catalog", "create", "history", "profile", "wallet"):
        await page.goto(f"{BASE_URL}/mini-app/?route={route}", wait_until="domcontentloaded")
        await page.wait_for_timeout(500)
        controls = await page.locator("button:visible").evaluate_all(
            """nodes => nodes.map((node) => ({
              id: node.id || '', text: (node.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 100),
              aria: node.getAttribute('aria-label') || '', disabled: node.disabled,
              route: node.dataset.roxyCustomerRoute || node.dataset.shellNav || '',
            }))"""
        )
        assert controls, f"route {route} has no visible controls"
        for control in controls:
            signature = control["id"] or control["aria"] or control["text"] or control["route"]
            if signature:
                report.controls_seen.add(f"inventory:{route}:{signature}")
    report.ok("visible control inventory", f"{len(report.controls_seen)} unique control signatures")


async def install_context(context: BrowserContext, init_data: str, user: dict[str, object]) -> None:
    await context.add_init_script(telegram_shim(init_data, user))
    await context.route(
        re.compile(r"https://telegram\.org/js/telegram-web-app\.js.*"),
        lambda route: route.fulfill(status=200, content_type="application/javascript", body=""),
    )


async def main() -> int:
    report = Report()
    init_data, user = telegram_init_data()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 430, "height": 932})
        await install_context(context, init_data, user)
        page = await context.new_page()
        page.on("pageerror", lambda error: report.page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: report.console_errors.append(message.text) if message.type == "error" else None,
        )
        page.on(
            "response",
            lambda response: report.http_5xx.append(f"{response.status} {response.url}")
            if response.status >= 500 and response.url.startswith(BASE_URL)
            else None,
        )
        failures: list[str] = []
        scenarios = [
            ("navigation", scenario_boot_and_navigation),
            ("generations", scenario_generations),
            ("history", scenario_history),
            ("wallet", scenario_wallet),
            ("profile-support-partner", scenario_profile_support_partner),
            ("child-routes", scenario_child_routes),
            ("control-inventory", inventory_visible_controls),
        ]
        for name, scenario in scenarios:
            try:
                await scenario(page, report)
            except Exception as exc:
                report.fail(name, exc)
                failures.append(f"{name}: {exc}")
                await page.screenshot(path=str(REPORT_PATH.parent / f"failure-{name}.png"), full_page=True)
                break
        await context.close()
        await browser.close()

    if report.page_errors:
        failures.extend(f"pageerror: {item}" for item in report.page_errors)
    if report.http_5xx:
        failures.extend(f"http5xx: {item}" for item in report.http_5xx)
    report.write()
    print(json.dumps({"scenarios": report.scenarios, "control_count": len(report.controls_seen)}, ensure_ascii=False, indent=2))
    if failures:
        print("E2E FAILURES:\n" + "\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
