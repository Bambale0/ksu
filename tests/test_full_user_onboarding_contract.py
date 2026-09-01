from pathlib import Path

from app.core.config import settings
from app.services.onboarding import OnboardingService, PRODUCT_ONBOARDING_VERSION


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"
COMPONENT = FRONTEND / "components" / "user-onboarding.tsx"
STYLES = FRONTEND / "components" / "user-onboarding.module.css"
PAGE = FRONTEND / "app" / "page.tsx"


def test_full_onboarding_is_mounted_as_customer_entry_experience() -> None:
    page = PAGE.read_text(encoding="utf-8")
    component = COMPONENT.read_text(encoding="utf-8")

    assert 'import { UserOnboardingGate } from "@/components/user-onboarding"' in page
    assert "<UserOnboardingGate />" in page
    assert 'role="dialog"' in component
    assert 'aria-modal="true"' in component
    assert "api.onboarding()" in component
    assert "await api.completeOnboarding()" in component


def test_onboarding_teaches_the_complete_creator_flow() -> None:
    component = COMPONENT.read_text(encoding="utf-8")

    assert component.count("visual:") >= 6
    assert "ROXY — ваша AI-студия в Telegram" in component
    assert "Выберите задачу — ROXY подберёт нужный инструмент" in component
    assert "Промпт и референсы" in component
    assert "Результат приходит в Telegram" in component
    assert "Профиль и лента" in component
    assert "Стоимость видна до запуска" in component
    assert "Начать создавать" in component


def test_onboarding_progress_is_resumable_but_completion_stays_server_owned() -> None:
    component = COMPONENT.read_text(encoding="utf-8")

    assert "roxy.onboarding.${version || \"current\"}.step" in component
    assert "window.localStorage.setItem" in component
    assert "window.localStorage.removeItem" in component
    assert "api.completeOnboarding()" in component
    assert 'window.location.replace(`/mini-app/?route=${target}`)' in component


def test_first_entry_content_deep_links_survive_onboarding_completion() -> None:
    component = COMPONENT.read_text(encoding="utf-8")

    assert "getStartParamFallback" in component
    assert "/^(feed_|remix_|profile_|posts_)/i" in component
    assert "if (hasContentLaunchTarget())" in component
    assert "window.location.reload()" in component


def test_onboarding_uses_native_telegram_back_button_and_no_drawn_back_control() -> None:
    component = COMPONENT.read_text(encoding="utf-8")

    assert "tg?.BackButton?.show?.()" in component
    assert "tg?.BackButton?.hide?.()" in component
    assert "tg?.BackButton?.onClick?.(back)" in component
    assert "tg?.BackButton?.offClick?.(back)" in component
    assert ">Назад<" not in component
    assert ">Пропустить<" in component


def test_onboarding_is_safe_area_and_small_screen_aware() -> None:
    styles = STYLES.read_text(encoding="utf-8")

    assert "var(--tg-safe-top" in styles
    assert "var(--tg-safe-bottom" in styles
    assert "@media (max-width: 390px)" in styles
    assert "@media (max-height: 720px)" in styles
    assert ":global(.onboarding-overlay:not(.roxy-onboarding-v2))" in styles


def test_legacy_product_version_rolls_forward_without_breaking_custom_versions(
    monkeypatch,
) -> None:
    assert PRODUCT_ONBOARDING_VERSION == "2"

    monkeypatch.setattr(settings, "onboarding_version", "1")
    assert OnboardingService._current_version() == "2"

    monkeypatch.setattr(settings, "onboarding_version", "v3-experiment")
    assert OnboardingService._current_version() == "v3-experiment"
