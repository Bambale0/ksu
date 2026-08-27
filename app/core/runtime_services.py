from __future__ import annotations

# Services that execute the application image in production. Keep this list in
# sync with docker-compose.yml and the deploy workflow; regression tests enforce
# that contract so a newly added worker cannot silently remain on an old image.
APPLICATION_SERVICES = (
    "app",
    "generation-worker",
    "media-worker",
    "payment-worker",
    "notification-worker",
    "admin-campaign-worker",
    "prompt-tool-worker",
    "creator-partnership-worker",
)

# Every long-running Python worker must publish a Redis heartbeat. The app itself
# is covered by /health/ready and therefore is intentionally not listed here.
OPERATIONAL_WORKERS = APPLICATION_SERVICES[1:]
