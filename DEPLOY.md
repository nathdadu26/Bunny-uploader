# Deploying to GitHub + Koyeb (free tier)

## 1. Push the project to GitHub

From inside the project folder (the one with `Dockerfile`, `app/`, etc.):

```bash
git init
git add .
git commit -m "Initial commit: Bunny Stream -> R2 -> MongoDB -> Telegram pipeline"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

`.env` is git-ignored on purpose — never commit real credentials. Use
Koyeb's environment variables screen instead (step 3).

If the repo already exists and you're just pushing updates:

```bash
git add .
git commit -m "Update"
git push
```

## 2. Create the Koyeb service

1. Koyeb dashboard → **Create Service** → **GitHub** → pick this repo/branch.
2. Builder: **Dockerfile** (Koyeb auto-detects the `Dockerfile` at the repo root).
3. Instance type: **Free**.
4. Port: `8000` (matches `EXPOSE 8000` / the app's default `PORT`).
5. Health check path: `/api/health`.

## 3. Environment variables (Koyeb → your service → Settings → Environment variables)

Set all of these (same keys as `.env.example`):

```
MONGO_URI=...
MONGO_DB_NAME=bunny_r2_tg
BUNNY_LIBRARY_ID=...
BUNNY_STREAM_API_KEY=...
BUNNY_STORAGE_ZONE_NAME=...
BUNNY_STORAGE_PASSWORD=...
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=videos
R2_PUBLIC_BASE_URL=https://pub-xxxx.r2.dev
TELEGRAM_BOT_TOKEN=...
STREAMING_DOMAIN=https://your-streaming-site.com
SESSION_SECRET=some-long-random-string
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=some-strong-password
```

Plus the two keepalive-specific ones (see step 4):

```
PUBLIC_URL=https://<your-app>-<org>.koyeb.app
SELF_PING_INTERVAL_MINUTES=4
```

Mongo note: Koyeb's free tier has no built-in database, so point
`MONGO_URI` at a free MongoDB Atlas cluster (or any reachable MongoDB
instance) — don't try to run Mongo in the same container.

## 4. Why `PUBLIC_URL` matters (keeping the free service awake)

Koyeb's free instance type sleeps after a period without incoming HTTP
traffic, then cold-starts on the next request. `app/core/keepalive.py`
handles this from inside the app itself:

- On startup, if `PUBLIC_URL` is set, a background job is scheduled
  (via the same APScheduler already used for Telegram posting) that
  calls `GET {PUBLIC_URL}/api/health` every `SELF_PING_INTERVAL_MINUTES`
  minutes — no separate cron job, external uptime service, or extra file
  needed.
- After your first deploy, Koyeb shows you the public URL
  (`https://<app>-<org>.koyeb.app`). Copy it into `PUBLIC_URL` and
  redeploy (or just edit the env var and let Koyeb restart the service).
- `/api/health` is a trivial `{"ok": true}` route in `app/main.py` — cheap
  to call every few minutes and doesn't touch Mongo/Bunny/R2.
- Keep the interval comfortably under Koyeb's idle timeout; 4 minutes is
  a safe default.

If you'd rather not rely on self-pinging, you can instead point any free
external uptime monitor (UptimeRobot, cron-job.org, etc.) at
`https://<your-app>.koyeb.app/api/health` — both approaches hit the same
endpoint, so you can use either or both.

## 5. Redeploying after changes

Koyeb auto-redeploys on every push to the connected branch by default. To
trigger manually: Koyeb dashboard → your service → **Redeploy**.
