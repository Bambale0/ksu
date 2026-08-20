# Repository hygiene

**Status:** maintained repository-operations policy as of 2026-08-20.

The production source of truth is `main`. Short-lived feature/fix/docs/chore branches exist only while they contain unmerged work or an open pull request.

## Merged branch cleanup

`.github/workflows/prune-merged-branches.yml` runs from trusted `main` after pushes to `main` and may also be invoked manually. It executes `scripts/prune_merged_branches.sh` with the repository-scoped GitHub token.

A branch is deleted only when **all** of these conditions hold:

1. GitHub records a merged pull request whose head repository is this repository.
2. The branch is not a protected environment/release name (`main`, `master`, `develop`, `development`, `staging`, `production`, `prod`, `release`, `release/*`).
3. No currently open pull request uses the branch.
4. The branch still exists.
5. The branch's current tip SHA is exactly the merged pull request's recorded head SHA.

The exact-tip condition is the safety boundary. If a branch was reused or received any commit after its PR merged, cleanup preserves it for manual inspection instead of deleting potentially unique work.

## Legacy code cleanup

Merged replacements should remove obsolete runtime paths rather than keep two competing implementations indefinitely. Before deleting legacy code:

- prove the replacement is merged and green;
- search runtime imports/routes/workers/configuration and tests for remaining references;
- preserve migration history when required for existing databases;
- remove stale environment variables, docs, runbook instructions and tests that describe the retired path;
- keep historical notes only when they are clearly marked historical and are not linked as current operational truth.

Do not delete an old migration merely because its feature is obsolete: an applied Alembic migration is database history. Retire behavior through a new forward migration when schema cleanup is needed.

## Pull request lifecycle

Normal repository lifecycle is:

```text
branch → implementation + tests + documentation → PR → required green CI → merge → automatic branch prune
```

Runtime-affecting PRs must include their documentation/configuration changes before merge. The cleanup workflow is not a substitute for reviewing whether code or docs became obsolete.

## Incident / audit procedure

If a branch expected to be deleted remains:

1. check whether it has an open PR;
2. compare its current tip SHA with the merged PR head SHA;
3. inspect whether additional commits contain unique work;
4. never force-delete a divergent branch until those commits have been intentionally merged, superseded or declared disposable.

If the cleanup workflow fails, repository operation continues normally; branch pruning is hygiene and must never block production runtime or mutate `main` contents.
