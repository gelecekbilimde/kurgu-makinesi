#!/usr/bin/env bash
# Asset store helper for the Kurgu repository.
#
# The ~3.1 GB brand/streaming pack is deliberately NOT tracked in git (one file
# is 1.6 GB, over GitHub's 100 MB limit). It lives in a shared Dropbox folder
# and is materialised into assets/ by this script. The manifest, kept at
# assets/assets.sha256, pins every file so a fetch is verifiable and reproducible.
#
# Usage:
#   ./scripts/fetch-assets.sh fetch              # download, extract, verify
#   ./scripts/fetch-assets.sh fetch --zip X.zip  # use an already-downloaded archive
#   ./scripts/fetch-assets.sh verify             # check assets/ against the manifest
#   ./scripts/fetch-assets.sh manifest           # regenerate assets/assets.sha256
#
# The archive URL is never stored in this script; it is requested interactively,
# or passed with --url for non-interactive runs.
#
# Requires bash 4+, curl, and one of unzip / bsdtar / 7z.
# On Windows run this from Git Bash. Git Bash ships curl and sha256sum but not
# unzip; Windows' built-in `tar` (C:\Windows\System32\tar.exe) is bsdtar and
# handles zip files.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_DIR="$REPO_ROOT/.cache"

DEST="${ASSETS_DEST:-$REPO_ROOT/assets}"

# The manifest lives inside the pack it describes, so the pack verifies itself.
# It is the only file under assets/ that git tracks.
MANIFEST_NAME="assets.sha256"
MANIFEST="$DEST/$MANIFEST_NAME"
MANIFEST_REL="${MANIFEST#"$REPO_ROOT"/}"
WORKDIR=""

# Only used for the progress line; 0 means "unknown".
ARCHIVE_BYTES="${ASSETS_ARCHIVE_BYTES:-0}"

# ---------------------------------------------------------------- logging
use_color=0
if [[ -n "${CLICOLOR_FORCE:-}" ]]; then
  use_color=1
