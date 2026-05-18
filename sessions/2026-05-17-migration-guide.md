# Migrating an In-Progress Project

This is a one-time session guide. When the migration is done, archive this file to `sessions/YYYY-MM-DD-migration.md` and delete it from the project root.

---

## What this session does

- Installs the new process without relitigating project history
- Treats past decisions as settled unless something looks actively wrong
- Audits for gaps that should be filled before the next phase
- Sets up clean forward motion from the current state

This is not a reconstruction project. The goal is a working cockpit for the next session, not a perfect record of every session that came before.

---

## Step 1 — Install the files

Add to the project root:
- `CLAUDE.md` — from template, current phase block updated to match actual current phase
- `CLAUDE-REFERENCE.md` — from template, unchanged
- `ROADMAP.md` — from template, phase map updated to reflect actual phase history and current state

Create folders if they don't exist:
```
sessions/
spec/
```

---

## Step 2 — Archive project history

Whatever the project used before — a long CLAUDE.md, notes, a design doc — don't delete it. Move it:

```
sessions/pre-migration-history.md
```

Add a single header to that file:
```markdown
# Pre-migration project history
Archived [date]. Original project documentation before adopting the claude-project-template workflow.
Full git history available via `git log`.
```

That's it. Don't try to convert it into session log format. It's a reference, not a record.

---

## Step 3 — Write the product spec

Open `spec/product.md` and fill it in — not from scratch, but from what the project has revealed about itself so far. A project that's been running for a while often knows more about what it actually is than the original pitch did.

Claude's job here is to ask, not to fill in. The questions:
- What is this and what does it do? (What does it actually do, not what you planned?)
- Who is it for?
- What need does it address?
- How will you know if it succeeded or failed?
- What is explicitly out of scope? (Especially things that came up and got deferred)

If the answers have drifted from whatever the original intent was — name that drift explicitly. It's useful information, not a failure.

**This is a hard stop before Step 4.** If `spec/product.md` isn't committed, Step 4 doesn't start.

---

## Step 4 — Write the technical spec

Open `spec/technical.md` and capture current state: architecture as it actually exists, data model as built, dependencies in use, git workflow already in place, build and test commands.

Fill in the build commands block in CLAUDE-REFERENCE.md from whatever the project uses.

Claude should flag anything that looks like:
- A decision that was never fully articulated
- A dependency that was added without tradeoffs being named
- An open question that got built around instead of resolved
- Complexity that isn't justified by the product spec

These go into ROADMAP.md under **Open design questions**, not into the spec as if they're resolved. Flag them, don't paper over them.

---

## Step 5 — Audit for process gaps

Claude reads through the pre-migration history and current codebase looking for:

**Decisions that need a provenance label**
Anything architectural that future sessions might revisit. These go into ROADMAP.md under **Decisions log** with the label `[pre-migration — provenance unknown]`. That's honest and useful — it flags that the decision exists without pretending it was tracked.

**Deferred ideas that got lost**
Things that came up in conversation and never made it to a backlog. These go into ROADMAP.md under **Backlog**.

**Testing holds**
Anything that shipped but was never manually verified. Flag it. The next phase doesn't start until Clover has actually confirmed it works.

**Rules that were implicitly followed or ignored**
If the project has patterns that conflict with the new process, name them now rather than discovering the friction in session. Some conflicts are fine — natural project drift. Others are gaps worth closing.

---

## Step 6 — Update current phase block

Update CLAUDE.md's current phase block to reflect exactly where the project is:

```
**PHASE: [N.N] — [Name]**
**Status: [status]**
**Model: [model] · Effort: [level]**
```

If the project is mid-phase, note what's done and what remains in the first session log.

---

## Step 7 — Write the migration session log

```markdown
# Session — [Date] — Migration: [Project Name]

## Session setup
- Model / Effort / Uncertainty: [what was used for this session]
- Open holds: none (migration session)

## What shipped
- Installed CLAUDE.md, CLAUDE-REFERENCE.md, ROADMAP.md
- Archived pre-migration history to sessions/pre-migration-history.md
- Committed spec/product.md
- Committed spec/technical.md

## Decisions made
- [Any decisions made during the audit — label each]

## Uncertainty flags
- [Anything Claude flagged as uncertain about current project state]

## Testing holds
- [Anything identified during audit that needs manual verification]

## Carryover
- [What the next session needs to know]

## Deferred / added to roadmap
- [Anything surfaced during audit that went to backlog or open questions]
```

---

## Step 8 — Commit and close

Single commit:
```
git add .
git commit -m "Migrate to claude-project-template workflow"
```

Push per the project's git workflow.

Archive this file:
```
mv MIGRATION.md sessions/YYYY-MM-DD-migration.md
git add .
git commit -m "Archive migration guide"
```

Close the session normally. State the next phase, model, effort, and any holds to clear.

---

## What to do if the audit reveals something serious

If the audit surfaces a real problem — a wrong architectural assumption that's been built on, a dependency with a serious tradeoff that was never named, something that looks actively broken — don't paper over it to get the migration done.

Stop. Name it. Use the post-mortem template in CLAUDE-REFERENCE.md if warranted. The migration can wait; building forward on a bad foundation cannot.
