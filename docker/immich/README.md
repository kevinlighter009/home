# Immich (Docker Compose)

This directory contains the Immich service configuration. Immich runs
independently from the `home_photo_repo` Python code.

## First-time setup

1. Format the external SSD as **APFS** (Mac-only) and create the target dirs:
   ```bash
   mkdir -p /Volumes/PhotoSSD/immich/{library,pgdata,backups}
   ```
2. Exclude `pgdata/` from Spotlight and Time Machine:
   ```bash
   mdutil -i off /Volumes/PhotoSSD
   ```
   System Settings → Time Machine → Options → add `/Volumes/PhotoSSD`.
3. Copy this directory's `.env.example` to `.env` and edit the paths and
   `DB_PASSWORD`.
4. Bring it up:
   ```bash
   cd docker/immich
   docker compose up -d
   ```
5. Visit http://localhost:2283 in a browser, create the admin account, then
   create per-family-member user accounts.
6. In Immich UI → Account → API Keys, generate one for `home_photo_repo` and
   put it in the top-level `home_photo_repo/.env` as `IMMICH_API_KEY`.
7. On each family member's iPhone: install the **Immich** app from the App
   Store, point at `http://<your-mac-hostname>.local:2283`, sign in, enable
   "Backup" → "Foreground" and "Background" with WiFi-only.

## Safe shutdown

Always stop Immich cleanly before unplugging the SSD:
```bash
cd docker/immich && docker compose down
```
