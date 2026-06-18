# poet.horse — Deployment Reference

Production deployment of the horse-counter Flask app at `https://poet.horse`,
hosted on Jon's shared VPS at `zap.rupture.net`.

**Status:** ✅ Fully working — HTTPS, Clerk auth (Google OAuth), Tumblr posting,
admin role all verified end-to-end as of 2026-05-15.

## Server

- **Host:** `zap.rupture.net` — multi-IP Ubuntu host running Apache 2.4
- **IP for poet.horse:** `162.221.25.24` (server has .18–.24 in the 162.221.25.x range)
- **Login:** `metaphorever@zap` via SSH
- **Permissions:** `metaphorever` is NOT in sudoers. System-level changes
  (Apache config, modules, certbot, firewall) must go through Jon at
  `admin@rupture.net`. Jon is friendly and helpful.

## DNS (Cloudflare)

- `poet.horse` A → `162.221.25.24` — **orange/proxied**, SSL mode **Full**
- Clerk satellite CNAMEs (5 total, from Clerk dashboard) — **grey/unproxied**:
  - `clerk.poet.horse` → `frontend-api.clerk.services` (plus 4 others)
  - These MUST stay grey or Clerk breaks.

## Apache vhost (managed by Jon, in `/etc/apache2/sites-enabled/001-vhosts.conf`)

```apache
<VirtualHost 162.221.25.24:80>
    ServerName poet.horse
    Redirect / https://poet.horse/
</VirtualHost>

<VirtualHost 162.221.25.24:443>
    SSLEngine on
    SSLCertificateFile "/etc/letsencrypt/live/poet.horse/fullchain.pem"
    SSLCertificateKeyFile "/etc/letsencrypt/live/poet.horse/privkey.pem"
    ServerName poet.horse
    Alias /.well-known/acme-challenge/ /home/metaphorever/letsencrypt-webroot/.well-known/acme-challenge/
    <Directory /home/metaphorever/letsencrypt-webroot/.well-known/acme-challenge/>
        Require all granted
    </Directory>
    ProxyPass /.well-known/acme-challenge/ !
    ProxyPass / http://127.0.0.1:8765/
    ProxyPassReverse / http://127.0.0.1:8765/
</VirtualHost>
```

Required Apache modules: `proxy_module` + `proxy_http_module`.

**Firewall:** Jon allowlisted everyone on `162.221.25.24:80` and `:443`. Required
for Cloudflare to reach the origin (otherwise Cloudflare returns 522).

**SSL renewal:** Auto-renews via certbot timer. Cert expires 2026-08-12.
Webroot for ACME challenges: `/home/metaphorever/letsencrypt-webroot/`.

## Gunicorn service (systemd user service)

