# Skipped tests — reminder to re-run later

Captured 2026-05-29 at user request. Re-run after the MLX-default-with-fallback
feature (Plan 8) is in production.

## 1. Plan 3.2 — Google Places API key + fallback

**Why skipped:** user doesn't have a Google Cloud Places API key set up yet.

**What to test when ready:**
- Enable `Places API (New)` in Google Cloud Console; create + IP-restrict an API key
- Set `GOOGLE_PLACES_API_KEY=AIza...` in `~/Documents/code/home/.env`
- Verify: `cd ~/Documents/code/home && make smoke-places`
  - Expected: 5+ real restaurants listed near the default SF Ferry Building coords
- Restart the worker; startup log should say `google_places=enabled`
- Take a food photo near a known restaurant; verify within one poll cycle:
  ```bash
  sqlite3 /Users/kailiangchen/Documents/app/db/app.sqlite \
    "SELECT place_match_source, place_id FROM photo_analysis \
     ORDER BY venue_resolved_at DESC LIMIT 1;"
  ```
  Expected: `place_match_source=google_places`, `place_id=gplaces:...`
- Repeat photo at same location should resolve locally (no second API call)

This also enables Plan 6.6 (venue disambiguator end-to-end), which requires
2+ Google candidates within the ambiguity threshold.

## 2. Plan 5 — launchd autostart + crash recovery

**Why skipped:** user prefers to run the worker/dashboard in the foreground
during testing.

**What to test when ready:**
- `cd ~/Documents/code/home && make install-launchd`
- `launchctl list | grep com.homephoto` should show 3 services (worker, dashboard, backup)
- Test crash recovery: `launchctl kill SIGTERM gui/$UID/com.homephoto.worker`
  then `launchctl list | grep com.homephoto.worker` — PID should have changed
- Test reboot survival: reboot the Mac, then `curl http://127.0.0.1:8000/healthz`
  should return `{"status":"ok"}` without any terminal commands
- Verify the nightly backup job: `launchctl print gui/$UID/com.homephoto.backup`
  and look for "next run time"
- Optionally trigger a manual backup: `BACKUP_DIR=/Users/kailiangchen/Documents/immich/backups \
  scripts/backup_postgres.sh`
- To uninstall: `make uninstall-launchd`
