# Workflow fields: photo / height / weight presets on current main

Baseline: `c7b0f08fb936e6fa85f7ef82ece38626da020f43` (after #652). This patch ports the safe UI repair from stale PR #614 without reintroducing its obsolete **16-field limit**. Current main supports workflows with more than 16 inputs.

Admin scenario: old recipes may store `person_photo` as a numeric field. Previously auto-sync could manufacture a phantom photo input instead of guiding the operator to correct the existing field. The editor now has three ready presets. Photo sets `person_photo` to `image`, height/weight set scalar `number` fields. Saved recipes are not modified until an admin clicks a preset and saves. Existing custom labels are preserved on correctly typed fields.

Verification: Playwright tests carried forward for broken saved recipe, duplicate guard, save and reopen, new workflow; existing regression with 18 inputs must stay green. UI-only, no database migration, limits, prices, provider routes, payment logic, server API or hidden prompt modification. Release exact SHA via six required checks after merge. Rollback is a revert of this isolated PR.