- Service file: `/home/metaphorever/.config/systemd/user/poet-horse.service`
- App directory: `/data/home/metaphorever/horse-counter`
- Venv: `/home/metaphorever/.venv`
- Binds to: `127.0.0.1:8765`, 2 workers
- **Has** `EnvironmentFile=/data/home/metaphorever/horse-counter/.env`
  (required or env vars don't load)

**Installing Python packages — the venv has NO `pip`.** Use `uv`, the same way
the deploy workflow does. `python -m pip ...` fails with "No module named pip".
```bash
/home/metaphorever/.local/bin/uv pip install <pkg> --python /home/metaphorever/.venv/bin/python
```

**Playwright / headless Chromium (image-card export + PQ scrape) — noble gotcha.**
`playwright install-deps chromium` will *always* fail on this Ubuntu 24.04 box
(exit 100, `Package 'libasound2' has no installation candidate`): the t64 ABI
transition renamed `libasound2` → `libasound2t64` and Playwright hardcodes the
old name. **Ignore that command's exit code** — it is not the gate. The system
libs are installed via an explicit `apt install` of the t64-named packages
(root, through Jon). The real check is launching Chromium:
`python -m playwright install chromium` (user-space) then a `chromium.launch()`
smoke test. If that prints OK, the deps are sufficient regardless of what
`install-deps` says.

```bash
systemctl --user [start|stop|restart|status] poet-horse.service
```

View running env vars:
```bash
cat /proc/$(systemctl --user show -p MainPID poet-horse.service | cut -d= -f2)/environ | tr '\0' '\n'
```

## .env file (`/data/home/metaphorever/horse-counter/.env`)

Required keys:
- `SECRET_KEY` — Flask session signing
- `APP_PINS` — comma-separated SHA-256 hashes (NOT raw PINs)
  - Generate: `python3 -c "import hashlib; print(hashlib.sha256(b'mypin').hexdigest())"`
- `TUMBLR_CONSUMER_KEY`, `TUMBLR_CONSUMER_SECRET`
- `TUMBLR_REDIRECT_URI=https://poet.horse/callback`
- `TUMBLR_BLOG_NAME=counting-horses`
- `CLERK_PUBLISHABLE_KEY` (pk_live_…), `CLERK_SECRET_KEY` (sk_live_…)
  - **Note:** Clerk dashboard suggests `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (Next.js style) —
    strip the prefix; the Flask app reads `CLERK_PUBLISHABLE_KEY`.

## Clerk

- **Production keys** (pk_live / sk_live), not dev. Dev keys complain in production.
- **Required social-OAuth setup per provider** (Google, GitHub) in production:
  1. Clerk dashboard shows the redirect URI (e.g. `https://clerk.poet.horse/v1/oauth_callback`)
  2. Register an OAuth app at the provider, paste that exact URI as authorized
     redirect (must match character-for-character)
  3. Paste the provider's client_id + secret back into Clerk's SSO Connection
- Email/magic link works without provider config.
- Clerk JS in `templates/base.html` loads from
  `https://clerk.poet.horse/npm/@clerk/clerk-js@5/dist/clerk.browser.js` —
  **NOT** the generic jsdelivr URL (that loads the headless build and
  `mountSignIn` fails with "Clerk was not loaded with Ui components").
- Clerk requires HTTPS — refuses to set cookies on HTTP
  (`secure-context: false` error).

## Database (SQLite)

- **Path:** `/data/home/metaphorever/horse-counter/data/poet.db` (NOT `db/poet.db`)
- Initialise schema:
  ```bash
  cd /data/home/metaphorever/horse-counter
  /home/metaphorever/.venv/bin/python -m tools.init_db --seed-tags
  ```
- No `sqlite3` CLI on the server — use Python:
  ```bash
  python3 -c "import sqlite3; c=sqlite3.connect('/data/home/metaphorever/horse-counter/data/poet.db'); print(list(c.execute('SELECT slug, role FROM users')))"
  ```
- Grant admin:
  ```bash
  python3 -c "import sqlite3; c=sqlite3.connect('/data/home/metaphorever/horse-counter/data/poet.db'); c.execute(\"UPDATE users SET role='admin' WHERE slug='clover'\"); c.commit()"
  ```
  Role is read fresh on every request — no re-login needed (sometimes re-clicking
  sign-in helps).

## First-login flow gotcha

After first Clerk sign-in, the app stashes `pending_clerk_id` in session and
redirects to `/setup-account` for slug picking. If you miss the slug picker
(e.g. landed on `/` instead), visit `/sign-in` again — the verify endpoint
will re-redirect to `/setup-account` since no user record exists yet for that
Clerk ID.

## Manual files not in git

- `data/horses.json.gz` (~29 MB) — in `.gitignore`. Must be SFTP'd from local
  on fresh deploy. (`scp` hung — use SFTP.) Without it, the dictionary fails
  to load and counting is disabled.

## Deploying code changes

**Push to `master` — that's it.** GitHub Actions auto-deploys on every push to master (git pull + gunicorn restart on the VPS). No need to SSH in for routine deploys.

SSH is only needed for: manual DB operations, env var changes, inspecting logs, or recovering from a broken deploy.

## Lessons learned (so we don't relearn them)

1. **`proxy_http_module` not enabled** — caused 500s; needed `a2enmod proxy_http`.
2. **EnvironmentFile not added to service** — `systemctl --user edit` didn't
   save the override; had to nano the main service file directly.
3. **Cloudflare SSL mode** — Flexible works for plain HTTP origin; Full needed
   once cert installed; orange/proxied required for the public site, grey for
   Clerk CNAMEs.
4. **Cloudflare 522** — origin firewall was blocking Cloudflare IPs; Jon
   allowlisted everyone on 80/443.
5. **Clerk JS URL** — generic jsdelivr URL is headless; needed the Frontend API
   URL (`https://clerk.poet.horse/npm/...`) for UI components.
6. **DB path** — `data/poet.db` not `db/poet.db`.
7. **`.env` Clerk var name** — strip the `NEXT_PUBLIC_` prefix that Clerk
   suggests by default.

## Quick health check

```bash
# On zap:
systemctl --user status poet-horse.service           # gunicorn running?
curl -vk https://162.221.25.24/                      # origin reachable?
curl -v https://poet.horse/                          # full stack via Cloudflare?
```
