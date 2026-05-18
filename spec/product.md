# poet.horse — Product spec

Written during the 2026-05-17 migration session. Clover's words throughout — Claude's job here was to ask, not to fill in.

---

## What is this and what does it do?

poet.horse is a website where every word in a poem must be a real, registered horse name — millions of them, backed by pedigreequery. Anyone can compose, publish, and read poems on the site.

In Clover's words today, after Phase 1.6 shipped:

> It is the nicest hobby project I have ever had. It has every feature I ever dreamed of for a creative writing tool in the horse poetry format. I am already impressed and heartened by the favorable responses and creative contributions from the tumblr community and see a lot of potential for building community around this shared format and tool.

**Notable: no drift.** The current state matches the original intent. The project arrived at what was imagined — uncommon for a project of this length.

The constraint phrasing is intentionally open at the upper bound — "millions" rather than a fixed number — to leave room to expand the dictionary later without rewriting the pitch. The lower bound is firm: real, registered, backed by an external source (currently pedigreequery; could be others).

---

## Who is it for?

> Feature complete for me, now I want to share it with the world. Tumblr proved it is popular with artistic weirdos but the world is full of artistic weirdos and horse lovers.

A calibrated success ladder — not one audience, three:

1. **Floor: a personal tool with a small loyal community.** "If it stays a personal project with a small loyal community that is already more than I could hope for." Already met.
2. **Middle: real income.** "If there is enough engagement to make it a realistic income stream I am willing to devote a lot of time to nurturing that."
3. **Moonshot: viral / generational platform.** "If it can go viral, get memed, turn into a gen-alpha hangout that bypasses social media blocks I would love that."

The **"gen-alpha hangout that bypasses social media blocks"** thread is a real UX constraint, not a throwaway: it implies low friction to share, works without forcing an account, doesn't look or behave like Yet Another Social App, and lives outside the algorithmic-platform jurisdiction teens are routed around.

---

## What need or problem does it address?

> All art needs constraints, mine are horse shaped.

Four overlapping needs, in Clover's framing:

**1. A fresh creative constraint.** Found poetry / constrained writing has a long lineage; horse names are a fresh constraint people haven't seen.

**2. A friendly venue for weirdness.** "This is a home for weirdos." Big platforms flatten or punish strangeness via algorithms and moderation. poet.horse is a place where weirdness is the point.

**3. Old-web ethos: a place to create.** "Old web ethos of being a place to create first and foremost. To engage with the site and community you must engage with the quirks and whimsy of the concept."

**4. Friction as moderation.** The horse-name requirement is a defensive moat against the spam / corporate / AI-slop patterns that have hollowed out every other platform.

> Target can't make a corporate account and post about sales unless they put in the work to make it out of horses.

**Plus the personal one** — every dev iteration is genuinely fun for the maker:

> Every development is FUN for me personally. I get better tools to make art, I get to read more creative poetry, I get to explore silly css and old school typography. This is all of my favorite things all jumbled together.

This is a spec-level input: the project's worst case is still rewarding for the maker, so it doesn't depend on growth to be worth doing.

---

## How will we know if it succeeded or failed?

### Success

Already met. The floor is high.

> Happy with even a micro community and maintaining it for myself. $20 a year is a low price for the joy it currently brings. Even with no community I would maintain it as a personal tool unless I am really destitute.

Higher tiers (income, virality) would be nice and would change time investment, but their absence isn't failure.

### Failure

Failure is specific and narrow: the site becomes a net negative. Three concrete vectors:

1. **Spam breaks through.** The horse-name friction stops working as a moat and the site becomes unusable.
2. **Doxxing via horses.** Someone encodes identifying info about a real person in a poem (using the constraint mechanism as a harassment vector). This is specific to *this* moderation surface and worth designing for.
3. **Legal threats from publishing companies about infringement.** Clover's stance: "Fair use is a defense not a shield. I am willing to concede to legal threats if I can keep the spirit of the site."

---

## What is explicitly out of scope

### Permanently out

