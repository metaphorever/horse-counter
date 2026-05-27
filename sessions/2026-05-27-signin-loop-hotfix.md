# Session: Sign-in loop hotfix — 2026-05-27

```
Model:                Opus 4.7
Effort:               high
Uncertainty flagging: standard
Git:                  master, current at open
Open holds:           none
```

Unplanned production hotfix (not a roadmap phase). Live incident: users stuck
bouncing between `/sign-in` and `/setup-account`.

---

## What shipped

### Sign-in / setup-account redirect loop fix

The global Clerk-session bridge in `base.html` (the `{% if clerk_publishable_key
and not current_user %}` script, ~line 160) redirected **any** page without a
Flask `current_user` to `/sign-in`. It only excluded `/sign-in` itself.

Two pages legitimately have a live Clerk session but no Flask user, and got
ping-ponged:

- **`/setup-account`** — mid-signup, before the user record is created (only
  `pending_clerk_id` is in session, not `user_id`). Bridge fired
  `window.location.href = '/sign-in'`; sign-in re-verified and redirected back
  to `/setup-account`; repeat. Affected **every** new signup.
- **`/sign-out`** — session just cleared, but `Clerk.user` still live for a beat,
  so the bridge raced to bounce to `/sign-in`, which re-verified and signed the
  user back in. Latent "can't stay signed out" bug, same root cause.

Fix: exclude all three auth-flow pages from the bridge —
`['/sign-in', '/setup-account', '/sign-out'].includes(pathname)`.

Commit: `8d59311`. Deployed via GitHub Action (success, 13s).

---

## Diagnosis note (why the prior fix missed it)

`d98ec02` ("Fix sign-in/setup-account redirect loop for users with cookie
issues") patched the **server-side** redirect: when `/setup-account` finds no
`pending_clerk_id`, it now bounces to `/sign-in?session_error=1` and the page
shows an error instead of re-verifying forever.

That addressed a *session-not-persisting* loop. The actual live loop was a
**separate, client-side** source — the base.html bridge — that fires even when
the session persists fine (because `current_user` is correctly falsy mid-signup).
Same symptom ("sign-in loop"), two independent causes. The decisive clue was
Clover's observation that hitting **Stop** on `/setup-account` left a working
page — proving the redirect was client-side JS, not a server 302.

---

## Testing holds

None. Clover verified both flows on the live site immediately after deploy:
fresh signup stays on `/setup-account` to pick a slug; sign-out stays signed out.

---

## Next session

Back to Phase 2 priority work (see ROADMAP.md). Open rough edges from the
2026-05-25 posture still stand (PA redirect, admin featured table on mobile,
editor section label parity). No holds from this hotfix.
