from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINI = ROOT / "app" / "web" / "mini_app"
API = ROOT / "app" / "api" / "v1"


def _read(root: Path, name: str) -> str:
    return (root / name).read_text(encoding="utf-8")


def test_functional_runtime_mounts_before_dynamic_customer_surfaces() -> None:
    integration = _read(MINI, "shell-integration.js")
    runtime = _read(MINI, "roxy-functional-runtime.js")

    assert '/mini-app/roxy-functional-runtime.js' in integration
    assert integration.index("mountFunctionalRuntime();") < integration.index("mountProfileTools();")
    assert integration.index("mountFunctionalRuntime();") < integration.index("mountRoxyBrand();")
    for token in (
        "installRandomUuidFallback()",
        "protectCanonicalHistory()",
        "observeNotificationSemantics()",
        "copyText",
        "window.RoxyFunctionalRuntime",
    ):
        assert token in runtime


def test_canonical_back_stack_is_not_overwritten_by_legacy_top_level_shell() -> None:
    runtime = _read(MINI, "roxy-functional-runtime.js")
    navigation = _read(MINI, "roxy-customer-navigation.js")

    assert "current?.roxyNavigation" in runtime
    assert "data?.ksuShell" in runtime
    assert "!data?.nested" in runtime
    assert "nativeReplaceState(data, title, url)" in runtime
    assert "window.history.pushState(historyState(initial)" in navigation
    assert 'window.addEventListener("popstate", handlePopState)' in navigation


def test_catalog_buttons_stay_inside_roxy_router_and_keep_back_history() -> None:
    discovery = _read(MINI, "roxy-discovery.js")

    assert 'openRoute("trends")' in discovery
    assert 'openRoute("prompt-tools")' in discovery
    assert 'button("", openCommunityFeed, "roxy-catalog-quick-card")' in discovery
    assert 'button("Открыть ленту", openCommunityFeed, "text-button")' in discovery
    assert 'window.location.assign("/mini-app/trends.html")' not in discovery
    assert 'window.location.assign("/mini-app/prompt-tools.html")' not in discovery
    assert 'card.addEventListener("keydown"' in discovery


def test_read_notifications_are_not_dead_clickable_buttons() -> None:
    runtime = _read(MINI, "roxy-functional-runtime.js")
    profile = _read(MINI, "profile-tools.js")

    assert 'button.notification-item' in runtime
    assert "button.disabled = !unread" in runtime
    assert 'button.setAttribute("aria-disabled", "true")' in runtime
    assert "attributeFilter: [\"class\"]" in runtime
    assert 'card.addEventListener("click", () => markOneRead(item.id, card));' in profile
    assert '/api/v1/notifications/${encodeURIComponent(id)}/read' in profile


def test_request_id_and_clipboard_have_telegram_webview_fallbacks() -> None:
    runtime = _read(MINI, "roxy-functional-runtime.js")
    prompt_tools = _read(MINI, "prompt-tools.js")
    bulk = _read(MINI, "bulk.js")
    create_center = _read(MINI, "roxy-create-center.js")

    assert "cryptoApi.getRandomValues(bytes)" in runtime
    assert 'Object.defineProperty(globalThis.crypto, "randomUUID"' in runtime
    assert "navigator.clipboard?.writeText" in runtime
    assert 'document.execCommand("copy")' in runtime
    assert "tg?.showPopup?." in runtime
    assert ".tool-copy-button" in runtime
    assert "crypto.randomUUID()" in prompt_tools
    assert "crypto.randomUUID()" in bulk
    assert "crypto.randomUUID()" in create_center


def test_primary_navigation_and_home_controls_have_action_handlers() -> None:
    navigation = _read(MINI, "roxy-customer-navigation.js")
    brand = _read(MINI, "roxy-brand.js")
    discovery = _read(MINI, "roxy-discovery.js")
    parity = _read(MINI, "roxy-parity-navigation.js")

    for route in ("home", "catalog", "create", "history", "profile"):
        assert f'["{route}"' in navigation
    assert 'button.addEventListener("click", () => open(route));' in navigation
    assert "roxyCreateCta" in brand
    assert "roxy-promo-cta" in discovery
    assert "roxy-promo-dot" in discovery
    for label in ("Каталог", "Лента", "Тренды", "Prompt", "Batch", "Референсы", "События", "Поддержка"):
        assert label in parity


def test_create_and_generation_controls_are_wired_end_to_end() -> None:
    app = _read(MINI, "app.js")
    center = _read(MINI, "roxy-create-center.js")
    music = _read(MINI, "roxy-music.js")
    generations = _read(API, "generations.py")

    for token in (
        'mediaCard({ type: "image"',
        'mediaCard({ type: "video"',
        'mediaCard({ type: "audio"',
        "void chooseMedia(type)",
        'button("✨ Улучшить текущий"',
        'button("🖼 Промпт по фото"',
        "/api/v1/uploads/kie",
        "/api/v1/prompt-tools/prompt-builder",
    ):
        assert token in center
    for token in (
        'dom.resetButton.addEventListener("click"',
        'dom.createButton.addEventListener("click"',
        "/api/v1/generations/quote",
        "/api/v1/generations",
        "/recreate",
    ):
        assert token in app
    assert 'document.addEventListener("click", interceptMusicCard, true)' in music
    assert 'window.KsuStudioShell?.open?.("home")' in music
    assert 'RoxyCustomerNavigation?.open?.("home")' not in music
    assert "models.append(MusicGenerationService.public_model())" in generations


