# AGENTS.md

This repository ships one agent skill: **Topeira**, assisted macOS storage cleanup.

Any agent asked to clean, map or diagnose disk usage on a Mac should read
[`topeira/SKILL.md`](topeira/SKILL.md) and follow it exactly, including its red lines:
read-only baseline first, dry-run, and explicit confirmation per category before deleting anything.
