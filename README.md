# Topeira — macOS storage cleanup skill for any AI agent

**Topeira** ("mole" in Portuguese) is an [Agent Skill](https://agentskills.io) that turns your coding agent into a careful macOS storage specialist. It measures first, maps the disk visually, proposes a plan by risk tier and deletes **only what you confirm, category by category**.

Works with Claude Code, Codex CLI, Cursor, Gemini CLI, OpenCode, or any agent that can read a `SKILL.md` and run a shell. Optional: [Mole](https://github.com/tw93/mole) (`brew install mole`).

## Why

"Your disk is almost full" + an agent with `rm -rf` is a bad mix. Topeira encodes the traps that bite in practice:

- TCC makes `du` and `rm` **lie** inside `~/Library/Containers` (exit 0, nothing deleted).
- Agent sandboxes silently skip dotfiles when measuring.
- APFS clones: a cache showing 16.8 GB may free only 2.5 GB.
- `mediaanalysisd` and open apps regenerate caches while you delete them.
- iCloud: `rm` deletes everywhere; Remove Download only evicts locally.

## What's inside

```
topeira/
├── SKILL.md                         # role, red lines, tiers, workflow, traps
├── references/
│   ├── visual-map.md                # whole-disk treemap + approval-request flow
│   ├── documents-icloud-curation.md # Documents/iCloud, Remove Download
│   └── continuous-drill.md          # multi-round drills, worktrees, agent histories
└── scripts/
    ├── topeira-map.py               # read-only disk map → HTML treemap (exclusive vs apparent bytes)
    ├── topeira-map.template.html
    ├── topeira-inventory.sh         # read-only baseline
    ├── topeira-icloud-status.swift  # read-only per-file iCloud status
    └── topeira-cleanup.sh           # interactive example run (use --dry-run first)
```

## Install

**Any runtime (script):**

```bash
git clone https://github.com/mrfaillol/topeira.git
cd topeira && ./install.sh
```

Copies the skill to `~/.agents/skills/topeira` and symlinks it into `~/.claude/skills`, `~/.codex/skills`, `~/.cursor/skills`, `~/.gemini/skills` and `~/.config/opencode/skills` — only for runtimes whose config folder already exists. Existing installs are backed up, not overwritten.

**skills CLI:** `npx skills add mrfaillol/topeira`

**Manual:** copy `topeira/` into your runtime's skills directory, or tell your agent: *"Read topeira/SKILL.md and follow it."* An `AGENTS.md` at the repo root points agents there.

## Use

Ask your agent:

| Say | Does |
|---|---|
| `topeira` | baseline + Mole dry-run + plan |
| `topeira inventory` | read-only, zero actions |
| `topeira map` | visual treemap of the whole disk (10–25 min, background) |
| `topeira urgent 20GB` | emergency, Tier A first |
| `topeira docker` / `topeira xcode` | scoped flows |
| `topeira ~/Library/Caches` | scoped to a path |
| `topeira ghosts` | orphan launchd agents, runaway `ssh-add`, dead cron |

The map page never produces a deletion script. It produces an **approval request** you paste back, and the agent re-measures and re-checks every item before acting.

> Disk measurement must run outside the agent's sandbox, and the terminal/agent host should have **Full Disk Access** (System Settings → Privacy & Security), otherwise protected folders under-report.

## Safety model

| Tier | Examples | Rule |
|---|---|---|
| A | npm/pip/Homebrew caches, DerivedData, logs | per-category confirmation |
| B | Docker, simulators, `node_modules`, git worktrees | individual confirmation |
| C | Downloads, Trash, Movies | listed, user decides |
| D | Documents, iCloud, Photos, Mail, Keychain, `.ssh`, app data | never proposed |

Everything is logged append-only to `~/.local/state/topeira/topeira_log.md` (override with `TOPEIRA_LOG`) with the **real** `df` delta.

## Português

Skill de limpeza de disco do macOS para qualquer agente de IA. Mede antes, mostra um mapa visual, propõe um plano por nível de risco e só apaga o que você confirmar, categoria por categoria. Instale com `./install.sh` e peça ao agente: `topeira inventory` ou `topeira mapa`.

## License

MIT. Not affiliated with Mole or Apple. Use at your own risk; read what the agent proposes before confirming.
