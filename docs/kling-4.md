# Kling 4.0 through Kie.ai

The catalog contains `kling-4.0` (Omni/reference generation) and
`kling-4.0-keyframe` (first/middle/last frames). Both also accept text alone,
produce native audio, and support 3–30 seconds at 720p or 1080p.
Choose either entry under Kling in Create. Describe the scene and optionally
upload references. Use `@image_1`, `@video_1`, `@first_frame`, `@keyframe_1`,
`@last_frame`, or the exact character/voice name in the prompt.
For the reference model, ROXY also accepts compact `@image1` / `@Image1` and
`@video1` / `@Video1` as input aliases when the corresponding upload slot exists;
they are normalized to `@image_1` / `@video_1` before quoting, storage, and
provider submission. Unknown slot numbers are rejected. A declared element or
voice named exactly `image1` / `video1` takes precedence over the alias.
Keyframe-mode identifiers (`@first_frame`, etc.) are unchanged.

Reference mode accepts 10 images, 5 videos, 7 named elements (at most 3 video
elements), and 3 named voices, with at most 15 entries combined. Video references
and video elements together are limited to 5 and 30 seconds in total. Individual
reference clips must be 2–30 seconds; character clips must be 3–8 seconds.
Video duration must come from the authenticated owner's measured ROXY uploads.
Images remain limited to 10 MB in ROXY. Kling 4 Omni reference videos (`video_urls`, including administrator-pinned trend clips) accept up to `KLING4_REFERENCE_VIDEO_MAX_MB` (default 100 MB); other input types retain their own limits. Image elements need 2–4 views.
Names must be unique ignoring case, 1–20 Latin/Chinese letters, digits or `_`;
provider-reserved names cannot be used. Descriptions are limited to 100 characters.
Voices can also be attached to a character. Voice detection and single-shot
character-video suitability remain provider checks.

Keyframe mode accepts a first frame, up to 8 ordered middle frames and a last
frame. Middle/last frames require the first frame. The combined frame cap is
`min(duration + 1, 10)`. Upload middle frames in chronological order.
The output follows the first frame's ratio when supplied. Explicit output ratios
are 16:9, 9:16, 1:1 and 21:9, following ROXY's existing explicit-ratio policy.
Prompts are limited to 8000 characters. 4K and Flash are not part of this integration.

User-approved bootstrap tariffs are 30 ROX/s at 720p and 45 ROX/s at 1080p.
They are editable through the existing authenticated admin generation-pricing
tariff, including `by_resolution`. Video references, including video elements,
use ROXY's existing 2× retail multiplier. Five seconds at 1080p costs 225 ROX,
or 450 ROX with a video reference. Kie procurement credits and its input/output
billing formula are separate from this retail tariff.

Both models use the existing `KIE_API_KEY`, jobs create/query client, bound and
verified callback, background outbox, polling recovery, result media ingestion,
history, repeat and refund path. No additional secret or migration is required.
Provider submissions preserve exact model and input snapshots. Ambiguous
submissions retain the existing duplicate-prevention/reconciliation behavior.
No paid live generation was used by the automated contract tests.

Owner repeats preserve named elements, voices and keyframe roles. Public-feed
repeats disclose no author reference URLs: ROXY replaces every media slot with
the viewer's own uploads, in order within each media type, while retaining the
server-owned names and scene structure. Additional references are validated
against the same provider quotas. The bounded recent-reference library now
retains 48 items per media type, enough for a maximal valid Kling composition
of 36 images plus 7 character voices; feed repeat accepts up to 48 reference IDs.

Sources verified 2026-11-07:
- https://docs.kie.ai/market/kling/v4-reference-to-video.md
- https://docs.kie.ai/market/kling/v4-keyframe-to-video.md
- https://kie.ai/kling-4-0

## Neironych route (2026-11-08)

The existing admin provider-routing setting now allows `kling-4.0` to choose
Neironych and Kie in either order or alone. The default remains Kie first until
upstream release acceptance. This does not change `kling-4.0-keyframe`.

Compatible text/image/video requests map to Neironych's native Kling 4 contract.
Image/video roles retain order, including repeated URLs; `@image_N` and
`@video_N` become `@Image N` and `@Video N` only in the frozen wire request.
Named elements, voices, original-sound controls and text-only auto geometry
cannot be represented equivalently and fall back before any Neironych POST.
Kie inputs remain unchanged. Existing paid-submission uncertainty, polling,
download, refund and route-snapshot protections are reused.

