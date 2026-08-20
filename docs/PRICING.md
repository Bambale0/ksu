# ROXY generation pricing

**Baseline date:** 2026-08-20.

This is the compact human-readable generation tariff reference. Runtime authority remains the backend model catalog plus the latest published Admin Tariffs override.

| Product | Price |
| --- | ---: |
| Nano Banana PRO | 25 ROX |
| WAN 2.7 photo | 20 ROX |
| GPT Image 2 | 20 ROX |
| Nano Banana 2 | 25 ROX |
| Nano Banana 2 Lite | 25 ROX |
| Seedream 4.5 | 20 ROX |
| Seedream 5 Pro | 20 ROX |
| Seedance 2.0 | 40 ROX/s |
| Seedance 2.5 | 60 ROX/s |
| Kling 2.5 Turbo Pro · T2V | 30 ROX/s |
| Kling 2.5 Turbo Pro · I2V | 30 ROX/s |
| Kling AI Avatar · Standard | 20 ROX/s |
| Kling AI Avatar · Pro | 30 ROX/s |
| Kling 3.0 | 30 ROX/s |
| Veo 3.1 | 35 ROX/s |
| Grok | 15 ROX/s |
| Grok Imagine 1.5 | 30 ROX/s |
| Gemini Omni | from 30 ROX/s |
| Kling Motion 2.6 720p | 20 ROX/s |
| Kling Motion 2.6 1080p | 30 ROX/s |
| Kling Motion 3.0 720p | 60 ROX/s |
| Kling Motion 3.0 1080p | 80 ROX/s |

Public denomination: **1 ROX = 1 RUB**.

Image models use flat billing. Video models use per-second billing unless a concrete model contract specifies otherwise. Tier-aware models resolve the tier first and then calculate total cost.

Kling 2.5 Turbo Pro supports only 5- or 10-second clips in the current Kie callable contract. Kling AI Avatar uses the real input-audio duration for billing (1–300 seconds); `billing_seconds` is ROXY accounting metadata and is not sent to Kie as a fake provider duration parameter.

Admin pricing changes must pass model/price-mode/tier validation, require `pricing.manage` and the privileged confirmation/MFA policy, and must be verified with a fresh quote plus controlled debit after publish.

Do not create a fake model mapping for a commercial name that has no concrete provider/backend model ID. In particular, `Kling 03 • Omni` is not a standalone runtime model until a real provider endpoint is mapped and tested.
