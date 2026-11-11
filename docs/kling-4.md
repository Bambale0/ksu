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
Images and videos are limited to 10 MB each. Image elements need 2–4 views.
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

## Curated trend with administrator-owned video (2026-11-11)

An admin can create a one-stage Kling 4.0 reference-mode Trend with one fixed,
verified template clip and exactly two visitor photos. In the Mini App's
**Тренды → Добавить** editor choose `Kling 4.0`, upload the permanent MP4/MOV
under **Постоянное видео для Kling 4.0**, then select a fixed video format and
quality and set a hidden prompt using `@image_1`, `@image_2` and `@video_1`.
The editor locks customer photo minimum/maximum to two. Upload a separate
public preview; the video input URL is not used as a preview.

The clip is stored through `/uploads/template-video` with independently
verified metadata and cannot be pruned as an ordinary user's reference. The
public client sees two photo slots and a single Generate action; the server
composes `image_urls=[customer_photo_1,customer_photo_2]` and
`video_urls=[admin_video]` only in a scoped Trend generation. This does not
enable template clips in ordinary customer Kling create requests.

Existing video-reference ×2 pricing is retained, with unit prices and provider
routing sourced from the current admin runtime configuration. Paid provider
quality and fidelity still need live acceptance; static contracts and mocked
browser tests alone do not prove source-video imitation.
