#!/usr/bin/env bash
set -u

RUN_MOLE=0
RUN_VOLUME=0
RUN_DEBUG=0
for arg in "$@"; do
  case "$arg" in
    --mole) RUN_MOLE=1 ;;
    --volume) RUN_VOLUME=1 ;;
    --debug) RUN_DEBUG=1 ;;
    --help|-h)
      cat <<'EOF'
topeira-inventory.sh: read-only baseline for the Topeira workflow.

Usage:
  bash topeira-inventory.sh
  bash topeira-inventory.sh --mole    # also run mo clean --dry-run
  bash topeira-inventory.sh --mole --debug
  bash topeira-inventory.sh --volume  # also run volume-level du
EOF
      exit 0
      ;;
  esac
done

timeout_cmd() {
  local seconds="$1"
  shift
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$seconds" "$@"
  elif command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" "$@"
  else
    "$@"
  fi
}

section() {
  printf '\n== %s ==\n' "$1"
}

probe_path() {
  local label="$1"
  local path="$2"
  if timeout_cmd 5 ls "$path" >/dev/null 2>&1; then
    printf 'OK   %s: %s\n' "$label" "$path"
  else
    printf 'MISS %s: %s\n' "$label" "$path"
  fi
}

section "Topeira Inventory"
date '+%Y-%m-%d %H:%M:%S %Z'
sw_vers 2>/dev/null || true
uname -m

section "Disk Baseline"
df -H /
diskutil info / 2>/dev/null | sed -n '/Volume Free Space/p;/Container Free Space/p;/APFS Snapshot/p;/FileVault/p'
tmutil listlocalsnapshots / 2>/dev/null || true

section "Processes"
for name in mediaanalysisd "Claude" "Codex" "Comet" "Brave Browser" "Spotify" "Steam" "Zed" "Visual Studio Code"; do
  matches="$(pgrep -lf "$name" 2>/dev/null | sed -n '1,3p' || true)"
  if [[ -n "$matches" ]]; then
    printf '%-18s %s\n' "$name" "$matches"
  else
    printf '%-18s none\n' "$name"
  fi
done

section "TCC/FDA Probes"
probe_path "Messages" "$HOME/Library/Messages"
probe_path "Mail" "$HOME/Library/Mail"
probe_path "mediaanalysisd" "$HOME/Library/Containers/com.apple.mediaanalysisd/Data/Library/Caches"
probe_path "Photos library dir" "$HOME/Pictures/Photos Library.photoslibrary"

section "Mole"
if command -v mo >/dev/null 2>&1; then
  command -v mo
  mo --version
  mo clean --help | sed -n '1,80p'
else
  echo "mo not found"
fi

section "Whitelist"
if [[ -f "$HOME/.config/mole/whitelist" ]]; then
  sed -n '1,220p' "$HOME/.config/mole/whitelist"
else
  echo "missing ~/.config/mole/whitelist"
fi

section "Top Local Paths"
for path in \
  "$HOME/.cache" \
  "$HOME/.codex" \
  "$HOME/.local/state" \
  "$HOME/.npm" \
  "$HOME/Downloads" \
  "$HOME/Library/Caches" \
  "$HOME/Library/Application Support" \
  "$HOME/Library/Group Containers" \
  "$HOME/Library/Logs" \
  "$HOME/Projects" \
  "$HOME/Projects_Local"; do
  if [[ -e "$path" ]]; then
    timeout_cmd 20 du -sh "$path" 2>/dev/null || printf '(TCC/timeout) %s\n' "$path"
  fi
done

if [[ "$RUN_VOLUME" -eq 1 ]]; then
  section "Volume Data Top Level"
  timeout_cmd 120 du -x -d1 -h /System/Volumes/Data 2>/dev/null | sort -rh || true
fi

if [[ "$RUN_MOLE" -eq 1 ]]; then
  section "Mole Clean Dry Run"
  if command -v mo >/dev/null 2>&1; then
    preview="/tmp/topeira-mole-preview.txt"
    if [[ "$RUN_DEBUG" -eq 1 ]]; then
      mo clean --dry-run --debug > "$preview"
    else
      mo clean --dry-run > "$preview"
    fi
    printf 'saved %s\n' "$preview"
    sed -E $'s/\x1b\\[[0-9;]*[A-Za-z]//g' "$preview" \
      | sed -E 's#Path: /Users/[^/]+/.*#Path: [redacted]#' \
      | grep -E 'Dry Run Mode|Free space:|Whitelist:|System Data clues|Project artifacts|Dry run complete|Potential space:|Detailed file list:|Use mo clean --whitelist' \
      | sed -n '1,80p'
  else
    echo "mo not found"
  fi
fi
