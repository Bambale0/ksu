# Kling 4.0 audio and product terminology — 2026-11-11

## Reproduction
A real iPhone Telegram Mini App screenshot displays internal KIE/Нейроныч
supplier names in three public controls. This is inappropriate UI copy and
misleadingly suggests video sound is unavailable in the native provider.

Current supplier's official /guide says native Kling 4.0 supports generated
sound with generate_audio=true (default) and silence with false, but NOT
native original-sound retention, elements, voices or reference_audios.
A retained successfully generated MP4 was inspected read-only with ffprobe:
AAC audio is present alongside H.264 video; one sample, not a guarantee.

## Fix + invariants
- User controls display only human concepts (sound from the source, characters,
  voices), no supplier names.
- Compatible native Kling receives explicit generate_audio=true in the frozen
  idempotent submission body. A true original-sound flag and video reference
  never turns into new sound: server preselects the capable route.
- Provider-only errors are translated at generation API and Telegram delivery
  boundaries. Internal logs keep useful provider/retry details for support.
- Certain upstream supplier credit rejection still follows existing
  idempotent refund path with appropriate user-visible language.
- Backward compatibility for old/frozen tasks, pricing, admin configurable
  routes, reference order, original audio intent.
- No made-up provider controls, wallet top-ups, provider balance changes,
  media rewrites, migrations or secret modifications.

## Regression + release
- Tests: supplier-native payload and audio on/off implications, frozen wire and
  provider idempotency; legacy route semantics; UI schema labels; API/Telegram
  error sanitization; supplier credit 402 and refunds.
- CI exact SHA followed by full main branch release gate, Playwright Chromium &
  iPhone WebKit, Docker immutable image parity, health and deployment marker.
- Real paid generation not automatically fired unless separately approved;
  supplier capabilities do not change by renaming UI controls.
- Remaining limitation: native supplier does not support copying original
  soundtrack from a video reference. A strict compatible route remains
  necessary until the supplier publishes a real matching control.

## Exact-head CI runner incident
Two independent workflow runs on the 2026-11-11 PR head failed **before tests**
at `Install MP4 tooling`: Ubuntu 26.04 runner `apt-get update` reported
`Temporary failure resolving 'archive.ubuntu.com'` and
`security.ubuntu.com`, then reached its five-minute timeout.
PostgreSQL and Redis Docker images did pull successfully on those runners.
This is a runner DNS/package installation incident, not a Kling regression.

Fix: `scripts/setup_ci_media_tools.sh` installs *both* ffmpeg/ffprobe from
`mwader/static-ffmpeg` using a verified immutable multi-arch image digest
`sha256:f5d100184884eb3e82b0eb14bb5ebf98da99826ac824989720297fb9ef21c822`.
The tooling itself is not removed; all tests still run. `e2e.yml` installs
real Chromium through Playwright without re-running apt on the hosted runner;
the browser journeys still fail if required browser libraries are missing.
The script runs in the PR CI and is validated by actual media/E2E steps.
