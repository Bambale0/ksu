# ROXY Creator / Influencer Partnership

Creator partnership is a separate product and accounting domain from the automatic referral program.

## Accounting boundary

Automatic referrals remain unchanged:

- 30% from level 1 real top-ups;
- 5% from level 2 real top-ups;
- rewards are withdrawable through `ReferralReward` / `PartnerWithdrawal` accounting.

Creator partnership grants are different:

- negotiated manually per channel / creator;
- stored in `CreatorPartnershipAgreement.monthly_rox`;
- credited to the normal spend wallet with transaction kind `creator_monthly_grant`;
- **not withdrawable**;
- never create or mutate `ReferralReward` rows;
- unique per `agreement_id + YYYY-MM` and wallet-idempotent with `creator-grant:<agreement>:<period>`.

This makes a monthly ROX allowance a content-production budget, not cash-equivalent referral income.

## User lifecycle

Mini App `Профиль` calls:

- `GET /api/v1/creator-partnership`
- `POST /api/v1/creator-partnership/applications`

An application contains:

- channel/project name;
- HTTPS channel URL;
- audience size;
- optional average views;
- requested cooperation format;
- free-form note.

Only one pending application is allowed. Submission is idempotent.

States:

- `pending`
- `approved`
- `rejected`
- `canceled`

An approved application has a separate agreement with:

- `active / paused / ended` status;
- individual terms summary;
- monthly ROX allowance;
- structured `terms` JSON for future extensions;
- start/end dates.

## Admin lifecycle

Admin API prefix:

`/api/v1/admin/creator-partnership`

Required permissions:

- read: `partners.read`
- decisions/updates/grants: `partners.manage`

Mutations are protected by the existing admin control plane:

- explicit `X-Confirm-Action`;
- `Idempotency-Key` through `AdminCommandLedger`;
- audit trail through `AdminAuditService`;
- manual grant additionally requires fresh MFA step-up.

A standalone operational surface is available at:

`/admin-app/creator-partnership.html`

It supports reviewing applications, approving/rejecting with individual terms, editing agreement status/allowance, reviewing grant history and making an explicitly confirmed MFA-step-up manual period grant.

## Monthly worker

`python -m app.workers.creator_partnership`

The worker checks active agreements periodically. It grants the current `YYYY-MM` period only once and commits wallet credit + grant row + notification in one database transaction.

Configuration:

`CREATOR_PARTNERSHIP_GRANT_INTERVAL_SECONDS=3600`

The Docker Compose deployment includes one `creator-partnership-worker` service. The database uniqueness rule and wallet idempotency are the final duplicate protection.

## Failure behavior

- inactive/paused/ended agreements cannot mint a scheduled or manual grant;
- periods before agreement start or after agreement end are rejected;
- repeated period processing returns the existing grant;
- creator grants never touch withdrawable referral accounting;
- user/admin state changes produce durable notifications and admin audit events where appropriate.
