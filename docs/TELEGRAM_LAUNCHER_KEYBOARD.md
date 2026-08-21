# Telegram launcher keyboard contract

ROXY uses two Telegram keyboard surfaces for `/start`:

1. Inline keyboard under the launcher message
   - one button only: `🚀 Открыть ROXY`
   - opens the Mini App through `web_app=WebAppInfo(...)`

2. Persistent reply keyboard below the input field
   - `🏠 Меню`
   - `🆘 Поддержка`

Prompt tools must not be pinned in the reply keyboard. They live inside the Mini App and may be shown as contextual inline buttons only when a user taps an old cached prompt shortcut.
