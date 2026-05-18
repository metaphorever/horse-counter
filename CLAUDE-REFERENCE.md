# poet.horse — Reference

Read this file when: starting a new project (Phase 0), closing a phase, running a post-mortem, or reaching project completion. Not loaded every session.

---

## Decision log labels

- **Claude proposed, Clover confirmed** — Claude suggested it, Clover confirmed with genuine understanding
- **Claude proposed, Clover ok'd** — Clover ok'd without deep engagement; flagged if high-stakes
- **Clover proposed, Claude approved** — Clover suggested it, Claude had no objection
- **Clover proposed, Claude pushed back, Clover revised** — concern raised, Clover updated position: [what changed]
- **Clover proposed, Claude pushed back, Clover overrode** — concern raised, Clover proceeded anyway: [concern noted]
- **Claude steelmanned, changed position** — objection was right: [what changed]
- **Claude steelmanned, held position** — objection considered, original stance maintained: [why]
- **Claude error, caught by Clover** — Claude was wrong, Clover caught it
- **Claude error, caught in testing** — surfaced during manual or automated testing
- **Claude error, caught next session** — discovered later; note what allowed it to slip through
- **Override: Clover directed** — Clover explicitly went off-script: [what, why, what to revisit]
- **Deferred** — noted, not decided, added to roadmap

---

## Uncertainty flagging levels

| Model + Effort | Default | Meaning |
|---|---|---|
| Opus xhigh | high | Flag any call made without strong confidence |
| Sonnet high | standard | Flag decisions with meaningful downstream consequences |
| Sonnet medium | suppressed | Routine work, established patterns, CRUD plumbing |

Adjust at session start if the work is clearly more or less consequential than the effort level implies. Record the reason. A suppressed session that hits a consequential decision escalates mid-session — it does not defer the flag to close.

---

## Effort levels

- **xhigh** — complex reasoning, load-bearing copy, decisions with wide-ranging consequences
- **high** — non-trivial logic, interconnected systems, careful schema work
- **medium** — mechanical work: scaffolding, components, seed data
- **low** — never appropriate

---

## Session log template

```markdown
# Session — [Date] — Phase [N.N]: [Phase Name]

## Session setup
- Model / Effort / Uncertainty: [e.g. Sonnet · high · standard]
- Open holds: [from prior session, or "none"]

## What shipped

## Decisions made
[Label each per decision log vocabulary. High-stakes only — skip copy and naming.]

## Uncertainty flags
[**Uncertain:** blocks raised this session — resolved or still open]

## Testing holds
[What Clover must verify before next phase. Questions Claude will ask to confirm.]

## Carryover
[What next session needs that it can't infer from code. Max 6 bullets.]

## Deferred / added to roadmap
```

---

## Git workflow options

Decide during Phase 0. Record the decision and reasoning in `spec/technical.md`.

**Branch per phase, fast-forward to main** — clean history, clear phase boundaries. Works well solo. Breaks down with parallel work or multiple contributors.

**Trunk-based** — simpler branching, faster iteration. Requires discipline to keep main shippable at all times.

Force-push to main is never permitted unless explicitly agreed with a documented reason.

---

## Project completion checklist

When a project reaches its defined endpoint — before closing the final session:

**Freeze or maintain?**
- Personal utility that works: consider freezing. Document how to run it, what breaks if dependencies drift, whether it needs a lockfile or container.
- Active tool: define a maintenance schedule — how often reviewed, what triggers an unscheduled session.

**MVP or foundation?**
- v2, beta, or public launch ahead: map it in ROADMAP.md before closing out.
- This is the end: say so explicitly and close the roadmap.

**Post-project retrospective**
- What worked well in the process?
- What rules got bent, and why?
- Any lessons that belong in CLAUDE.md?

Claude initiates this conversation. It does not happen by default.

---

## Post-mortem template

For significant failures — not routine bugs, but anything that reveals a process or assumption problem.

```markdown
# Post-mortem — [Date] — [Brief description]

## What happened

## Root cause
[Not the proximate cause — the underlying one]

## Was this a process failure?
[Did a rule fail to catch it? Was a rule missing? Was a rule followed but wrong?]

## Decision provenance
[Which session introduced this? What was the label at the time?]

## Lesson
[What changes — in process, rules, or working approach — to prevent recurrence]

## CLAUDE.md update needed?
[Yes / No — if yes, what and where]
```
