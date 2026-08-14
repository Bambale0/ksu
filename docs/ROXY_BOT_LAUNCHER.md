# ROXY Telegram bot launcher

The Telegram bot is intentionally a thin launcher for the ROXY Mini App.

## Main menu

The main inline keyboard is deliberately compact:

1. `🚀 Открыть ROXY` — full-width entry to `?route=home`.
2. `✨ Создать` / `▦ Каталог` — compact two-button row.
3. `≡ История` / `👤 Профиль` — compact two-button row.

When `PUBLIC_BASE_URL` is configured, every visible product action is a Telegram `web_app` button and opens the matching Mini App route. The text bot does not duplicate product screens.

Callback data on these buttons exists only as a deployment fallback when `PUBLIC_BASE_URL` is empty, so operators can still recover navigation instead of presenting broken WebApp URLs.

## Product boundary

The bot remains responsible for `/start`, onboarding, notifications, support/admin flows and deep-link entry. Product work — creation, discovery, history, profile/cabinet, wallet and creator workflows — belongs to the Mini App.
