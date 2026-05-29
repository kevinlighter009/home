# Plan 5 Follow-ups (from final review)

Plan 5 shipped — the project is feature-complete. Final reviewer flagged
items worth folding into future maintenance work.

## Important

### 1. launchd doesn't inherit interactive shell env
`launchd/com.homephoto.worker.plist.template` and `dashboard.plist.template`
hard-code `PATH` but no other env vars. The worker reads its own `.env`,
so any setting *defined in `.env`* works. But if `SSD_DATA_DIR` is only
set in `~/.zshrc` (and the user's `.env` has the default placeholder),
the launchd-started worker silently falls back to
`$HOME/home_photo_repo_data` — different from interactive runs.

**Fix shape:** add a one-line note in operations.md's troubleshooting
section. Optionally, have `install_launchd.py` verify `.env` contains
non-default values for `SSD_DATA_DIR` before installing.

### 2. `eval` in `scripts/backup_postgres.sh`
The `run()` helper uses `eval` on shell-quoted strings (line 30). All
interpolated values currently come from env vars the operator controls,
so it's safe today. A future change that adds a user-supplied parameter
to the command would risk injection.

**Fix shape:** add a comment marking `run()` as trusted-input-only, OR
refactor to use arrays + `"${cmd[@]}"` instead of `eval`.

## Minor

3. **`make logs` shows "no files to tail"** on a brand-new install
   until the worker writes its first log line. Cosmetic.
4. **Restore runbook bypasses `make uninstall-launchd`** in
   operations.md:99 (uses `launchctl bootout` directly). Inconsistent
   with the install side. Pick one.
5. **MLX plist hard-codes the model name.** Swapping models requires
   editing the template + reinstalling. Acceptable default; worth
   noting in operations.md MLX section.
6. **`launchctl print` "next run time" wording** in troubleshooting
   (operations.md:255) varies across macOS releases. Not parsed
   programmatically, so harmless.
7. **`uninstall_launchd._SERVICES` includes `mlx`** but
   `install_launchd._SERVICES` doesn't. Intentional asymmetry (uninstall
   is conservative); but worth a comment explaining why.

## Project-wide follow-ups (cross-plan, not just Plan 5)

These accumulated across all five follow-up docs:

- **Plan 2 #1:** Stage B doesn't see Google Places candidates (spec §4.3
  intends LLM venue tiebreaker). Most consequential outstanding item —
  warrants its own mini-plan.
- **Plan 1 #1 + Plan 2 #1:** worker's `run_once` catch-up loop terminates
  on first per-asset failure. Acceptable for home use; doc tightening
  worth doing.
- **HTTP Basic auth** for dashboard if anyone wants LAN access (spec §7
  explicitly defers).
- **Stage B venue/dish prompt versioning** is recorded in DB (Plan 3
  Task 1) but no migration tool re-runs on stale rows.

## Decision

These are the kind of polish items that accumulate naturally in a
personal project. Address as needed:
- Item #1 should land in a 1-line doc patch when convenient
- Item #2 deserves attention before any backup-script change that takes
  user input
- The rest are "fix when it bites you"
