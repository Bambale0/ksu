# Telegram Mini App direct links

ROXY social links must open the Mini App directly, not only the bot profile.

Use this format for share, repeat, profile, referral and prompt links:

```text
https://t.me/<bot_username>/<mini_app_short_name>?startapp=<payload>
```

The `<mini_app_short_name>` value is configured through `TELEGRAM_MINI_APP_SHORT_NAME` / `settings.telegram_mini_app_short_name` and must match the short name configured in BotFather for the Mini App.

Do not generate new public links as `https://t.me/<bot_username>?startapp=<payload>`; Telegram clients can open only the bot card for that shape.
