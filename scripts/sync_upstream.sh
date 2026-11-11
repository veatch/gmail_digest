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
# Parse the YAML mapping directly instead of calling load_config(): the
# instance may be running an older validator that rejects newer config fields
# before it has a chance to sync the updated application code.
AUTO_SYNC=0
UPSTREAM_URL=""
UPSTREAM_REF="main"
UPSTREAM_PATHS=""
if ! SETTINGS="$(
  PYTHONPATH=src python3 - <<'PY'
from pathlib import Path
from digest.config import DEFAULT_UPSTREAM_PATHS, loads_simple_yaml
import shlex

data = loads_simple_yaml(Path("config.yml").read_text(encoding="utf-8"))
u = data.get("upstream") or {}
if not isinstance(u, dict):
    raise SystemExit("config.yml: upstream must be a mapping")
paths = u.get("paths")
if paths is None:
    paths = DEFAULT_UPSTREAM_PATHS
if not isinstance(paths, list):
    raise SystemExit("config.yml: upstream.paths must be a list")
auto_sync = u.get("auto_sync", False)
print(f"AUTO_SYNC={int(auto_sync is True or str(auto_sync).lower() in {'true', 'yes', 'on', '1'})}")
print(f"UPSTREAM_URL={shlex.quote(str(u.get('url') or '').strip())}")
print(f"UPSTREAM_REF={shlex.quote(str(u.get('ref') or 'main').strip())}")
print(f"UPSTREAM_PATHS={shlex.quote(chr(10).join(str(p) for p in paths))}")
PY
)"; then
  warn "could not read upstream settings from config.yml — continuing without sync"
  exit 0
fi
eval "$SETTINGS"

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
