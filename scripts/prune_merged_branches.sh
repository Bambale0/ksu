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

# A branch is eligible automatically only when its *current* tip still equals
# the exact head SHA of a merged PR. If anyone added commits after that merge,
# it is preserved unless a later reviewed PR explicitly marks it superseded.
gh api --paginate "repos/${repo}/pulls?state=closed&per_page=100" \
  --jq '.[] | select(.merged_at != null and .head.repo.full_name == env.GITHUB_REPOSITORY) | [.head.ref, .head.sha] | @tsv' \
  > "$merged_heads"

deleted=0
preserved=0

is_protected_name() {
  local branch="$1"
  case "$branch" in
    main|master|develop|development|staging|production|prod|release|release/*)
      return 0
      ;;
  esac
  return 1
}

has_open_pr() {
  local branch="$1"
  grep -Fxq "$branch" "$open_heads"
}

delete_branch() {
  local branch="$1"
  local reason="$2"
  if gh api -X DELETE "repos/${repo}/git/refs/heads/${branch}" >/dev/null 2>&1; then
    echo "deleted ${reason} branch: ${branch}"
    deleted=$((deleted + 1))
    return 0
  fi
  echo "preserved branch after delete refusal: ${branch}" >&2
  preserved=$((preserved + 1))
  return 1
}

while IFS=$'\t' read -r branch merged_sha; do
  [[ -n "${branch:-}" && -n "${merged_sha:-}" ]] || continue

  if is_protected_name "$branch" || has_open_pr "$branch"; then
    preserved=$((preserved + 1))
    continue
  fi

  current_sha="$(gh api "repos/${repo}/git/ref/heads/${branch}" --jq '.object.sha' 2>/dev/null || true)"
  [[ -n "$current_sha" ]] || continue

  if [[ "$current_sha" != "$merged_sha" ]]; then
    preserved=$((preserved + 1))
    continue
  fi

  delete_branch "$branch" "merged" || true
done < "$merged_heads"

# Some historical branches are replaced by a clean-port PR rather than merged
# directly (for example an old staging implementation rebased/reworked against
# current main). Those branches may be removed only when a reviewed commit on
# main explicitly lists them here. Open PRs and protected names still win.
superseded_file="scripts/superseded_branches.txt"
if [[ -f "$superseded_file" ]]; then
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    branch="${raw%%#*}"
    branch="$(printf '%s' "$branch" | xargs)"
    [[ -n "$branch" ]] || continue

    if is_protected_name "$branch" || has_open_pr "$branch"; then
      preserved=$((preserved + 1))
      continue
    fi

    current_sha="$(gh api "repos/${repo}/git/ref/heads/${branch}" --jq '.object.sha' 2>/dev/null || true)"
    [[ -n "$current_sha" ]] || continue
    delete_branch "$branch" "superseded" || true
  done < "$superseded_file"
fi

echo "branch cleanup complete: deleted=${deleted} preserved=${preserved}"
