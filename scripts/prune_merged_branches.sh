#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

repo="$GITHUB_REPOSITORY"
open_heads="$(mktemp)"
merged_heads="$(mktemp)"
trap 'rm -f "$open_heads" "$merged_heads"' EXIT

# Never prune a branch that still has an open PR in this repository.
gh api --paginate "repos/${repo}/pulls?state=open&per_page=100" \
  --jq '.[] | select(.head.repo.full_name == env.GITHUB_REPOSITORY) | .head.ref' \
  | sort -u > "$open_heads"

# A branch is eligible only when its *current* tip still equals the exact head SHA
# of a merged PR. If anyone added commits after that merge, it is preserved.
gh api --paginate "repos/${repo}/pulls?state=closed&per_page=100" \
  --jq '.[] | select(.merged_at != null and .head.repo.full_name == env.GITHUB_REPOSITORY) | [.head.ref, .head.sha] | @tsv' \
  > "$merged_heads"

deleted=0
preserved=0

while IFS=$'\t' read -r branch merged_sha; do
  [[ -n "${branch:-}" && -n "${merged_sha:-}" ]] || continue

  case "$branch" in
    main|master|develop|development|staging|production|prod|release|release/*)
      preserved=$((preserved + 1))
      continue
      ;;
  esac

  if grep -Fxq "$branch" "$open_heads"; then
    preserved=$((preserved + 1))
    continue
  fi

  current_sha="$(gh api "repos/${repo}/git/ref/heads/${branch}" --jq '.object.sha' 2>/dev/null || true)"
  [[ -n "$current_sha" ]] || continue

  if [[ "$current_sha" != "$merged_sha" ]]; then
    preserved=$((preserved + 1))
    continue
  fi

  if gh api -X DELETE "repos/${repo}/git/refs/heads/${branch}" >/dev/null 2>&1; then
    echo "deleted merged branch: ${branch} (${merged_sha})"
    deleted=$((deleted + 1))
  else
    echo "preserved branch after delete refusal: ${branch}" >&2
    preserved=$((preserved + 1))
  fi
done < "$merged_heads"

echo "branch cleanup complete: deleted=${deleted} preserved=${preserved}"
