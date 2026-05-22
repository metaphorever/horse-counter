# Phase 1.23 — GitHub Actions Deploy

Automate the current manual deploy sequence (SSH → git pull → restart) so that
every push to `master` deploys to the VPS without any manual steps.

---

## What it does

On push to `master`:
1. SSH into `metaphorever@zap.rupture.net`
2. `git pull origin master` in the app directory
3. `uv pip install -r requirements.txt` — picks up any new deps automatically
4. `systemctl --user restart poet-horse.service`

Fails fast (`set -e`) so a broken pull never triggers a restart on stale code.

---

## Secrets required

One GitHub Actions secret must be added to the repo before the first run:

| Secret name | Value |
|---|---|
| `DEPLOY_SSH_KEY` | Private half of the deploy key (ed25519, no passphrase) |

---

## One-time VPS setup

Run these once from a local terminal that can SSH into the VPS:

```bash
# 1. Generate a deploy key (no passphrase — GitHub Actions can't enter one)
ssh-keygen -t ed25519 -C "github-actions-poet-horse" -f ~/.ssh/poet-horse-deploy -N ""

# 2. Authorize it on the VPS
ssh-copy-id -i ~/.ssh/poet-horse-deploy.pub metaphorever@zap.rupture.net

# 3. On the VPS — enable lingering so the user systemd session survives SSH exit
#    (required for systemctl --user to work from a non-login SSH session)
ssh metaphorever@zap.rupture.net "loginctl enable-linger metaphorever"

# 4. Add private key to GitHub Secrets
#    Repo → Settings → Secrets and variables → Actions → New repository secret
#    Name: DEPLOY_SSH_KEY
#    Value: contents of ~/.ssh/poet-horse-deploy  (the private key, no .pub)
cat ~/.ssh/poet-horse-deploy   # copy this whole block including the header/footer lines
```

---

## Decisions

- **`appleboy/ssh-action@v1.0.3`** — handles SSH connection, key loading, and
  script execution cleanly; widely used, no extra deps.
- **`XDG_RUNTIME_DIR` export** — `systemctl --user` needs the D-Bus user socket;
  SSH sessions don't set this automatically, so we export it explicitly.
- **`uv pip install` included** — idempotent; adds ~2s per deploy but ensures
  requirements changes deploy automatically without a separate manual step.
- **No health check** — gunicorn restarts in ~1s and Apache proxies through;
  a post-restart health check would add complexity for no real gain at this scale.
- **Trigger: push to master only** — PRs don't deploy; only merged/direct pushes do.
