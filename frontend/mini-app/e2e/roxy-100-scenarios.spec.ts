import { expect, type Page, test } from "@playwright/test";

type RouteName = "home" | "feed" | "catalog" | "create" | "history" | "profile" | "partners";

const routes: RouteName[] = ["home", "feed", "catalog", "create", "history", "profile", "partners"];
const viewports = [
  { width: 360, height: 760 },
  { width: 390, height: 844 },
  { width: 414, height: 896 },
  { width: 430, height: 932 },
];
const scenarios = Array.from({ length: 100 }, (_, index) => ({
  id: index + 1,
  route: routes[index % routes.length],
  viewport: viewports[index % viewports.length],
  sort: (["recent", "top_day", "top"] as const)[index % 3],
}));

const models = [
  {
    id: "nano-banana-2",
    title: "Nano Banana 2",
    family: "Nano Banana",
    media_type: "image",
    operation: "auto",
    price_rox: "25.00",
    ui_schema: {
      defaults: { prompt: "", resolution: "2K" },
      fields: [
        { name: "prompt", label: "Промпт", control: "textarea", required: true, group: "main", placeholder: "Опишите идею" },
        { name: "resolution", label: "Разрешение", control: "select", suggestions: ["1K", "2K", "4K"], group: "settings" },
      ],
      groups: [{ id: "main", title: "Описание" }, { id: "settings", title: "Настройки" }],
    },
    presentation: { family_group: "nano-banana", family_title: "Nano Banana", version_label: "2", product_title: "Оптимальный баланс качества и скорости" },
  },
  {
    id: "kling-video",
    title: "Kling Video",
    family: "Kling",
    media_type: "video",
    operation: "auto",
    price_rox: "80.00",
    ui_schema: {
      defaults: { prompt: "" },
      fields: [{ name: "prompt", label: "Промпт", control: "textarea", required: true, group: "main" }],
      groups: [{ id: "main", title: "Описание" }],
      billing_seconds: { label: "Длительность", min: 5, max: 10, required: true },
    },
    presentation: { family_group: "kling", family_title: "Kling", version_label: "Видео", product_title: "Движение по описанию" },
  },
];
const families = [
  { id: "nano-banana", family: "nano_banana", title: "Nano Banana", media_types: ["image"], variant_count: 1, price_from_rox: "25.00", variants: [{ id: "nano-banana-2", title: "Nano Banana 2", version: "2", media_type: "image", operation: "auto", price_rox: "25.00", description: "Оптимальный баланс" }] },
  { id: "kling", family: "kling", title: "Kling", media_types: ["video"], variant_count: 1, price_from_rox: "80.00", variants: [{ id: "kling-video", title: "Kling Video", version: "Видео", media_type: "video", operation: "auto", price_rox: "80.00", description: "Видео по описанию" }] },
];
const feedItems = [
  { id: "feed-1", status: "succeeded", preview_url: "/promo/roxy-promo-1.png", result_url: "/promo/roxy-promo-1.png", model: "Nano Banana 2", prompt: "неоновый портрет", prompt_hidden: true, created_at: "2026-08-21T01:00:00Z", feed_published_at: "2026-08-21T01:05:00Z", likes_count: 12, shares_count: 3, comments_count: 2, liked_by_me: false, prompt_actions_allowed: true, is_mine: false },
  { id: "feed-2", status: "succeeded", preview_url: "/promo/roxy-promo-2.png", result_url: "/promo/roxy-promo-2.png", model: "Kling Video", prompt_hidden: true, created_at: "2026-08-21T02:00:00Z", feed_published_at: "2026-08-21T02:05:00Z", likes_count: 4, shares_count: 1, comments_count: 0, liked_by_me: true, prompt_actions_allowed: true, is_mine: true },
];
const trends = [
  { id: "trend-1", title: "Неоновый аватар", description: "Готовый стиль для профиля", media_type: "image", cost_rox: "25.00", model: { title: "Nano Banana 2" }, reference_requirements: { min: 0 } },
  { id: "trend-2", title: "Короткий ролик", description: "Динамичный промо-сценарий", media_type: "video", cost_rox: "80.00", model: { title: "Kling" }, reference_requirements: { min: 0 } },
];
const generations = [
  { id: "gen-1", status: "succeeded", result_url: "/promo/roxy-promo-1.png", result_urls: ["/promo/roxy-promo-1.png"], model: models[0], prompt: "пикачу в неоне", created_at: "2026-08-21T01:00:00Z", is_profile_visible: true, publication_scope: "profile" },
  { id: "gen-2", status: "queued", model: models[1], prompt: "ролик продукта", created_at: "2026-08-21T01:10:00Z" },
];

