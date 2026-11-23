# Visual disk map

A read-only whole-disk map with a treemap, recommendations and an **approval request** button. The page **never generates a deletion script**: it builds a text request the user pastes back into the conversation, and the agent executes item by item under the usual guards.

## Run

```bash
python3 "$SKILL_DIR/scripts/topeira-map.py"                  # whole Data volume
python3 "$SKILL_DIR/scripts/topeira-map.py" --roots ~        # home only, faster
python3 "$SKILL_DIR/scripts/topeira-map.py" --redact         # collapses names inside Documents/iCloud/Desktop/Photos/Mail
python3 "$SKILL_DIR/scripts/topeira-map.py" --render <mapa.json>   # re-render the page only
python3 "$SKILL_DIR/scripts/topeira-map.py" --no-open --out DIR
```

- Output: `~/.local/state/topeira/mapas/<YYYYMMDD-HHMMSS>/mapa.{json,html}`. Keeps the last 5 runs. Opens the page unless `--no-open`.
- Run it **outside the agent sandbox** (sandboxed shells skip dotfiles silently).
- Time: a full volume (~750 GB, millions of files) takes 10–25 min; one project folder takes seconds. `--max-seconds` (default 1500) marks the scan as partial when hit. Run it in the background.
- Read-only: `scandir` + `lstat`, plus `getattrlist` for exclusive size. Does not open file contents, does not download iCloud placeholders, does not follow symlinks or cross volumes.

## What the page shows

- **KPIs:** free now, free after the selection, Finder's "important usage" number (includes purgeable), total Tier A, total "review first" (B/C), and **not mapped** (volume used minus scanned: snapshots, purgeable, TCC-blocked, system).
- **Explorer:** squarified treemap; click to drill in, breadcrumb to go back. Colour by category or by tier. Green hatch = A, amber = B, red dashed border = whitelist/Tier D (never in a request).
- **Recommendations** grouped by tier, each with an **exclusive → apparent** range. Exclusive (`ATTR_CMNEXT_PRIVATESIZE`) is the guaranteed minimum gain; apparent is the ceiling. APFS clones push them far apart.
- **Copy approval request:** produces `topeira approve — map <id>` text with tier, size range, proposed action and paths per item.

## When the user pastes a request

The request sets the **maximum scope**; it waives no guard. Per item:

1. The map is a snapshot. Re-measure the path now (it may have grown or vanished).
2. Check running processes/apps (`pgrep`) and the whitelist resolved against the real home.
3. If the request says "… and N more folders", list them before executing. Do not infer the list.
4. Execute only that item's action. Measure `df` before/after and log the real delta.
5. Worktrees (Tier B): `git worktree remove` without `--force`, after checking unpushed commits, unique untracked/ignored files, locks and active use by other agents/sessions. Reflog-only commits get an archive ref first. See `continuous-drill.md`.
6. B/C items with mutually exclusive choices (keep in cloud vs delete) need a specific answer; a generic "go" does not pick one.

## Classification (summary; rules live in `topeira-map.py`)

| Tier | Examples | Rule |
|---|---|---|
| A safe | npm/Homebrew/pip/Yarn/Go caches, Puppeteer, Gradle, DerivedData, app caches outside the whitelist, logs, `.next`/`.turbo` | recreatable; still approved per category |
| B review | uv, Playwright, simulators, DeviceSupport, Android, `node_modules`/`.venv`/`Pods` in projects, **agent worktrees**, agent visualization/audit artifacts | recreation cost or possible unique work |
| C collection | Trash, Downloads, Movies, Xcode Archives | only the user knows |
| D protected | Documents, iCloud, Desktop, Photos, Music, Mail, Messages, `.ssh`, Keychains, Application Support, agent histories (Cursor/OpenCode/Claude/Codex), Ollama, games | never in a request |

**Application Support** stays D by default (app data), coloured by owner (AI, games, dev). Only three things become recommendations:

- Electron cache subfolders right under each app (`Cache`, `Code Cache`, `GPUCache`, `CachedData`, `Dawn*`, `ShaderCache`, `Crashpad`, `logs`) — Tier A, app closed;
- `Claude/vm_bundles` (Claude Desktop VM, ~13 GB, re-downloaded by the app) — Tier B, never with the app open;
- `com.docker.install/in_progress` (an interrupted Docker update) — Tier B.

Whitelisted Electron caches stay protected.

`~/Library/Containers` is not scanned (TCC red line). Docker.raw and mediaanalysisd live there; use `topeira docker` or the specific flow.

If the Python interpreter lacks macOS "Files and Folders" permission, `~/Documents`, `~/Desktop`, `~/Downloads` and iCloud show as "no permission" (0 GB) and fall into "not mapped". Grant access or measure with `du` from a terminal that has Full Disk Access. Never conclude they are empty.

## Privacy

- The map contains personal and client folder names. It stays **local**.
- Publish or share it only with the user's explicit OK, and generated with `--redact`.
- Never paste `mapa.json` excerpts into issues, forums or versioned logs. The log gets totals and category paths only.