The initial two neutral upstream probes failed moderation. A later explicitly
requested probe completed and its full MP4 and 3-second usage were verified;
Kling 4.0 is now published by Neironych's authenticated catalog enable gate.
KSU rollout still requires partner-native acceptance, exact-head CI, deployment
verification and the audited admin route switch. Until that switch, Kie remains
primary; this section does not claim an already completed KSU rollout.

## Audio preservation and provider admission (2026-11-11)

For `kling-4.0`, the configured production preference is read from the
audited `generation_provider_routes` setting. Compatible requests remain on
the configured primary supplier; an explicit `keep_original_sound=false` is
equivalent to omission (the KIE upstream contract defaults to false) and does
**not** trigger a Neironych→KIE fallback. It is never silently converted to
`generate_audio=false`: Neironych generates its normal native audio.

`keep_original_sound=true` with `video_urls` **requires KIE** because the
currently reviewed Neironych Kling API has no native equivalent. A request
containing `elements` or `voices` also requires KIE. At admission, before
any ROX debit/outbox, only provider-capable branches are retained in the
immutable per-generation route snapshot. Unsupported configurations with a
Neironych-only route fail before wallet debit, with a user-readable error.
Other models and already-accepted/frozen generations keep existing routes.

The Mini App labels the original-audio toggle as KIE-only. A certain KIE
supplier-credit rejection (HTTP or payload code 402) is classified as
permanent, refunded idempotently, and localized to Russian. Users may disable
original-audio preservation to use Neironych's generated audio, **only by
explicit choice**; original-audio requests are never degraded in the backend.
No provider API key, supplier purchase cost, route, model, or retail ROX tariff
is hardcoded. KIE supplier credits still require an actual KIE top-up; code
cannot create provider funds.

Regression cases cover absent/false/true audio flag, pre-debit routing,
KIE-only restrictions, no source mutation, upstream wire body, and 402 vs
ambiguous submission error handling.

## Customer-facing sound controls (2026-11-11)

The ROXY Mini App presents model capabilities, never internal supplier names:
- `Сохранить звук исходного видео` — user chooses to retain the input clip's
  original audio when uploading a video. This remains a strict capability: do
  not silently substitute an AI-generated soundtrack if the chosen provider
  cannot fulfill the request.
- `Персонажи и объекты` and `Голоса` — customer-visible capabilities; routing
  and compatibility validation occur only on the backend.

Verified upstream guide `https://api.нейроныч.online/guide`:
`kling-4.0` supports `generate_audio=true` (default) and
`generate_audio=false` (silent output), but does **not** document native
original-track preservation, named subjects/voices or audio references.
For native-compatible requests, ROXY sends `generate_audio=true` explicitly
in the frozen idempotent POST, preserving reference order. Original-sound
requests keep their existing supplier-capable route. There is no fake
`keep_original_sound` mapping, no audio replacement, and no silent downgrade.

A read-only `ffprobe` of an existing successful native Kling 4.0 MP4
(2026-11-08) confirmed H.264 video **and AAC audio** streams. This proves
that example contains audio, not that every future rendering will.
The user API and Telegram failure messages for Kling 4.0 do not expose
supplier brand names, routes, upstream codes or credentials; internal logs
retain enough provenance for incident reconciliation. This is presentation
sanitization, not deletion of technical error evidence.


## Curated Kling 4.0 video trend with flexible photo references

Administrator creates an ordinary one-stage Kling 4.0 trend with a permanently
uploaded **video input** in the dedicated admin-only upload field, which is
separate from the publicly displayed preview. The admin chooses the permissible
photo-upload range; the hidden prompt's indexed `@image_N` slots determine
the required minimum. Customers may provide additional images within that
range and the model's real capacity (10 images), subject also to the 15-item
combined budget shared by images, named elements, voices and the pinned clip.
A video-only recipe can explicitly allow zero customer uploads. The admin-owned clip is injected as `@video_1` and never needs to
be uploaded again by customers. Price comes from the existing configured
model tariff, including the reference-video multiplier.

If a non-pinned Kling prompt refers to `@image_2`, server normalization
automatically declares at least two image slots and preflight validates two
distinct placeholders before any billing. A prompt referring to a video without
a pinned clip returns a clear preflight error. The admin editor also synchronizes
the photo fields, displays actionable validation and 502 messages and keeps
idempotency keys stable for repeated identical create/update submissions.

For pinned clips: product-owned verified MP4/MOV, 2–30 seconds and 100 MB default cap (configurable via `KLING4_REFERENCE_VIDEO_MAX_MB`),
separate additive `template_video_references` metadata from migration 0045.
The public DTO never exposes the private clip or hidden prompt; clients cannot
substitute a video or modify fixed ratio/quality. Never replay a timed-out
paid generation blindly. The supplier route remains runtime configurable.
