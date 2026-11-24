# ROXY web identity release recovery — 2026-11-24

## Checkpoint

- Draft PR #645 original head b80fc8f6c984822e14fcc89094293672410a73bd had a failing onboarding contract and browser audit; it was behind main.
- Recovery commits 52909b9021c555bafed1049e6353f477e58c6f2c, ce095d16e2d06ff7cd922a0485b81f7eb8502bad and d6bde38d7911afd00ed40abc1e72898776c48374 record the audit, add nine dependency behavior scenarios, and share the onboarding gate between cookie and native Telegram authentication.
- PR #660 passed all six workflows and was merged as 857f70c2c494ef84bda07754f31b8ce344a2af61. Its latest public layout, glass navbar, transparent RX, gallery, video loader and current profile placement are preserved.
- Isolated QA merge 44c180dd7e4e46de7aed1c65cb1adbdc30092360 resolved eight conflicting paths. Landing CTA opens /login with allowed query context; legacy browser login remains reachable for backwards compatibility; cookie logout revokes the server session before navigation, and native Telegram never displays web logout. The static browser-test server serves /login.
- Python compilation, Node syntax checks for login.js and the static server, and feature diff whitespace check against main passed. Full backend and browser tests still need exact-head CI. QA host does not have the backend dependencies or authenticated Git push configured.
- Product files are transferred by exact blob SHA. Main CONTEXT.md is preserved; this separate ledger records the recovery because transferring the full merged journal was blocked. Earlier branch history remains reachable.

## Release gate

Do not merge the draft or run a production migration before review, all required CI checks, schema and provider configuration validation, real cookie/native authentication, ownership and shared-wallet regressions, verified provider credentials, payment/generation reconciliation, and separate migration approval. No production data, balances, secrets, payment configuration or provider routing were changed in this recovery.
