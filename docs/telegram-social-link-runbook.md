# Telegram social link runbook

When a user reports that a share/repeat link opens only the Telegram bot card:

1. Check `BOT_USERNAME`.
2. Check `TELEGRAM_MINI_APP_SHORT_NAME`.
3. Generate a sample link in this shape:

```text
https://t.me/<bot_username>/<mini_app_short_name>?startapp=feed_<generation_uuid>_ref_<telegram_id>
```

4. Open it on mobile Telegram and confirm ROXY Mini App opens directly.
5. If it still opens only the bot card, the Mini App short name in env does not match BotFather.
