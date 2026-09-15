# Mini App interface language

ROXY Mini App supports Russian and English customer UI.

## Customer behavior

- The compact `RU / EN` switch is shown in the top bar next to the ROX balance.
- The same switch is available on standalone Mini App screens opened by deep link.
- A manual choice is persisted to `PUT /api/v1/me/preferences` as `ui_language=ru|en` and cached locally for fast startup.
- Existing `ui_language=auto` accounts remain supported. `auto` resolves from Telegram `language_code`; if Telegram does not provide one, ROXY keeps Russian as the compatibility default.
- Changing the interface language does not translate user-generated prompts or editable text.

## Implementation

`frontend/mini-app/components/ui-language-provider.tsx` owns language state and persistence.
`frontend/mini-app/lib/ui-language.ts` owns the RU/EN interface copy and dynamic UI patterns.

The provider wraps the entire authenticated Mini App in `app/layout.tsx`, so the language setting follows navigation between the main customer shell and standalone routes such as Payments, Prompt Tools, Settings, Support, and Trend.

When adding new customer-facing Russian copy, add the English equivalent to the language module and cover the affected flow with a browser test.
