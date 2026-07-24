# Bunny Stream → R2 → MongoDB → Telegram pipeline

FastAPI project that:

1. Uploads a video directly to **Bunny Stream** via API.
2. Waits (polls) until Bunny finishes transcoding.
3. Downloads Bunny's finished output **zip** (all qualities of mp4, HLS
   folders, `master.m3u8`, per-quality playlists, thumbnails, preview
   video/image, seek sprite folder — everything).
4. Unzips it and uploads every single file to **Cloudflare R2**.
5. Saves every resulting link into **MongoDB**.
6. Optionally auto-posts the thumbnail + a caption link to one or more
   **Telegram channels** on a schedule.

A small dashboard (`/dashboard/overview`, `/dashboard/myfiles`,
`/dashboard/settings`) is included to drive all of this.

**This project never creates or hosts a streaming/watch page.** It only
builds the caption link `STREAMING_DOMAIN/ad/{mapping}` that your existing
streaming site is expected to handle.

## 1. Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real values
```

You need:
- A running MongoDB instance (`MONGO_URI`).
- A Bunny Stream video **library ID** + **Stream API key**
  (`BUNNY_LIBRARY_ID`, `BUNNY_STREAM_API_KEY`).
- The **storage zone name + password** backing that library, used only to
  download the finished output zip:
  `BUNNY_STORAGE_ZONE_NAME`, `BUNNY_STORAGE_PASSWORD`.
- A Cloudflare R2 bucket + API token (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`) and its public base URL
  (`R2_PUBLIC_BASE_URL` — either the bucket's `r2.dev` public URL or your
  own custom domain attached to the bucket).
- A Telegram bot token from @BotFather (can also be set later from the
  Settings page instead of `.env`).
- `STREAMING_DOMAIN` — the domain your separate streaming site lives on;
  only used to build the caption link.

Run it:

```bash
python run.py
# or: uvicorn app.main:app --reload
```

Open `http://localhost:8000/dashboard` — default login is
`DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` from `.env` (change these).

## 2. How a single upload flows through the system

1. **`POST /api/upload`** (called by the My Files page) — accepts
   multiple files at once, and a whole folder via the browser's
   `webkitdirectory` picker or drag-and-drop.
2. Each file is validated as a video (images/audio are rejected — only
   video extensions in `app/core/naming.py::ALLOWED_VIDEO_EXTENSIONS`
   are accepted).
3. It's renamed to `TG-@atoz_links-VID_{DDMMYYYYHHMMSS}{ext}`. **The
   original filename is never written to Mongo or anywhere else** — only
   this generated name is stored, per the requirement.
4. A Bunny Stream video object is created, the file is uploaded to it, and
   a MongoDB doc is inserted immediately with:
   - `status: "PROCESSING"`
   - `title: ""`, `thumbnail: null` → the dashboard shows a black
     placeholder thumbnail and no title while this is the state.
   - a random `mapping` slug (used later for `STREAMING_DOMAIN/ad/{mapping}`).
5. A background task (`app/core/pipeline.py::run_pipeline`) is kicked off
   immediately and does the rest without blocking the HTTP response:
   - Polls `GET /library/{id}/videos/{videoId}` every 10s until Bunny's
     `status` field reaches `4` (Finished), or marks the doc `ERROR` if
     Bunny reports an error/timeout.
   - Downloads the output zip from exactly:
     `https://storage.bunnycdn.com/{BUNNY_STORAGE_ZONE_NAME}/{videoId}/?accessKey={BUNNY_STORAGE_PASSWORD}&download`
   - Unzips it, walks every file (root-level files **and** nested HLS/seek
     folders), and uploads each one to R2 under
     `videos/{mapping}/{original relative path in the zip}`.
   - While uploading, it buckets recognized files into: `thumbnail(s)`,
     `preview_image`, `preview_video`, `master_playlist`, `qualities`
     (per-resolution mp4), `hls` (per-resolution playlist + segment
     links), `seek_thumbnails`. **Every file — recognized or not — is
     also stored in `all_files`**, so nothing from the zip is ever lost
     even if Bunny's internal folder naming differs from what's assumed
     here (see "Assumptions" below).
   - Updates the Mongo doc: `status: "READY"`, fills in `title`,
     `thumbnail`, and all the link fields above.

## 3. Telegram auto-posting

- **Adding a channel**: there's no manual "add channel" form. In Telegram,
  forward any message from the target channel to the bot in a private
  chat. The bot reads the forwarded message's origin, registers the
  channel in MongoDB (default: manual/interval `0`, quantity `1`,
  active), and replies "✅ Channel added: ...". This requires:
  - The bot token saved in Settings (or `TELEGRAM_BOT_TOKEN` in env).
  - `PUBLIC_URL` set in the environment, so the app can register its
    Telegram **webhook** at `{PUBLIC_URL}/api/telegram/webhook`. This
    happens automatically on startup and whenever you save a new bot
    token; you can also trigger it manually via
    `POST /api/settings/bot/setup-webhook`.
  - The forwarded message must show its origin — if the channel hides
    "forwarded from" info, Telegram won't include it and the bot will
    reply asking you to unhide it or try a different message.
