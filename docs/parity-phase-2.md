# Phase 2 — Navigation and runtime ownership

Parent: #145

Scope:

- One customer navigation/router owner.
- Deterministic child routes and BackButton/browser history parity.
- Remove menu replacement races between legacy shell/economy/customer navigation.
- Replace broad DOM mutation observers with explicit events/state updates.
- Remove generation `window.fetch` interception.

Exit criteria:

- A single module owns customer route state and visible primary navigation.
- Browser history and Telegram BackButton resolve the same route stack.
- No broad body-subtree MutationObserver is used for navigation/economy/music behavior.
- No global `window.fetch` monkey patch remains for generation UI decoration.
