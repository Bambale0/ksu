# Seedance 2.0 1080p: definitive upstream rejection copy

**Baseline:** main `c7b0f08fb936e6fa85f7ef82ece38626da020f43` after PR #652. Replaces outdated draft PR #637; no unrelated changes.

**Observed incident:** Neironych primary rejected 1080p with HTTP 409 / `capability_mismatch`, followed by Nexus fallback HTTP 402. Existing permanent error path refunds the generation, but exposed a technical provider response. Neironych may support 1080p in other conditions; this does **not** disable or downgrade resolution.

**Change:** Only when the exact chain includes `_model_id=seedance-2.0`, `resolution=1080p`, an explicit prior Neironych capability mismatch, and a definite Nexus 402, replace the customer-visible terminal error with a localized message suggesting a separate 720p attempt. Keep the existing fail-and-refund operation and structured warning. Every other case uses the original error.

**Regression:** Positive and negative tests for 1080p/720p, Seedance 2.5, missing primary failure. No paid provider tests, settings, prices, provider routing or schema migrations. Release through current-main six GitHub checks and SHA-based deployment. Rollback via revert.
