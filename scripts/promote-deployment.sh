#!/usr/bin/env bash
# Promote only tasks-app image tags; never rewrite a caller's working tree.
set -euo pipefail

[[ $# -eq 3 ]] || { echo "Usage: $0 DEPLOYMENTS_DIR SOURCE_DIR TESTED_SHA" >&2; exit 2; }
deployments="$(git -C "$1" rev-parse --show-toplevel)"
source_dir="$(git -C "$2" rev-parse --show-toplevel)"
tested_sha="$3"
[[ "$tested_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "Expected full tested commit SHA" >&2; exit 2; }
[[ "$(git -C "$source_dir" rev-parse HEAD)" == "$tested_sha" ]] || { echo "Source checkout differs from tested revision" >&2; exit 1; }
[[ -z "$(git -C "$deployments" status --porcelain --untracked-files=all)" ]] || { echo "Deployment checkout must be clean" >&2; exit 1; }
overlay="applications/tasks-app/overlays/homelab/kustomization.yaml"
tag="${tested_sha:0:12}"
candidate=""

cleanup() {
  # Only this script's newly allocated disposable candidate is removed.
  if [[ -n "$candidate" ]]; then
    git -C "$deployments" worktree remove --force "$candidate"
    candidate=""
  fi
}
trap cleanup EXIT

check_source_head() {
  local remote
  remote="$(git -C "$source_dir" ls-remote --exit-code origin refs/heads/main)"
  [[ "${remote%%[[:space:]]*}" == "$tested_sha" ]] || { echo "Tested source was superseded; refusing promotion" >&2; return 1; }
}

for attempt in 1 2 3; do
  check_source_head
  git -C "$deployments" fetch origin main
  base="$(git -C "$deployments" rev-parse FETCH_HEAD)"
  candidate="$(mktemp -d "${TMPDIR:-/tmp}/tasks-promotion.XXXXXX")"
  git -C "$deployments" worktree add --detach "$candidate" "$base"
  (
    cd "$candidate/applications/tasks-app/overlays/homelab"
    kustomize edit set image \
      "tasks-api=ghcr.io/avjpl/tasks-api:$tag" \
      "tasks-web=ghcr.io/avjpl/tasks-web:$tag"
  )
  changes="$(git -C "$candidate" status --porcelain --untracked-files=all)"
  if [[ -z "$changes" ]]; then
    check_source_head
    echo "Already promoted $tag"
    exit 0
  fi
  [[ "$changes" == " M $overlay" ]] || { echo "Unexpected changes outside the image overlay" >&2; exit 1; }
  git -C "$candidate" add -- "$overlay"
  git -C "$candidate" commit -m "chore(deploy): promote tasks-app $tag"
  check_source_head
  if git -C "$candidate" push origin HEAD:refs/heads/main; then
    echo "Promoted tasks-app $tag"
    exit 0
  fi
  remote="$(git -C "$deployments" ls-remote --exit-code origin refs/heads/main)"
  [[ "${remote%%[[:space:]]*}" != "$base" ]] || { echo "Push rejected without a concurrent main update" >&2; exit 1; }
  cleanup
  echo "Remote deployment changes detected; rebuilding promotion (attempt $attempt/3)" >&2
done
echo "Promotion failed after three concurrent-update attempts" >&2
exit 1
