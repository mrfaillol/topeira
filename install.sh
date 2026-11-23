#!/usr/bin/env bash
# Installs the Topeira skill for every agent runtime found on this Mac.
# Canonical copy: ~/.agents/skills/topeira. Other runtimes get a symlink to it,
# only when their config directory already exists. Existing installs are backed up, never deleted.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)/topeira"
CANON="$HOME/.agents/skills/topeira"
TS="$(date +%Y%m%d-%H%M%S)"

backup() { [ -e "$1" ] || [ -L "$1" ] || return 0; mv "$1" "$1.bak-$TS"; echo "  backup: $1.bak-$TS"; }

mkdir -p "$(dirname "$CANON")"
if [ "$(cd "$CANON" 2>/dev/null && pwd -P)" != "$(cd "$SRC" && pwd -P)" ]; then
  backup "$CANON"; cp -R "$SRC" "$CANON"
fi
chmod +x "$CANON"/scripts/*.sh "$CANON"/scripts/*.py 2>/dev/null || true
echo "installed: $CANON"

# runtime-home : skills dir
for pair in \
  "$HOME/.claude:$HOME/.claude/skills" \
  "$HOME/.codex:$HOME/.codex/skills" \
  "$HOME/.cursor:$HOME/.cursor/skills" \
  "$HOME/.gemini:$HOME/.gemini/skills" \
  "$HOME/.config/opencode:$HOME/.config/opencode/skills"; do
  home="${pair%%:*}"; dir="${pair#*:}"
  [ -d "$home" ] || continue
  mkdir -p "$dir"
  link="$dir/topeira"
  if [ -L "$link" ] && [ "$(readlink "$link")" = "$CANON" ]; then echo "ok:     $link"; continue; fi
  backup "$link"; ln -s "$CANON" "$link"; echo "linked: $link -> $CANON"
done
echo "done. Ask your agent: \"topeira inventory\""
