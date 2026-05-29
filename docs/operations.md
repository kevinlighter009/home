# Operations Guide

Day-2 operations for `home_photo_repo`: launchd auto-start, backups,
migration to a new Mac, local MLX provider setup, and troubleshooting.

## Install auto-start (launchd)

The worker and dashboard run as user-level launchd services. They start at
login, restart on crash, and write logs to `~/Library/Logs/home_photo_repo/`.

```bash
cd ~/Documents/code/home
make install-launchd
```

This installs three services:

| Service | When it runs | Log file |
|---|---|---|
| `com.homephoto.worker` | always (`RunAtLoad`, `KeepAlive`) | `worker.log`, `worker.err.log` |
| `com.homephoto.dashboard` | always | `dashboard.log`, `dashboard.err.log` |
| `com.homephoto.backup` | daily at 03:00 | `backup.log`, `backup.err.log` |

The MLX plist (`com.homephoto.mlx`) is optional and not installed by default.
See [Provider option B: Local MLX](#provider-option-b-local-mlx-apple-silicon)
below for the one-command opt-in (`make install-mlx`).

### Verify services are running

```bash
launchctl list | grep com.homephoto
```

You should see all three with PIDs (column 1 = PID, column 2 = last exit
code, column 3 = label). PID `-` means the service is loaded but not
currently running (this is normal for `backup`, which only runs at 03:00).

### Tail the logs

```bash
make logs
```

Or look at a single service:

```bash
tail -f ~/Library/Logs/home_photo_repo/worker.log
```

### Uninstall

```bash
make uninstall-launchd
```

This `launchctl bootout`s each service and removes the plists from
`~/Library/LaunchAgents/`. Safe to re-run; idempotent.

---

## Backups

### Automatic (nightly)

Once installed, `com.homephoto.backup` runs at 03:00 daily. Each run:

1. Calls `docker exec immich_postgres pg_dumpall -U postgres`.
2. Pipes the output through `gzip`.
3. Writes to `$BACKUP_DIR/immich_YYYY-MM-DD_HHMMSS.sql.gz` (default
   `$HOME/home_photo_repo_dev/immich/backups`).
4. Deletes any `.sql.gz` older than 14 days.

Tune via env vars in the plist or by overriding before manual runs:

```bash
BACKUP_DIR=/Volumes/PhotoSSD/immich/backups RETENTION_DAYS=30 \
  scripts/backup_postgres.sh
```

### Manual

```bash
make backup-now
```

Or for a different target:

```bash
BACKUP_DIR=/tmp/test-backup scripts/backup_postgres.sh
```

### Restore from a backup

```bash
# Stop services cleanly (preferred — single command):
make uninstall-launchd
# (Alternatively, if you want to keep the plists around for one-step re-install:
#  launchctl bootout gui/$UID/com.homephoto.worker  and the same for dashboard.
#  The plist files in ~/Library/LaunchAgents stay on disk that way.)

cd ~/Documents/code/home/docker/immich
docker compose down

# Wipe the existing pgdata.
rm -rf $DB_DATA_LOCATION/*

# Bring Postgres up alone and restore.
docker compose up -d database
sleep 10  # let it initialize
gunzip -c /path/to/immich_YYYY-MM-DD_HHMMSS.sql.gz | \
  docker exec -i immich_postgres psql -U postgres

# Bring the rest up.
docker compose up -d

# Re-load launchd services (re-renders plists from templates):
make install-launchd
```

---

## Migrate to a new Mac

The SSD holds everything portable; the launchd plists are per-user and
get re-generated on the new Mac.

### On the old Mac

```bash
# Stop everything cleanly.
make uninstall-launchd
cd docker/immich && docker compose down

# Unmount the SSD safely.
diskutil unmountDisk /Volumes/PhotoSSD
```

Physically move the SSD.

### On the new Mac

1. Install Homebrew, Docker Desktop, Python 3.12, and `uv` (see
   `docs/SETUP.md` §1).
2. Plug in the SSD; confirm it mounts as `/Volumes/PhotoSSD`.
3. Clone the repo:
   ```bash
   git clone https://github.com/kevinlighter009/home.git ~/Documents/code/home
   cd ~/Documents/code/home
   ```
4. Copy `.env` from your password manager (or recreate from `.env.example`).
   Ensure `SSD_DATA_DIR=/Volumes/PhotoSSD/home_photo_repo`.
5. Copy `docker/immich/.env` similarly (paths pointing at the SSD).
6. Bring up Immich:
   ```bash
   cd docker/immich && docker compose up -d && cd ../..
   ```
7. Bootstrap the Python side **without re-creating the DB**:
   ```bash
   make bootstrap-existing
   ```
8. Install launchd services:
   ```bash
   make install-launchd
   ```
9. On each family member's iPhone: open the Immich app → Settings → Server
   URL → update if the Mac's hostname changed.

Wall-clock: ~30–60 min depending on Docker image download speed.

---

## Provider option B: Local MLX (Apple Silicon)

The default pipeline uses Anthropic's Claude API. If you'd rather run
everything locally (zero per-call cost, full offline operation), swap in
a vision model running on your Mac via [mlx-vlm](https://github.com/Blaizzy/mlx-vlm).
The architecture supports per-stage provider selection — you can keep
Anthropic for one stage and MLX for the other, or use MLX for both.

### Automatic fallback (default behavior)

The default configuration sets MLX as primary AND configures Anthropic as
the per-call fallback (`LLM_FALLBACK_PROVIDER=anthropic` in `.env.example`).
What this means in practice:

- **MLX server up + reachable** → all classification happens locally.
- **MLX server down / not installed / model not yet downloaded** → the
  worker's `classify()` raises a transient error, the FallbackProvider
  catches it, and Anthropic handles the call. No data loss, no
  needs_review flag — just a `log.warning` line and per-call slowness.

This means a fresh install with both an `ANTHROPIC_API_KEY` and an MLX
server set up will use local inference by default. If you haven't run
`make install-mlx` yet, fallback to Anthropic is automatic; the worker
keeps running.

To **disable** fallback (strict mode — fail loudly if primary is down):

```dotenv
LLM_FALLBACK_PROVIDER=
```

To **use only Anthropic** (no MLX at all):

```dotenv
LLM_STAGE_A_PROVIDER=anthropic
LLM_STAGE_B_PROVIDER=anthropic
LLM_FALLBACK_PROVIDER=
```

The worker's startup log line will show the active chain, e.g.
`stage_a=mlx→anthropic` (fallback configured) vs `stage_a=mlx` (strict).

### Requirements

- Apple Silicon (M1 or newer)
- ≥16 GB unified memory (the default model needs ~5 GB; comfortable on 16 GB+; recommended ≥24 GB)
- ~10 GB free disk for model + cache

### Quick install

```bash
make install-mlx
```

This:
1. Installs `mlx-vlm` via the `mlx` extras group.
2. Installs the `com.homephoto.mlx` launchd service (auto-starts at login).
3. Prints next-step instructions.

Then enable MLX for one or both stages by editing `.env`:

```dotenv
LLM_STAGE_A_PROVIDER=mlx     # use MLX for is-food check
LLM_STAGE_B_PROVIDER=mlx     # use MLX for dish + cuisine
```

Then verify and restart the worker:

```bash
make smoke-mlx                                       # round-trip a synthetic image
launchctl bootout gui/$UID/com.homephoto.worker
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.worker.plist
```

The worker's startup log line will now print `stage_a=mlx` (or `stage_b=mlx`).

### Choosing a model

The MLX server hosts ONE model at a time. Stage A and Stage B both target
that single model unless you run two MLX servers on different ports (advanced).

| Use case | Model | RAM | Speed | Notes |
|---|---|---|---|---|
| **Default (balanced)** | `mlx-community/Qwen2.5-VL-7B-Instruct-4bit` | ~5 GB | Fast | What `make install-mlx` installs |
| Lighter (16 GB Mac, prefer speed) | `mlx-community/Qwen2-VL-2B-Instruct-4bit` | ~1.5 GB | Fastest | Lower quality |
| Better quality, slightly more RAM | `mlx-community/Qwen2.5-VL-7B-Instruct-6bit` | ~6 GB | Slightly slower than 4-bit | ~10% RAM overhead |
| High quality (64 GB+ Mac) | `mlx-community/Qwen2.5-VL-32B-Instruct-4bit` | ~18 GB | Slower | Production-grade vision |

To change the model:

1. Edit `launchd/com.homephoto.mlx.plist.template` — change the `--model` value.
2. Edit `.env` — set `MLX_STAGE_A_MODEL` and `MLX_STAGE_B_MODEL` to the SAME new value.
3. Re-install:

   ```bash
   uv run python -m launchd.install_launchd mlx
   ```

The first invocation after a model change triggers a one-time download
(~3–20 GB depending on model). Subsequent boots are instant.

### Different models per stage (advanced)

If you want a fast small model for Stage A and a heavier model for
Stage B, you need to run two MLX servers on two ports:

1. Add a second port (e.g., `8082`) and a second plist
   (`launchd/com.homephoto.mlx-b.plist.template`).
2. Adjust `MLX_BASE_URL_STAGE_A` / `MLX_BASE_URL_STAGE_B` — but note that
   the current code uses a single `MLX_BASE_URL`. You'd need to extend
   `Settings` and `build_provider` to accept two URLs. This is a real
   change, not just config.

For most users, the single-model default delivers good results without
the operational complexity.

### Reverting to Anthropic

```bash
# In .env:
LLM_STAGE_A_PROVIDER=anthropic
LLM_STAGE_B_PROVIDER=anthropic

# Optionally uninstall the MLX launchd service:
uv run python -m launchd.uninstall_launchd mlx

# Restart the worker:
launchctl bootout gui/$UID/com.homephoto.worker
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.worker.plist
```

### Verifying the local pipeline

After enabling MLX:

```bash
make smoke-mlx       # round-trip a synthetic image through Stage A
```

Then take a food photo with your iPhone. Within one poll cycle, the
worker should classify it without making any external API calls — you
can verify with Activity Monitor (no Anthropic-bound network traffic
during processing).

### Troubleshooting

- **`make smoke-mlx` says "server not reachable"** — the launchd service
  may still be starting. First-run loads the model from disk; that can
  take 10–30 s. Wait, then re-try. Check
  `tail ~/Library/Logs/home_photo_repo/mlx.err.log` for errors.
- **Model download stalls** — `mlx-vlm` downloads from Hugging Face on
  first run. If you're behind a corporate proxy, set `HF_ENDPOINT` or
  use `huggingface-cli login` first.
- **High thermal throttling** — the 32B model can heat a MacBook
  noticeably under sustained load. Use 7B unless you have an iMac or
  Mac Studio with active cooling.
- **`mlx-vlm` install fails on Intel Mac** — Intel is not supported.
  Stay on the Anthropic provider.

---

## Troubleshooting

### Services don't appear in `launchctl list`

```bash
ls -la ~/Library/LaunchAgents/com.homephoto.*
```
If the files are present but `launchctl list` is empty: re-run `make
install-launchd`. The script calls `launchctl bootstrap` after copying.

### Worker / dashboard exits with code 1 on startup

Check the err.log:
```bash
tail -50 ~/Library/Logs/home_photo_repo/worker.err.log
```
Common causes:
- `.env` missing or has placeholder values
- `uv` not on PATH for the launchd process (the plist sets PATH explicitly;
  if you moved uv, edit the template and re-install)
- SSD not mounted (when `SSD_DATA_DIR=/Volumes/PhotoSSD/...`)
- **`SSD_DATA_DIR` mismatch between interactive shell and launchd.** launchd
  does NOT inherit your shell's environment — only what's in `.env` and what
  the plist's `EnvironmentVariables` block defines. If you set
  `SSD_DATA_DIR` only in `~/.zshrc`, the launchd-spawned worker silently
  falls back to `$HOME/home_photo_repo_data`. Always set it in `.env`.

### Backups not running at 03:00

```bash
launchctl print gui/$UID/com.homephoto.backup
```
Look at `next run time`. If the Mac was asleep at 03:00, launchd will run
the missed job on next wake. To run manually:
```bash
launchctl kickstart -k gui/$UID/com.homephoto.backup
```

### Backup script fails with "permission denied"

The plist runs as your user, but `docker exec` needs Docker Desktop to
be running. If you log out / fast-user-switch, Docker might pause and
the backup will fail. Either:
- Stay logged in
- Or run `docker context use desktop-linux` first (rare)

### Dashboard reachable from another device

Default binds to `127.0.0.1` (localhost-only). To expose:
- Add HTTP Basic auth first (see spec §7 — not yet implemented).
- Then change `.env`: `DASHBOARD_BIND=0.0.0.0:8000`
- Restart the dashboard.

### Resetting from scratch (DESTRUCTIVE)

```bash
make uninstall-launchd
cd docker/immich && docker compose down -v && cd ../..
rm -rf $SSD_DATA_DIR/db $HOME/home_photo_repo_dev
make bootstrap
```
