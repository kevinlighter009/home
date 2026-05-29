# Operations Guide

Day-2 operations for `home_photo_repo`: launchd auto-start, backups,
migration to a new Mac, optional MLX setup, and troubleshooting.

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
To opt in:

```bash
uv run python -m launchd.install_launchd mlx
```

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

## Optional: MLX vision server

If you want a local fallback for Stage A and/or Stage B (zero per-call
API cost), enable MLX:

### Install mlx-vlm

```bash
uv add mlx-vlm  # or pip install mlx-vlm
```

### Smoke test the server manually

```bash
uv run mlx_vlm.server --model mlx-community/Qwen2-VL-2B-Instruct-4bit --port 8081
```

(In another terminal, verify with `curl http://localhost:8081/v1/models`.)

### Install the MLX launchd service

```bash
uv run python -m launchd.install_launchd mlx
```

> **Note:** the MLX plist template hardcodes the model name
> `mlx-community/Qwen2-VL-2B-Instruct-4bit`. To switch models, edit
> `launchd/com.homephoto.mlx.plist.template`, then re-run
> `uv run python -m launchd.install_launchd mlx`.

### Switch the pipeline to MLX

Edit `.env`:

```dotenv
LLM_STAGE_A_PROVIDER=mlx
# Or both stages:
LLM_STAGE_B_PROVIDER=mlx
```

Restart the worker:

```bash
launchctl bootout gui/$UID/com.homephoto.worker
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.homephoto.worker.plist
```

The worker startup log should now print `stage_a=mlx` or `stage_b=mlx`.

To revert: change `.env` back to `anthropic` and restart the worker.

### Uninstall MLX

```bash
uv run python -m launchd.uninstall_launchd mlx
```

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
