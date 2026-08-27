# Telegram Mini App direct links

ROXY social links prefer Direct Mini App URLs when BotFather has a matching short name.

Use this format for share, repeat, profile, referral and prompt links only when the short name exists:

```text
https://t.me/<bot_username>/<mini_app_short_name>?startapp=<payload>
```

The `<mini_app_short_name>` value is configured through `TELEGRAM_MINI_APP_SHORT_NAME` / `settings.telegram_mini_app_short_name` and must match the short name configured in BotFather for the Mini App.

Do not guess `app` or any other path segment. If the short name is absent or unknown, ROXY generates `https://t.me/<bot_username>?start=<payload>` instead; the bot preserves the payload into the WebApp button. Do not generate new public links as `https://t.me/<bot_username>?startapp=<payload>` because Telegram clients can open only the bot card for that shape.
