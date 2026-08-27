# Mini App short name deployment note

Set the BotFather Mini App short name only when that exact Direct Mini App short name exists:

```env
TELEGRAM_MINI_APP_SHORT_NAME=<botfather_short_name>
```

Use the exact short name configured in BotFather. When it is set, public social links are generated as:

```text
https://t.me/<bot_username>/<mini_app_short_name>?startapp=<payload>
```

When the variable is empty, ROXY falls back to bot `/start <payload>` links. The bot then renders the WebApp button with the same payload, avoiding Telegram's "application not found" error for non-existent short names.
