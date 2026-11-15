
### 2026-11-15 — Crypto Pay HTTP logging and Mini App chunk recovery
- Baseline: KSU origin/main bee6030898cc97763bc3588745aafe4cc789fb12.
- Production evidence: 24 failed reconciliations of 5 Crypto Pay invoices because upstream returned HTTP 500/520; raw Cloudflare HTML appeared in app logs. Existing payment reconciliation backoff and idempotent webhook flow were inspected and preserved.
- Separate production browser error: ChunkLoadError for a hashed JS asset. The same asset now serves HTTP 200 from the current production container; this was likely a transient fetch/stale tab, not a permanently missing file.
- Change: provider errors expose HTTP codes without untrusted response body; no payment status mutations. Next.js React error boundary attempts one full reload for chunk failures per 5-minute session window, retaining manual reload; other errors use React reset.
- Tests: 6 red-to-green mock Crypto Pay HTTP 500/520 cases; 3 Node unit tests for chunk recovery and reload loop bound; full Next build/TypeScript succeeded, 24 static pages.
- Rollout: PR to main, protected CI, exact-SHA production build/deploy, check client error trends and external invoice reconciliation; if upstream stays down, do not manually credit payments.