- **Algorithmic / engagement-ranked front page.** Search, filter, and clearly-labeled curation are the discovery model. "No black box algorithms."
- **Public engagement metrics as the dominant frame.** See refinement below — surfacing them in opt-in discovery contexts is fine; structuring the site around them is not.
- **Voting on horse popularity or poem popularity** as a thumbs-up affordance. Rankings come from real usage signals (publishes, saves, pasture adds, views), never a vote.
- **Filtering the dictionary by "appropriate" names.** The dictionary stays a fact, not a vibe. Moderation happens on poems, not on the source data.
- **Third-party tracking** (pixels, analytics SDKs, fingerprinting). Server logs only; self-hosted Plausible acceptable later if needed.
- **AI-generated poem submissions.** Stated rule: "AI get the same restriction as under 13s — if you can successfully pretend to be an adult human there's nothing I can do to stop you but please behave and post good poems." The horse-name constraint does most of the enforcement work.
- **DMs.** Profiles can link to external sites/socials; users slide into DMs on Discord or wherever, not here.
- **Comment sections / complicated reply structures.** "Reply" via your own poem is the engagement model.
- **SPA / heavy JS framework.** Web 1.0 ethos: static where possible, light JS, view-source-able.
- **Addictive engagement loops.** "Fun and engaging, but not 'addictive.'"
- **Importing the legacy `data/poems/*.json` and counting-horses Tumblr archive.** Added 2026-05-17: *"I am thinking of doing a fresh launch rather than importing old poems to keep everything on the new site under the new explicit TOS."* Cleaner consent story; older work stays on Tumblr or wherever it already is. Strikes the archived Phase 1.18 from the plan.

### On the table but not committed

- **Ads (Carbon-style polite banners) for revenue.** Not ruled out if monetization becomes viable. Default policy: "We may run ads but you can block them if you want, we don't go out of our way to hoover up your data but we are not the place to expect real privacy shields." Privacy implications considered and weighed at the time.
- **Native mobile app.** Out of scope unless community demand surfaces it. "I like the web charm but if the community demands it then I won't rule it out."
- **Collaborative modes (exquisite corpse, send-a-horse-to-a-friend).** Both interesting; both deferred. "I want to keep it pretty constrained to the current loop until there is real demand from a real community who is actually making it worth my time."

### Net additions in scope (new from this session)

- **Following other posters.** Low-key social graph; no DMs, no friend requests, just a feed-following primitive. Slot into backlog.
- **Profile bios constructed from horse names.** On-brand requirement: your bio must obey the constraint too.
- **Profile external links.** Personal sites, social platforms — the explicit place to take connection off-platform.
- **"Response to" link variant of attribution.** Tentative — extends the Phase 1.5 attribution flag (`inspired_by_text` / `inspired_by_url`) to point at a poet.horse permalink rather than only an external work. "Fun and pretty low cost to build in with the current structure but it doesn't need to block anything currently in dev."

---

## Refinements / drift from archived ROADMAP

The migration prompt explicitly asks for drift to be named, not papered over.

### Popularity / metrics surfacing — refined

The archived cross-cutting commitment read:

> "Save (blue-ribbon) counts and Pasture-add counts are private to the user and admin only — never displayed publicly. No upvotes, no engagement metrics surfaced to users."

The refined position:

> Drift on metrics and voting is that it's okay to have these features, just not prioritize them. Having a heavily saved poem is a point of pride but not something the site structure is pushing users to pursue.

In effect:
- "Most saved poem about love" as a search/filter? **Yes.**
- "Most-ribbon-tagged horse" as a fun glimmer affordance? **Yes.**
- A leaderboard on the front page? **No.**
- Notifications nudging users toward more engagement? **No.**

The rule: **mechanical web-2 elements can exist in deliberate, opt-in discovery surfaces; they cannot become the dominant frame.** This supersedes the flat-no in the archived doc and will be carried into the new cross-cutting commitments.

### Everything else from the archived doc is inherited as-is

Including the full "Settled architecture," "Cross-cutting commitments" (with the metrics refinement above), and "Deferred / open" lists. Those don't need to be repeated here — the new `ROADMAP.md` carries the live version.