def test_history_controls_cover_open_repeat_hide_restore_and_delete() -> None:
    app = _read(MINI, "app.js")
    management = _read(MINI, "roxy-history-management.js")
    social = _read(MINI, "social.js")
    generations = _read(API, "generations.py")

    for token in ("Открыть", "Повторить", "ksu-history-close", "ksuHistoryMore", "loadHistoryPage(false)"):
        assert token in app
    for token in ("Управлять", "Скрыть", "Вернуть", "/history/restore"):
        assert token in management
    assert "confirmHistoryRemoval" in social
    assert '@router.delete("/{generation_id}/history")' in generations
    assert '@router.post("/{generation_id}/history/restore")' in generations


def test_wallet_checkout_controls_have_server_contracts() -> None:
    wallet = _read(MINI, "wallet.js")
    card = _read(MINI, "primary-card-checkout.js")
    surface = _read(MINI, "payment-surface.js")
    payments = _read(API, "payments.py")
    card_api = _read(API, "card_payments.py")

    for token in (
        'dom.checkoutButton.addEventListener("click"',
        'button.addEventListener("click", () =>',
        'reopen.addEventListener("click"',
        'refresh.addEventListener("click"',
        '"Idempotency-Key"',
    ):
        assert token in wallet
    for token in (
        'pay.addEventListener("click"',
        'refresh.addEventListener("click"',
        'currency.addEventListener("change"',
        'email.addEventListener("input"',
        '"Idempotency-Key"',
    ):
        assert token in card
    assert 'lavaButton.addEventListener("click"' in surface
    assert 'cryptoButton.addEventListener("click"' in surface
    assert '@router.post("", status_code=201)' in payments
    assert "Idempotency-Key" in payments
    assert "/checkout" in card_api


def test_profile_partner_support_and_social_controls_have_backends() -> None:
    cabinet = _read(MINI, "roxy-profile-cabinet.js")
    profile = _read(MINI, "profile-tools.js")
    partner = _read(MINI, "partner.js")
    social = _read(MINI, "social.js")
    referrals = _read(API, "referrals.py")
    support = _read(API, "support.py")
    notifications = _read(API, "notifications.py")

    for token in ("Мои ROX", "История", "Партнёры ROXY", "Настройки", "scrollPartner()", "creatorPartnershipEntry"):
        assert token in cabinet
    for token in ("Сохранить", "Прочитать все", "Создать обращение", "Ответить", "Закрыть", "Переоткрыть"):
        assert token in profile
    for token in ("Скопировать", "Пригласить", "Партнёры ROXY", "Начисления", "Партнёры", "Деньги", "Перевести в ROX", "Оформить вывод", "Отменить"):
        assert token in partner
    for token in ("Найти", "Подписаться", "Отписаться", "Удалить"):
        assert token in social
    for route in ("/wallet-transfers", "/withdrawals"):
        assert route in referrals
    assert '@router.post("/tickets"' in support
    assert '@router.post("/read-all")' in notifications


def test_catalog_tools_batch_feed_and_onboarding_controls_have_handlers() -> None:
    trends = _read(MINI, "trends.js")
    prompt = _read(MINI, "prompt-tools.js")
    batch = _read(MINI, "bulk.js")
    feed = _read(MINI, "feed.js")
    onboarding = _read(MINI, "onboarding.js")
    preset = _read(MINI, "roxy-preset-editor.js")

    for token in ("trend-filter", "trend-card", "trend-runner-close", "trend-upload", "trend-run-button", "runTrend"):
        assert token in trends
    for token in ("tool-tab", "tool-upload", "tool-submit", "tool-copy-button", "submitTool"):
        assert token in prompt
    for token in ("batchUpload", "batchStart", "batch-retry", "batch-history-hide", "retryFailed", "startBatch"):
        assert token in batch
    for token in ("open-feed", "close-feed", "like", "comments", "share", "remix", "publish-profile", "publish-feed"):
        assert token in feed
    for token in ('start.addEventListener("click", complete)', 'retry.addEventListener("click", loadStatus)', "onboarding-link"):
        assert token in onboarding
    for token in ("Редактировать", "Сохранить изменения", "Отмена", "savePreset"):
        assert token in preset


def test_embedded_child_routes_and_back_controls_are_wired() -> None:
    children = _read(MINI, "roxy-child-screens.js")
    batch = _read(MINI, "roxy-batch-embedded.js")
    author = _read(MINI, "roxy-author-profile.js")

    for route in ("notifications", "support", "creator", "subscriptions", "author", "references", "presets", "batch", "trends", "prompt-tools"):
        assert f"{route}:" in children or f'"{route}":' in children
    assert "window.history.back()" in children
    assert "roxy-child-screen-back" in children
    assert 'close.addEventListener("click", closeFromUser)' in batch
    assert 'tg?.BackButton?.onClick?.(onBackButton)' in batch
    assert 'action.addEventListener("click", () => toggleSubscription' in author