elif [[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  use_color=1
fi

if (( use_color )); then
  C_RESET=$'\033[0m'; C_RED=$'\033[1;31m'; C_YELLOW=$'\033[1;33m'
  C_GREEN=$'\033[1;32m'
else
  C_RESET=""; C_RED=""; C_YELLOW=""; C_GREEN=""
fi

die()  { printf '%serror:%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; exit 1; }
info() { printf '%s\n' "$*" >&2; }
warn() { printf '%swarning:%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
ok()   { printf '%s%s%s\n' "$C_GREEN" "$*" "$C_RESET" >&2; }

# ---------------------------------------------------------------- utilities
human() {
  local bytes=$1
  if   (( bytes >= 1073741824 )); then awk -v b="$bytes" 'BEGIN{printf "%.1f GB", b/1073741824}'
  elif (( bytes >= 1048576 ));    then awk -v b="$bytes" 'BEGIN{printf "%.1f MB", b/1048576}'
  elif (( bytes >= 1024 ));       then awk -v b="$bytes" 'BEGIN{printf "%.1f KB", b/1024}'
  else printf '%s B' "$bytes"; fi
}

setup_sha() {
  if   command -v sha256sum >/dev/null 2>&1; then SHA=(sha256sum)
  elif command -v shasum    >/dev/null 2>&1; then SHA=(shasum -a 256)
  else die "need sha256sum or shasum"; fi
}

setup_extractor() {
  if   command -v unzip   >/dev/null 2>&1; then EXTRACTOR=unzip
  elif command -v bsdtar  >/dev/null 2>&1; then EXTRACTOR=bsdtar
  elif command -v 7z      >/dev/null 2>&1; then EXTRACTOR=7z
  elif tar --version 2>/dev/null | grep -qi bsdtar; then EXTRACTOR=bsdtar
  else
    die "need unzip, bsdtar or 7z to extract the archive
       on Windows, put C:\\Windows\\System32 first in PATH (that tar.exe is bsdtar),
       or install unzip in Git Bash"
  fi
}

# Files under a directory: relative, NUL-separated, sorted, junk filtered.
# The manifest is excluded: it lives inside the pack but does not describe itself.
# assets/stock/ is the stock footage cache of the finding-stock-footage skill, not part of the
# brand pack, so neither verify nor manifest looks at it.
list_files() {
  ( cd "$1" && find . -type f \
      ! -name '.DS_Store' ! -name 'Thumbs.db' ! -path '*/__MACOSX/*' \
      ! -path "./$MANIFEST_NAME" ! -path './stock/*' \
      -print0 | LC_ALL=C sort -z )
}

file_size() {
  stat -c %s -- "$1" 2>/dev/null || stat -f %z -- "$1" 2>/dev/null || wc -c < "$1"
}

extract_zip() {
  local archive=$1 dir=$2
  mkdir -p "$dir"
  case "$EXTRACTOR" in
    unzip)  unzip -q "$archive" -d "$dir" ;;
    bsdtar) bsdtar -xf "$archive" -C "$dir" ;;
    7z)     7z x -y -o"$dir" "$archive" >/dev/null ;;
  esac
}

# If the whole archive sits inside one top-level folder, hoist its contents.
strip_prefix() {
  local dir=$1 tops
  tops=$(find "$dir" -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null \
         || find "$dir" -mindepth 1 -maxdepth 1 -exec basename {} \;)
  [[ -n "$tops" ]] || return 0
  if [[ $(printf '%s\n' "$tops" | wc -l) -eq 1 && -d "$dir/$tops" ]]; then
    local tmp="${dir}.hoist"
    mv "$dir/$tops" "$tmp" && rm -rf "$dir" && mv "$tmp" "$dir"
    info "stripped top-level folder '$tops'"
  fi
}

resolve_url() {
  local url="${1:-}"
  if [[ -z "$url" ]]; then
    if [[ -t 0 ]]; then
      read -r -p "Asset archive URL: " url
    else
      die "no archive URL given; pass --url URL"
    fi
  fi
  [[ -n "$url" ]] || die "no archive URL given"
  printf '%s' "$url"
}

# ---------------------------------------------------------------- commands
cmd_manifest() {
  [[ -d "$DEST" ]] || die "$DEST does not exist"
  local tmp count=0 total=0 rel hash
  tmp=$(mktemp)
  : > "$tmp"

  while IFS= read -r -d '' f; do
    rel=${f#./}
    hash=$("${SHA[@]}" "$DEST/$f" | cut -d' ' -f1)
    printf '%s  %s\n' "$hash" "$rel" >> "$tmp"
    total=$((total + $(file_size "$DEST/$f")))
    count=$((count + 1))
    printf '\r  hashed %d files (%s)' "$count" "$(human "$total")" >&2
  done < <(list_files "$DEST")
  printf '\n' >&2

  LC_ALL=C sort -k2 "$tmp" -o "$tmp"
  mv "$tmp" "$MANIFEST"
  info "wrote $MANIFEST_REL ($count files, $(human "$total"))"
}

cmd_verify() {
  [[ -f "$MANIFEST" ]] || die "$MANIFEST_REL not found"
  [[ -d "$DEST" ]] || die "$DEST does not exist (run: ./scripts/fetch-assets.sh fetch)"

  local expected actual problems=0 line
  expected=$(mktemp); actual=$(mktemp)

  awk '{sub(/^[0-9a-f]+  /,""); print}' "$MANIFEST" | LC_ALL=C sort > "$expected"
  ( cd "$DEST" && list_files . | tr '\0' '\n' | sed 's|^\./||' ) | LC_ALL=C sort > "$actual"

  while IFS= read -r line; do
    warn "missing file: $line"; problems=$((problems + 1))
  done < <(LC_ALL=C comm -23 "$expected" "$actual")
  while IFS= read -r line; do
    warn "unexpected file: $line"; problems=$((problems + 1))
  done < <(LC_ALL=C comm -13 "$expected" "$actual")

  local failures
  failures=$( cd "$DEST" && "${SHA[@]}" -c --quiet "$MANIFEST" 2>&1 ) || true
  if [[ -n "$failures" ]]; then
    while IFS= read -r line; do
      [[ "$line" == *": FAILED"* ]] || continue
      local rel="${line%%: FAILED*}"
      grep -qxF -- "$rel" "$actual" || continue   # missing files are reported above
      warn "checksum mismatch: $rel"
      problems=$((problems + 1))
    done <<< "$failures"
  fi
  rm -f "$expected" "$actual"

  if (( problems > 0 )); then
    warn "local pack differs from $MANIFEST_REL ($problems problem(s))"
    return 1
  fi
  ok "OK — $(wc -l < "$MANIFEST") files match $MANIFEST_REL ($(human "$(( $(du -sk "$DEST" | cut -f1) * 1024 ))"))"
}

download() {
  local url=$1 target=$2 rc=0
  mkdir -p "$(dirname "$target")"

  if [[ -s "$target" ]]; then
    info "resuming at $(human "$(file_size "$target")")"
    if curl -fL --retry 3 --retry-delay 2 -C - --progress-bar -o "$target" "$url"; then
      return 0
    else
      rc=$?
    fi
    if (( rc == 33 )); then
      info "server does not support ranged requests; restarting"
      rm -f "$target"
    else
      die "download failed (curl $rc; partial kept at $target; rerun to resume)"
    fi
  fi

  if (( ARCHIVE_BYTES > 0 )); then
    info "downloading to $target (~$(human "$ARCHIVE_BYTES"))"
  else
    info "downloading to $target"
  fi
  # Dropbox redirects to a signed CDN URL that supports range requests.
  curl -fL --retry 3 --retry-delay 2 --progress-bar -o "$target" "$url" \
    || die "download failed (partial kept at $target; rerun to resume)"
}

cmd_fetch() {
  local zip="" url="" force=0 verify=1 redownload=0
  while (( $# )); do
    case "$1" in
      --zip)        zip="${2:?--zip needs a path}"; shift 2 ;;
      --url)        url="${2:?--url needs a value}"; shift 2 ;;
      --force)      force=1; shift ;;
      --no-verify)  verify=0; shift ;;
      --redownload) redownload=1; shift ;;
      *) die "unknown option: $1" ;;
    esac
  done

  local existing
  existing=$(find "$DEST" -mindepth 1 -maxdepth 1 ! -name "$MANIFEST_NAME" -print -quit 2>/dev/null || true)
  if [[ -n "$existing" ]] && (( ! force )); then
    die "$DEST is not empty; pass --force to merge/overwrite"
  fi

  local archive workdir
  if [[ -n "$zip" ]]; then
    archive="$(cd "$(dirname "$zip")" && pwd)/$(basename "$zip")"
    [[ -f "$archive" ]] || die "$archive not found"
  else
    url=$(resolve_url "$url")
    archive="$CACHE_DIR/assets.zip"
    local part="$archive.part"
    (( redownload )) && rm -f "$archive" "$part"
    if [[ -f "$archive" ]]; then
      info "using cached archive ($(human "$(file_size "$archive")"))"
    else
      download "$url" "$part"
      mv "$part" "$archive"
    fi
  fi

  workdir="$(mktemp -d "${TMPDIR:-/tmp}/kurgu-assets.XXXXXX")"
  WORKDIR="$workdir"
  trap 'rm -rf "${WORKDIR:-}"' EXIT

  info "extracting with $EXTRACTOR"
  extract_zip "$archive" "$workdir"
  strip_prefix "$workdir"

  # A manifest inside the archive is stale by definition; the tracked copy wins.
  if [[ -e "$workdir/$MANIFEST_NAME" ]]; then
    warn "archive contains $MANIFEST_NAME; keeping the tracked copy"
    rm -f "$workdir/$MANIFEST_NAME"
  fi

  mkdir -p "$DEST"
  info "installing into $DEST"
  # Copy then delete, so a failure leaves the extracted tree intact.
  cp -a "$workdir"/. "$DEST"/

  # A hash mismatch is reported, not fatal: the assets are still in place.
  if (( verify )); then cmd_verify || true; fi
}

usage() {
  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

main() {
  local cmd=${1:-}
  [[ -n "$cmd" ]] || usage 1
  shift || true
  case "$cmd" in
    fetch)    setup_sha; setup_extractor; cmd_fetch "$@" ;;
    verify)   setup_sha; cmd_verify ;;
    manifest) setup_sha; cmd_manifest ;;
    -h|--help|help) usage 0 ;;
    *) die "unknown command: $cmd (try --help)" ;;
  esac
}

main "$@"
