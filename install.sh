#!/bin/bash
# Topeira installer. Needs only what ships with macOS (bash 3.2, curl, ditto).
# No git, Homebrew, Python or Xcode tools required.
#
#   From a clone:   ./install.sh
#   Without git:    curl -fsSL https://raw.githubusercontent.com/mrfaillol/topeira/main/install.sh | bash
#   Remove:         ./install.sh --uninstall   (or: curl ... | bash -s -- --uninstall)
#
# Copies the skill to ~/.agents/skills/topeira and to the skills folder of each agent
# runtime already present (real copies, not symlinks: some agents skip symlinked skills).
# Re-run to update. Existing non-Topeira folders are backed up, never deleted.
set -eu
REPO_ZIP="https://github.com/mrfaillol/topeira/archive/refs/heads/main.zip"
CANON="$HOME/.agents/skills/topeira"
STATE="$HOME/.local/state/topeira"
TS="$(date +%Y%m%d-%H%M%S)"

# runtime config folder : skills folder
TARGETS="
$HOME/.gemini:$HOME/.gemini/config/skills
$HOME/.claude:$HOME/.claude/skills
$HOME/.codex:$HOME/.codex/skills
$HOME/.cursor:$HOME/.cursor/skills
$HOME/.config/opencode:$HOME/.config/opencode/skills
"

if [ "${1:-}" = "--uninstall" ]; then
  echo "$TARGETS" | while IFS=: read -r home dir; do
    [ -n "$home" ] || continue
    d="$dir/topeira"
    if [ -f "$d/.topeira-installed" ]; then rm -rf "$d"; echo "removed: $d"; fi
  done
  if [ -f "$CANON/.topeira-installed" ]; then rm -rf "$CANON"; echo "removed: $CANON"; fi
  if [ -d "$STATE" ]; then
    echo "kept logs/maps: $STATE  (delete with: rm -rf \"$STATE\")"
  fi
  exit 0
fi

backup() { if [ -e "$1" ] || [ -L "$1" ]; then mv "$1" "$1.bak-$TS"; echo "  backup: $1.bak-$TS"; fi; }

# Source: the clone next to this script, or a fresh download.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$HERE" ] && [ -f "$HERE/topeira/SKILL.md" ]; then
  SRC="$HERE/topeira"
else
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  echo "downloading $REPO_ZIP"
  curl -fsSL "$REPO_ZIP" -o "$TMP/topeira.zip"
  ditto -x -k "$TMP/topeira.zip" "$TMP/x"
  SRC="$(echo "$TMP"/x/*/topeira)"
  [ -f "$SRC/SKILL.md" ] || { echo "download did not contain topeira/SKILL.md" >&2; exit 1; }
fi

place() {  # place <dest>
  dest="$1"
  if [ -e "$dest" ] && [ ! -f "$dest/.topeira-installed" ]; then backup "$dest"; fi
  rm -rf "$dest"; mkdir -p "$(dirname "$dest")"
  cp -R "$SRC" "$dest"
  date '+%Y-%m-%d %H:%M' > "$dest/.topeira-installed"
  chmod +x "$dest"/scripts/*.sh "$dest"/scripts/*.py 2>/dev/null || true
  echo "installed: $dest"
}

if [ "$(cd "$CANON" 2>/dev/null && pwd -P)" != "$(cd "$SRC" && pwd -P)" ]; then place "$CANON"; fi
echo "$TARGETS" | while IFS=: read -r home dir; do
  [ -n "$home" ] && [ -d "$home" ] || continue
  place "$dir/topeira"
done

if [ ! -d "$HOME/.gemini" ] && [ ! -d "$HOME/.claude" ] && [ ! -d "$HOME/.codex" ] && [ ! -d "$HOME/.cursor" ] && [ ! -d "$HOME/.config/opencode" ]; then
  echo "no agent runtime found yet. Open Antigravity once, then run this installer again."
fi
echo 'done. Ask your agent: "topeira inventory"'
