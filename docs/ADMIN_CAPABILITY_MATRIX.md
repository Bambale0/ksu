# Admin capability parity matrix

Source baseline: NEUROMIX admin contour migration brief supplied on 2026-08-13.
Target baseline: `Bambale0/ksu` `main` at `bebb81e0d6b5dfda6a68341579d8d762166a2c85`.

The matrix is intentionally completed before implementation. Existing `ksu` capabilities are reused rather than duplicated.

| Capability | Existing ksu surface | Target module/service | Transport | R/W | Audit | Idempotent | Worker | Gap |
|---|---|---|---|---|---|---|---|---|
| Admin authentication, RBAC, MFA/step-up | `app/api/admin_deps.py`, `app/services/admin_security.py`, `admin_accounts/auth/audit` | `admin_policy` facade over existing security | HTTP/Web/Telegram | R/W | yes | session-specific | no | adapt/reuse |
| Admin command ledger | none | `app/db/admin_models.py`, `app/services/admin_commands.py` | shared | W | yes | yes | no | missing |
| Telegram `/admin` launcher | `app/bot/handlers/admin.py` | `admin_telegram_ui` | Telegram | R | yes where applicable | n/a | no | partial |
| Telegram stats summary | none | `AdminSummaryService` + Telegram thin adapter | Telegram | R | optional | n/a | no | missing |
| Telegram user lookup | web/API user list/detail exists | `AdminUserService` | Telegram/HTTP/Web | R | yes for sensitive reads | n/a | no | adapter missing |
| Manual credit/debit | `POST /api/v1/admin/users/{id}/wallet-adjustments` writes directly in route | `AdminUserService.adjust_balance` | Telegram/HTTP/Web | W | yes | yes | no | refactor |
| Block/unblock user | `PATCH /api/v1/admin/users/{id}/status` | `AdminUserService.block/unblock` | Telegram/HTTP/Web | W | yes | yes | no | refactor/aliases |
| Partner analytics | partner service/cabinet exists | `AdminPartnerService` | Telegram/HTTP/Web | R | yes | n/a | no | admin surface missing |
| Partner withdrawal queue/actions | data model exists | `AdminPartnerService` | Telegram/HTTP/Web | R/W | yes | yes for actions | no | missing |
| Finance dashboard/export | payment/admin operations data exists | `AdminFinanceService` | Telegram/HTTP/Web | R | yes | n/a | no | partial |
| XLS/CSV exports | none | `AdminFinanceService` export serializers | Telegram/Web | R | yes | n/a | no | missing |
| Pricing/packages/image/video/partner exchange/prompt costs | model catalog has runtime prices but no versioned admin tariff domain | `AdminPricingService`, `TariffVersion` | Telegram/HTTP/Web | R/W | yes | yes publish | no | missing |
| Promo create/lookup/activate/deactivate | user promo redemption exists | `AdminPromoService` | Telegram/HTTP/Web | R/W | yes | yes writes | no | admin management missing |
| Prompt library moderation | none found | `AdminPromptModerationService` | Telegram/HTTP/Web | R/W | yes | yes moderation actions | no | missing |
| Subscription-required toggle | none found | `AdminRuntimeConfigService` | Telegram/Web | R/W | yes | yes | no | missing |
| Broadcast preview/confirm | durable notification delivery exists, no campaign admin domain | `AdminNotificationService` | Telegram/HTTP/Web | R/W | yes | yes | yes | partial infrastructure |
| AI admin | none | `AdminAiService` interface | Telegram/Web | R/W | yes | command dependent | optional | missing |
| Runtime config/preset reload | model catalog exists | `AdminRuntimeConfigService` | Telegram/Web | W | yes | yes | no | missing |
| Internal signed health/summary/users | no `/internal/admin/*` surface | `app/api/internal_admin.py` | signed HTTP | R | yes | n/a | no | missing |
| Internal block/unblock/balance | existing browser-admin routes use bearer admin session | shared services + signed adapter | signed HTTP | W | yes | yes | no | missing transport |
| Internal generations/finance/payments | partial browser-admin read routes | signed adapter over shared services | signed HTTP | R | yes | n/a | no | partial |
| Payment recheck/reprocess | reconcile exists; no command-ledger reprocess contract | `AdminPaymentService` | Telegram/HTTP/Web | W | yes | yes | optional | partial |
| Tariff versions/publish | none | `AdminPricingService` | signed HTTP/Web | R/W | yes | yes | no | missing |
| Operations list/detail/timeline | `admin_operations.py` exists | `AdminOperationService` | HTTP/Web | R | yes | n/a | no | partial |
| Operation replay/refund | generation/admin operations partially exist | `AdminOperationService` | Telegram/HTTP/Web | W | yes | yes | generation worker | partial |
| Support ticket assign/update/reply | public support exists; no operator domain/outbox | `AdminSupportService`, support outbox | Telegram/HTTP/Web | R/W | yes | yes reply | yes | missing |
| CMS documents/version/publish | none | `AdminCmsService` | HTTP/Web | R/W | yes | yes publish | no | missing |
| Notification campaigns preview/create/test/start/cancel | notification outbox/delivery exists | `AdminNotificationService`, campaign/delivery models | Telegram/HTTP/Web | R/W | yes | yes | yes | missing admin domain |
| Admin-only trends | social feed exists, no trend admin model found | `AdminSocialService` | Web | R/W | yes | yes | no | missing |
| Feed moderation blur/remove | social service exists | `AdminSocialService` | Web | W | yes | yes | no | missing |
| Privileged generation preview | generation catalog exists | `AdminGenerationPreviewService` | Web | R/W | yes | yes for execution | generation worker | missing |
| Backend admin revalidation | existing admin deps enforce server side | shared `admin_policy` | Web/HTTP | R/W | yes | n/a | no | reuse |
| Support durable worker | none | `app/workers/admin_support.py` | worker | W | yes | idempotent lease | yes | missing |
| Campaign durable worker | generic notification worker exists | extend with campaign materialization/delivery | worker | W | yes | idempotent lease | yes | partial |

