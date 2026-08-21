# Admin contour audit — 2026-08-21

## Scope

Checked the admin notification/broadcast path, public generation catalog, feed publication path, and default deployment topology for the KSU Mini App/backend.

## Findings fixed in this branch

### 1. Broadcast workers were not part of the default compose stack

`AdminNotificationService.start_campaign()` correctly creates `NotificationCampaignDelivery` rows, and `app.workers.admin_campaigns` can deliver them to Telegram. The default `docker-compose.yml` did not start this worker, so a production deploy that only used the main compose file could create campaigns that never left `pending`.

Fix: added both workers to the default stack:

- `notification-worker` — processes ordinary/test notification deliveries.
- `admin-campaign-worker` — processes admin campaign/broadcast deliveries.

### 2. Model picker exposed runtime implementation variants as customer choices

The public catalog could show separate T2I/I2I or T2V/I2V entries for the same product. That forced users to understand provider implementation details and produced duplicated model names.

Fix: public family variants are now coalesced by product key. Reference-capable products are shown as one customer-facing variant with automatic mode selection.

### 3. References were mandatory on I2I public forms

For a product that should work as both text-only and reference-based generation, the public UI schema still inherited provider-required reference fields from the I2I contract.

Fix: reference fields are optional on auto-routed public model cards. Backend routing now decides the executable provider model:

- no reference payload → T2I/T2V target;
- image/video reference payload → I2I/I2V target;
- input URL is promoted to the correct provider field automatically.

### 4. Feed/profile publication UI now exposes both surfaces

Foxgen's Mini App pattern separates profile publications from public feed posts and includes social actions on published cards.

Fix: the KSU Mini App now routes to a social-ready shell with:

- explicit `В профиль` publication;
- explicit `В ленту + профиль` publication;
- prompt/reference visibility toggles before publishing;
- feed/profile likes, shares, comments, repeat/remix, and owner removal actions;
- automatic feed refresh while the catalog is open.

## Admin contour notes

### Permissions and safety

The notification service uses `AdminPolicy.require_permission()` for reads and `AdminPolicy.authorize_action()` for campaign mutation/start/cancel paths. Campaign start requires confirmation and step-up validity.

### Idempotency

Campaign create/test/start/cancel run through `AdminCommandLedger.execute()`, so repeated admin submits should reuse the same command result when the same idempotency key is supplied.

### Delivery lifecycle

Campaign deliveries use explicit statuses:

- `pending`
- `sending`
- `retry`
- `sent`
- `failed`
- `suppressed`
- `undeliverable`
- `cancelled`

Leases and retry delays are centralized in `CampaignDeliveryService`.

### Delivery suppression

The worker respects inactive users and `UserPreference.notifications_enabled` / `marketing_notifications` before sending marketing campaign messages.

## Remaining follow-up

1. Add an admin console smoke/E2E test that creates a campaign, starts it, and verifies delivery rows leave `pending` when the worker runs.
2. Add production deploy/runbook check that verifies these processes are alive after deployment:
   - `app`
   - `generation-worker`
   - `media-worker`
   - `payment-worker`
   - `notification-worker`
   - `admin-campaign-worker`
3. Confirm live provider docs before changing individual model parameter ranges beyond the already encoded KSU contracts.