# Mini App short name deployment note

Production must set the BotFather Mini App short name:

```env
TELEGRAM_MINI_APP_SHORT_NAME=app
```

Use the exact short name configured in BotFather. New public social links are generated as:

```text
https://t.me/<bot_username>/<mini_app_short_name>?startapp=<payload>
```

Without the path segment, Telegram can open only the bot profile/card instead of ROXY Mini App.
