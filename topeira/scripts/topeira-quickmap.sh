#!/bin/bash
# topeira-quickmap.sh — read-only disk map using only what ships with macOS
# (bash 3.2, du, df, osascript). No Python, Swift, Xcode tools or Homebrew.
# Use it when `xcode-select -p` fails: calling python3/swift there would pop the
# "install Command Line Tools" dialog, i.e. install software on the machine.
#
# Usage:
#   bash topeira-quickmap.sh                 # volume + home + ~/Library, top 15 each
#   bash topeira-quickmap.sh ~/Library/Caches 25   # one root, top 25
# Output: Markdown on stdout, and a copy in ~/.local/state/topeira/quickmap-<ts>.md
# Never deletes, moves or opens file contents. Does not enter ~/Library/Containers.
set -u
TOP="${2:-15}"
OUTDIR="$HOME/.local/state/topeira"
mkdir -p "$OUTDIR"
OUT="$OUTDIR/quickmap-$(date +%Y%m%d-%H%M%S).md"

human() { awk -v k="$1" 'BEGIN{ if (k>=1048576) printf "%.1f GB", k/1048576; else if (k>=1024) printf "%.0f MB", k/1024; else printf "%d KB", k }'; }

important_free() {
  osascript -l JavaScript -e 'ObjC.import("Foundation");
    var r=$.NSURL.fileURLWithPath("/").resourceValuesForKeysError($(["NSURLVolumeAvailableCapacityForImportantUsageKey"]), null);
    r.objectForKey("NSURLVolumeAvailableCapacityForImportantUsageKey").js' 2>/dev/null
}

table() {  # table <root> <title>
  root="$1"
  echo ""
  echo "## $2 — \`$root\`"
  echo ""
  echo "| # | size | folder |"
  echo "|---|---|---|"
  n=0
  # -x: stay on this volume. Containers skipped (TCC can hang or lie there).
  du -x -k -d 1 "$root" 2>/dev/null \
    | grep -v "/Library/Containers$" \
    | awk -v r="$root" '$2 != r' \
    | sort -rn | head -n "$TOP" \
    | while IFS=$'\t' read -r kb path; do
        n=$((n+1))
        echo "| $n | $(human "$kb") | \`${path/#$HOME/~}\` |"
      done
}

{
  echo "# Topeira quick map — $(date '+%Y-%m-%d %H:%M')"
  echo ""
  df -k /System/Volumes/Data | awk 'NR==2 {printf "- APFS: %.1f GB used of %.1f GB, %.1f GB free\n", $3/1048576, $2/1048576, $4/1048576}'
  imp="$(important_free)"
  if [ -n "$imp" ]; then
    awk -v b="$imp" 'BEGIN{printf "- Finder \"available for important usage\" (includes purgeable): %.1f GB\n", b/1073741824}'
  fi
  if ls "$HOME/Library/Messages" >/dev/null 2>&1; then
    echo "- Full Disk Access: yes"
  else
    echo "- Full Disk Access: **no** — Mail, Messages, Photos and similar folders will under-report"
  fi
  echo "- Local snapshots: $(tmutil listlocalsnapshots / 2>/dev/null | grep -c com.apple)"
  if [ $# -ge 1 ]; then
    table "$1" "Largest folders"
  else
    table /System/Volumes/Data "Volume"
    table "$HOME" "Home"
    table "$HOME/Library" "Library"
  fi
  echo ""
  echo "_Read-only. Sizes are allocated blocks; APFS clones mean deleting can free less. Not a deletion plan: every item still needs per-category confirmation._"
} | tee "$OUT"
echo ""
echo "saved: $OUT" >&2
