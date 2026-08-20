# Trending generation model catalog

**Status:** current product contract, synchronized 2026-08-20.

ROXY no longer exposes every historical provider version in the customer model picker. The active picker is intentionally narrow and follows the current `Bambale0/banano_kling:tanyapi` product set, while KSU keeps its own stricter provider validation, billing, outbox/recovery and current Kie callable contracts.

The Tanya branch is a **product-selection reference**, not a provider-payload authority. Provider field schemas and exact upstream IDs remain governed by the current Kie contract and KSU regression tests.

## Public Photo catalog

The Photo picker exposes only these current products:

| Customer product | KSU runtime IDs | Tanya reference |
| --- | --- | --- |
| Nano Banana 2 Lite | `nano-banana-2-lite` | `nano-banana-2-lite` |
| Seedream 5 Pro | `seedream-5-pro-t2i`, `seedream-5-pro-i2i` | `seedream_5_pro` |
| Nano Banana Pro | `nano-banana-pro` | `banana_pro` |
| Nano Banana 2 | `nano-banana-2` | `banana_2` |
| Seedream 4.5 Edit | `seedream-4.5-edit` | `seedream_edit` |
| GPT Image 2 | `gpt-image-2-t2i`, `gpt-image-2-i2i` | `flux_pro` customer label `GPT Image 2` |
| Wan 2.7 Pro | `wan-2.7-image-pro` | `wan_27` with Pro enabled by default |
| Grok Imagine image edit | `grok-image-i2i` | `grok_imagine_i2i` |

KSU keeps split T2I/I2I runtime IDs where the provider has separate callable routes. The Mini App groups those concrete routes into the appropriate customer family/version rather than inventing a second provider mapping.

Not offered for new customer work: base Nano Banana/Edit, Seedream 3.0, Seedream 4.0, Seedream 4.5 T2I, Seedream 5 Lite, Seedream 5 Pro layer decomposition, GPT Image 1.5, standard Wan 2.7 image and Grok image T2I.

## Public Video catalog

The Video picker exposes the current Tanya-style families through KSU's current contracts:

| Customer product | KSU runtime IDs / selector |
| --- | --- |
| Kling 3.0 | `kling-3.0`; server-driven `mode` covers the supported variant choice |
| Kling 2.5 Turbo Pro | `kling-2.5-turbo-pro-t2v`, `kling-2.5-turbo-pro-i2v` |
| Grok Imagine | `grok-video-i2v` |
| Grok Imagine 1.5 | `grok-video-1.5` |
| Seedance 2.0 | `seedance-2.0` |
| Seedance 2.5 | `seedance-2.5` |
| Gemini Omni Video | `gemini-omni-video` |
| Veo 3.1 | `veo-3.1`; `veo_model` selects current Quality/Fast/Lite variants |
| Kling Motion Control | `kling-motion-2.6`, `kling-motion-3.0` |
| Kling AI Avatar | `kling-avatar-standard`, `kling-avatar-pro` |

Seedance 2.5 is retained publicly in ROXY because KSU already has a provider-verified current callable contract. In Tanya it is present in the capability registry and exposed as an admin preview in the bot rather than the ordinary Mini App list.

Not offered for new customer work: Seedance 1.5 Pro, Seedance 2.0 Fast/Mini, Wan 2.7 video routes as top-level products, Grok text-to-video as a separate picker product, and historical duplicated variants that are already represented by a current KSU model plus its server-driven settings.

`grok-video-upscale` and `grok-video-extend` remain callable **result follow-up operations**, but they are not top-level model-picker cards.

## Legacy/history compatibility

Removing a model from the public picker does **not** rewrite old generations and does not silently switch them to a newer provider model.

- `ModelCatalog.get()` retains legacy specs for reading old rows and recovery compatibility.
- `ModelCatalog.list()` returns only the current trending picker set.
- `ModelCatalog.prepare()` rejects inactive historical IDs for new quote/create work before wallet debit or provider submission.
- Existing generation rows prefer their stored `_provider_model` / `_kie_model` snapshot during recovery.
- Historical Alembic migrations are never deleted as part of model cleanup.

This separation lets ROXY remove obsolete customer choices without breaking history or turning an old queued task into a different paid provider request.

## Release acceptance

Before release:

1. `GET /api/v1/generations/models` returns exactly the maintained trending product IDs plus the separate Suno music product added by the generation API.
2. Legacy IDs listed above are absent from the Photo/Video picker.
3. Quote/create of an inactive legacy ID fails before wallet debit and provider submission.
4. A historical row that references a removed model remains readable and keeps its stored provider identity.
5. Grok upscale/extend remain callable only as current follow-up operations and do not become model-picker cards.
6. Current Kling 2.5/Avatar, Seedance 2.5, Veo 3.1 and other retained provider-contract tests remain green.
7. Family grouping still exposes every retained concrete T2I/I2I/T2V/I2V route without duplicating obsolete versions.
8. Admin-free customer billing behavior remains unchanged for every retained model.
9. Production is not considered updated until the merged SHA is deployed and `/mini-app/release.json` plus physical Mini App smoke evidence match that SHA.