## Architectural target

```text
Telegram /admin ─┐
Web admin UI ────┼──> admin_policy ──> admin_services ──> DB/domain
Signed HTTP API ─┘          │                 │
                            │                 ├──> admin_command_ledger
                            │                 ├──> support outbox
                            │                 └──> notification campaigns/deliveries
                            └──> audit

workers: support outbox + notification campaign delivery
```

## Implementation order

1. Introduce shared admin domain models, command ledger, redaction, policy facade and migration.
2. Move user status/balance writes behind shared services; retain current `/api/v1/admin/*` contracts.
3. Add signed `/internal/admin/*` router with exact-body HMAC, timestamp skew, network allowlist, request IDs and required write headers.
4. Add versioned tariffs, support outbox, CMS versioning and notification campaigns.
5. Extend Telegram `/admin` into a thin FSM/callback shell over shared services.
6. Extend web admin console over the same services and server-confirmed permissions.
7. Add/extend workers and contract/integration/UI tests.

## Security invariants

- No admin route or callback trusts hidden UI state.
- Every privileged handler revalidates admin policy server-side.
- Internal API HMAC signs timestamp + request id + method + path + exact raw body bytes.
- Internal write requests require `Idempotency-Key`, `X-Admin-User-Id`, and `X-Request-Id`.
- Internal API enforces configured network allowlist before command execution.
- Destructive or expensive commands require explicit confirmation/step-up policy.
- Request, response and operation representations redact `token`, `secret`, `password`, `authorization`, `api_key`, `webhook`, and `callback` keys recursively.
- Admin command ledger is append-only from application code; duplicate idempotency keys replay the stored result and never repeat the side effect.
- Support replies and campaign sends are durable worker side effects, never request-lifecycle-only sends.
