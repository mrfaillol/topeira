# Documents and iCloud curation

## Purpose and scope

Help the user decide what to keep locally, keep cloud-only (on demand), consolidate into an archive, or delete permanently — based on content and recovery evidence. Ask priorities early while continuing independent read-only analysis. When the user prioritizes technical clutter, preserve personal/professional originals by default.

Explicit permission to analyze allows scoped metadata and resident-content reads. It does **not** authorize eviction, moving, deleting or changing retention settings.

## Common preferences to ask about (record the answers, with date and scope)

- Keep the personal/professional/historical collection, but in the cloud rather than locally? ("keeping content" ≠ "allocating it locally")
- Focus reclamation on large worktrees, duplicate repositories and AI-session residue?
- For archive-and-remove batches: verify real recovery and file-level iCloud upload before removing local sources. Pending upload ≠ archived.
- Archive format: a normal ZIP per task with a readable index and original folder structure is easiest to browse and restore; avoid opaque formats that need a custom restorer.
- Failed attempts / intermediate artifacts: decide per concrete batch, from content, not by blanket rule.

One consequential question per round, with a concrete recommendation. Preferences never grant blanket deletion approval or weaken the gates.

## Inventory without downloading

Measure volume free space and scoped logical vs allocated bytes. Identify dataless placeholders from metadata before opening anything. Do not open, hash, preview, decompress or run `git status` on placeholders just to classify them — that can hydrate files. Skip secrets, credentials, keys and private database bodies. Do not follow symlinks or cross volumes. Report inaccessible paths and incomplete measurements. APFS clones mean summed allocation is not guaranteed reclaimable.

Use `scripts/topeira-icloud-status.swift <paths...>` for read-only Foundation status queries (uploaded / uploading / downloading / requested / conflicts / errors / excluded). Missing keys mean unknown, not false. A parent marked uploaded does not prove every descendant is. Never call repair/reset actions.

## Real content discrimination

Read representative resident README, handoff, result, manifest, patch and index files. Record exact paths, what was inspected, purpose, dates as context, confidence and limits. Separate conclusions supported by content from name-based leads. Age, identical README, equal HEAD or closed conversations alone do not establish redundancy.

For repositories, distinguish clones, registered worktrees, bare backups, fixtures and snapshots. Before recommending deletion check local changes, unique untracked/ignored files, unpushed commits, refs, dependencies, ongoing tasks and owner/recovery source. If those checks would hydrate cloud files, defer and propose on-demand retention first. Archives must be verified before any source removal.

## Batch decisions

Classify each reviewed batch: keep-local, keep-cloud-on-demand, archive-consolidate, delete-candidate, unknown-review. Present exact paths, local/logical size, useful content, disposable part, uniqueness checks, sync evidence, recommendation, recovery implications, confidence and remaining checks. No overlaps or parent/child double counting. Split mixed folders. Say "sampled" when you sampled.

Approval for one action does not authorize another. Historical logs are evidence, not current authorization. Re-check each approved path before mutation and measure the real volume delta afterwards.

## Remove Download diagnosis

"Optimize Mac Storage" is pressure-based; it does not promise immediate eviction. "Keep Downloaded" retains local content. Opening files, indexers and scanners can download them again. Check current Apple documentation before explaining behavior. Observe processes and open handles without killing them; an open handle is a lead, not proof. Compare metadata before/after a small, explicitly approved eviction to test a hypothesis.

Before an approved eviction verify: file-level upload, no errors/conflicts, pinning, active readers/writers, provider state. Use Finder's Remove Download or the native eviction API — **never `rm`**: eviction keeps cloud data, deletion propagates to every synced device. iCloud sync is not a backup. Never sign out, reset FileProvider, delete CloudKit/`bird` state or force cloud removal to "fix" downloads.

## Delivery

Deliver content-grounded batches and a concrete next step, not only size rankings. Report local-byte changes separately from deletions; do not attribute system/user eviction to yourself. Save a sanitized report without credentials or client-content excerpts.

For multi-round continuation see [continuous-drill.md](continuous-drill.md).
