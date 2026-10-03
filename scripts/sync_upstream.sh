#!/usr/bin/env bash
# Path-scoped sync from the public template into a private copy.
# Never touches state/ or config.yml. Soft-fails so the digest can still run.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf 'sync-upstream: %s\n' "$*"; }
warn() { printf 'sync-upstream: WARNING: %s\n' "$*" >&2; }

if [[ ! -f config.yml ]]; then
  log "no config.yml — skip (copy config.example.yml → config.yml to enable)"
  exit 0
fi

# Read upstream settings without project deps (works before uv sync).
eval "$(
  PYTHONPATH=src python3 - <<'PY'
from digest.config import load_config
import shlex

cfg = load_config("config.yml")
u = cfg.upstream
print(f"AUTO_SYNC={int(bool(u.auto_sync))}")
print(f"UPSTREAM_URL={shlex.quote(u.url)}")
print(f"UPSTREAM_REF={shlex.quote(u.ref)}")
print(f"UPSTREAM_PATHS={shlex.quote(chr(10).join(u.paths))}")
PY
)"

if [[ "${AUTO_SYNC}" != "1" ]]; then
  log "upstream.auto_sync is false — skip"
  exit 0
fi

if [[ -z "${UPSTREAM_URL}" ]]; then
  warn "upstream.url is empty — skip"
  exit 0
fi

if [[ -z "${UPSTREAM_PATHS}" ]]; then
  warn "upstream.paths is empty — skip"
  exit 0
fi

# Skip if this repo is the upstream itself (public template).
ORIGIN_URL="$(git remote get-url origin 2>/dev/null || true)"
normalize() {
  local u="$1"
  u="${u%.git}"
  u="${u%/}"
  u="${u#https://}"
  u="${u#http://}"
  u="${u#git@}"
  u="${u/://}"
  printf '%s' "$u" | tr '[:upper:]' '[:lower:]'
}
if [[ "$(normalize "$ORIGIN_URL")" == "$(normalize "$UPSTREAM_URL")" ]]; then
  log "origin matches upstream.url — skip (this is the template repo)"
  exit 0
fi

mapfile -t PATHS <<<"${UPSTREAM_PATHS}"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

if git remote get-url upstream >/dev/null 2>&1; then
  git remote set-url upstream "${UPSTREAM_URL}"
else
  git remote add upstream "${UPSTREAM_URL}"
fi

log "fetching ${UPSTREAM_URL} (${UPSTREAM_REF})"
if ! git fetch --depth=1 upstream "${UPSTREAM_REF}"; then
  warn "git fetch failed — continuing without sync"
  exit 0
fi

FETCH_HEAD="$(git rev-parse FETCH_HEAD)"
log "upstream at ${FETCH_HEAD}"

# Checkout allowlisted paths from the fetched ref only.
if ! git checkout FETCH_HEAD -- "${PATHS[@]}"; then
  warn "git checkout of allowlisted paths failed — continuing without sync"
  exit 0
fi

if git diff --cached --quiet && git diff --quiet; then
  # checkout -- stages matched paths; unstage check:
  :
fi

# `git checkout <tree> -- paths` stages changes. Commit if the index differs.
if git diff --cached --quiet; then
  log "already up to date"
  exit 0
fi

git status --short
git commit -m "Sync allowlisted paths from upstream (${UPSTREAM_REF})"

if ! git push origin HEAD; then
  warn "git push failed — synced tree remains for this run only"
  exit 0
fi

log "pushed upstream sync commit"
exit 0
