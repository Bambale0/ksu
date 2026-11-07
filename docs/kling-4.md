# Kling 4.0 through Kie.ai

The catalog contains `kling-4.0` (Omni/reference generation) and
`kling-4.0-keyframe` (first/middle/last frames). Both also accept text alone,
produce native audio, and support 3–30 seconds at 720p or 1080p.
Choose either entry under Kling in Create. Describe the scene and optionally
upload references. Use `@image_1`, `@video_1`, `@first_frame`, `@keyframe_1`,
`@last_frame`, or the exact character/voice name in the prompt.

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

Sources verified 2026-11-07:
- https://docs.kie.ai/market/kling/v4-reference-to-video.md
- https://docs.kie.ai/market/kling/v4-keyframe-to-video.md
- https://kie.ai/kling-4-0