- Once a channel appears in the Settings table, you can edit its
  **interval** (manual/15min/30min/1h/2h/6h/12h/24h), **quantity per
  batch**, and **active** toggle directly inline — changes save
  immediately. The only action button is **remove**, which deletes the
  channel (name, id, everything) from MongoDB.
- A background scheduler (`APScheduler`, checked every minute) posts the
  oldest `READY` videos that haven't yet been posted to a given channel,
  once that channel's interval has elapsed. Interval `0` ("manual") never
  auto-fires — set a real interval from the table if you want it to post
  on its own.
- Each post is `sendPhoto` with the video's thumbnail and a caption
  containing `STREAMING_DOMAIN/ad/{mapping}`.
- **You must add the bot as an admin to each channel yourself** in
  Telegram so it's able to post.
- The Settings page's top card shows: bot name (fetched via Telegram's
  `getMe`), total channels, total posts, and total failed posts — each
  channel also tracks its own `posted_count` / `failed_count`.

## 4. Dashboard pages

- `/dashboard/overview` — total videos, total storage used (sum of every
  uploaded file's byte size across all videos), total views.
- `/dashboard/myfiles` — drag-and-drop / multi-file / whole-folder upload
  with a live progress bar per batch; a 25-per-page table showing
  thumbnail, title, status, mapping, and actions (edit title/folder, play
  in a modal `<video>` player using the HLS `master.m3u8`, delete — delete
  also best-effort removes the Bunny video and every R2 object under that
  video's prefix).
- `/dashboard/settings` — bot token + channel management described above.

## 5. Assumptions made (please confirm/adjust)

Bunny Stream's exact internal zip folder/file naming isn't guaranteed to
match one exact convention, so `app/core/zip_processor.py` uses pattern
matching rather than hardcoded paths:
- A file counts as a **thumbnail** if `"thumb"` is in its filename and
  it's an image.
- A file counts as **preview image** if its name starts with `preview`
  and is an image; **preview video** if it starts with `preview` and is
  `.webp/.mp4/.gif`.
- A root-level `master.m3u8` / `playlist.m3u8` / `index.m3u8` is treated
  as the **master playlist**.
- A root-level `{number}p.mp4` (e.g. `720p.mp4`) is treated as a
  **per-quality mp4 fallback**.
- Any `.m3u8`/`.ts`/`.m4s` file inside a subfolder is treated as part of
  an **HLS folder**, keyed by that subfolder's name (e.g. `720p`).
- Anything inside a folder literally named `seek` is treated as a
  **seek/storyboard thumbnail**.
- Whatever doesn't match any of the above is still uploaded to R2 and
  recorded in `all_files`, so you can inspect a real zip once and adjust
  these rules in one place if your Bunny plan structures things
  differently.

Other assumptions, called out because they weren't fully specified:
- **Dashboard auth**: a minimal username/password login (env-configured)
  protects `/dashboard/*`; there was no login system specified, so this
  is the simplest reasonable default — swap for real auth/SSO if needed.
- **"Storage used"** on the overview page sums the byte size of every
  file actually stored in R2 for every video (recorded during upload),
  not Bunny's own storage.
- **Folder support** in My Files is a simple string tag per video (from
  either a manual "folder" field on upload or the top-level name of a
  drag-and-dropped folder) plus a filter — there's no nested folder tree
  UI, since none was specified.
- Background jobs run as in-process `asyncio` tasks / APScheduler inside
  the FastAPI process. That's fine for a single instance; if you deploy
  multiple replicas, move `run_pipeline` and the channel-posting job to a
  real queue (Celery/RQ + Redis) so only one worker executes each job.

## 6. Project layout

```
app/
  main.py              FastAPI app, mounts routes + static files
  config.py            Settings loaded from .env
  database.py          Motor (async MongoDB) client + collections
  models.py             Pydantic schemas
  core/
    naming.py           custom filename + mapping slug generation
    bunny.py            Bunny Stream API client (create/upload/status/zip URL)
    zip_processor.py    unzip + categorize + upload every file to R2
    r2.py               Cloudflare R2 (boto3 S3-compatible) client
    pipeline.py         the background job tying steps 2-5 together
    telegram.py         sendPhoto + admin verification
    scheduler.py        APScheduler auto-posting loop
    auth.py             simple signed-cookie dashboard login
  routes/
    upload.py           POST /api/upload
    files.py            /api/files (list/detail/edit/delete/view)
    overview.py         /api/overview
    settings.py         /api/settings/bot, /api/settings/channels
    dashboard.py        HTML pages + login
  templates/            Jinja2 dashboard pages
  static/                CSS + JS for the dashboard
```