async function mockTelegram(page: Page) {
  await page.addInitScript(() => {
    (window as any).Telegram = {
      WebApp: {
        initData: "query_id=test&user=%7B%22id%22%3A1001%2C%22first_name%22%3A%22Igor%22%2C%22username%22%3A%22creator%22%7D",
        initDataUnsafe: { user: { id: 1001, first_name: "Igor", username: "creator", photo_url: "" } },
        ready() {}, expand() {}, onEvent() {}, offEvent() {},
        openLink(url: string) { window.location.assign(url); },
        HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
      },
    };
  });
}

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/me") return json({ id: "u1", telegram_id: 1001, username: "creator", first_name: "Igor", last_name: "", balance_rox: "125.00" });
    if (path === "/api/v1/onboarding") return json({ enabled: false, completed: true });
    if (path === "/api/v1/generations/models") return json({ models, families });
    if (path === "/api/v1/generations/quote") return json({ cost_rox: "25.00", cost_rub: "25.00", balance_after_rox: "100.00" });
    if (path === "/api/v1/generations" && method === "POST") return json({ id: "gen-created", status: "queued", cost_rox: "25.00" });
    if (path === "/api/v1/generations/gen-created") return json({ ...generations[0], id: "gen-created" });
    if (path.startsWith("/api/v1/generations/")) return json(generations[0]);
    if (path === "/api/v1/generations") return json({ items: generations, has_more: false, next_before: null });
    if (path === "/api/v1/feed") return json({ items: feedItems });
    if (path.startsWith("/api/v1/profiles/")) return json({ author: { telegram_id: 1001 }, items: feedItems.slice(0, 1) });
    if (path.endsWith("/publish")) return json({ publication_scope: "feed", downgraded_to_profile: false, item: feedItems[1] });
    if (path.endsWith("/like")) return json({ id: "feed-1", surface: "feed", liked_by_me: true, likes_count: 13 });
    if (path.endsWith("/share")) return json({ id: "feed-1", shares_count: 4, link: "https://t.me/roxy_bot?start=feed_1001_feed-1" });
    if (path.endsWith("/comments") && method === "GET") return json({ items: [{ id: "c1", text: "Круто", created_at: "2026-08-21T01:20:00Z", author: { display_name: "User" } }] });
    if (path.endsWith("/comments") && method === "POST") return json({ id: "c2", text: "Нравится", created_at: "2026-08-21T01:25:00Z", author: { display_name: "Igor" } });
    if (path.endsWith("/remix")) return json({ id: "gen-remix", status: "queued" });
    if (path.endsWith("/remove")) return json({ id: "feed-1", publication_scope: "private", is_public_feed: false, is_profile_visible: false });
    if (path === "/api/v1/trends") return json({ items: trends });
    if (path.endsWith("/run")) return json({ id: "gen-trend", status: "queued", cost_rox: "25.00" });
    if (path === "/api/v1/referrals/stats") return json({ referral_link: "https://t.me/roxy_bot?start=ref_1001", first_line: 3, second_line: 1, available_rub: "500.00", available: "500.00", total_rewards_rub: "1400.00" });
    if (path === "/api/v1/referrals/invitations") return json({ items: [{ id: "i1", created_at: "2026-08-20T12:00:00Z", invited_user: { username: "friend" }, status: "active" }] });
    if (path === "/api/v1/referrals/rewards") return json({ items: [{ id: "r1", amount_rub: "100.00", kind: "invite", created_at: "2026-08-20T12:30:00Z" }] });
    if (path === "/api/v1/me/transactions") return json([{ id: "tx1", kind: "bonus", amount: "100.00", balance_after: "125.00", status: "done", created_at: "2026-08-20T12:00:00Z" }]);
    if (path === "/api/v1/payments/card/packages") return json({ label: "Оплата", currencies: ["RUB"], packages: { starter: { credits: "100", prices: { RUB: "100" } } } });
    if (path === "/api/v1/payments/card/checkout") return json({ id: "pay1", status: "created", payment_url: "https://example.test/pay" });
    return json({ detail: `Unhandled ${method} ${path}` }, 404);
  });
}

async function openScenario(page: Page, scenario: (typeof scenarios)[number]) {
  await mockTelegram(page);
  await mockApi(page);
  await page.setViewportSize(scenario.viewport);
  await page.goto(`/?route=${scenario.route}`);
  await expect(page.locator("body")).toContainText("ROXY");
}

async function expectFriendlyScreenCopy(page: Page) {
  for (const paragraph of await page.locator(".screen-head p").all()) {
    await expect(paragraph).toHaveCSS("font-size", "0px");
    const afterContent = await paragraph.evaluate((element) => getComputedStyle(element, "::after").content);
    expect(afterContent).toContain("Выбирайте идею");
    expect(afterContent).not.toMatch(/KIE|provider|server routes|media routes|ui_schema|backend/i);
  }
}

test.describe("ROXY Mini App 100 пользовательских сценариев", () => {
  for (const scenario of scenarios) {
    test(`scenario ${scenario.id}: ${scenario.route} ${scenario.viewport.width}x${scenario.viewport.height}`, async ({ page }) => {
      await openScenario(page, scenario);
      await expectFriendlyScreenCopy(page);
      await expect(page.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
      await expect(page.getByRole("button", { name: /Создать/ })).toBeVisible();

      const body = page.locator("body");
      if (scenario.route === "home") {
        await expect(body).toContainText("Что создаём?");
        await page.getByRole("button", { name: /Фото/ }).first().click();
        await expect(body).toContainText("Настрой генерацию");
      }
      if (scenario.route === "feed") {
        await page.getByRole("button", { name: scenario.sort === "top_day" ? "Топ дня" : scenario.sort === "top" ? "Топ" : "Новые" }).click();
        await expect(body).toContainText("Работы сообщества");
      }
      if (scenario.route === "catalog") {
        await expect(body).toContainText("Готовые сценарии");
        await expect(page.locator(".catalog-model-section")).toHaveCount(0);
      }
      if (scenario.route === "create") {
        await expect(body).toContainText("Настрой генерацию");
        await page.locator("textarea").first().fill(`Сценарий ${scenario.id}: пикачу в неоне`);
        await expect(page.getByRole("button", { name: /Создать/ }).last()).toBeVisible();
      }
      if (scenario.route === "history") {
        await expect(body).toContainText("Все генерации");
        await page.getByRole("button", { name: /Nano Banana|AI генерация/ }).first().click();
        await expect(body).toContainText("Моя работа");
      }
      if (scenario.route === "profile") {
        await expect(body).toContainText("Публикации");
        await expect(body).toContainText("Ссылка на профиль");
      }
      if (scenario.route === "partners") {
        await expect(body).toContainText("Партнёры");
        await expect(body).toContainText("Реферальная ссылка");
      }
    });
  }
});
