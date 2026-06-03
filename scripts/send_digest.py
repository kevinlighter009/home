"""Weekly digest sender.

Reads config from .env, renders an HTML email from the local SQLite database,
and sends it via Gmail SMTP.

Run with:
    make digest

Or invoke directly:
    python scripts/send_digest.py [--dry-run]

Flags:
    --dry-run   Print the email to stdout instead of sending.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Send weekly food-memory digest")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the email instead of sending it")
    args = parser.parse_args()

    # Import here so we get a clean error if the package isn't installed
    from home_photo_repo.config import Settings
    from home_photo_repo.digest.renderer import render_digest
    from home_photo_repo.digest.sender import send_digest

    settings = Settings()

    if not args.dry_run and not settings.digest_enabled:
        print("Digest is disabled (DIGEST_ENABLED=false). Pass --dry-run to preview.", file=sys.stderr)
        return 1

    db_path = str(settings.db_path)
    if not os.path.exists(db_path):
        print(f"ERROR: database not found at {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        subject, html_body, plain_body = render_digest(conn)
    finally:
        conn.close()

    if args.dry_run:
        print(f"Subject: {subject}")
        print("=" * 60)
        print(plain_body)
        print("=" * 60)
        print("[HTML body omitted; use --dry-run with a browser to preview]")
        return 0

    # Validate email config
    from_email = settings.digest_from_email.strip()
    app_password = settings.digest_app_password.get_secret_value().strip()
    to_emails = [e.strip() for e in settings.digest_to_emails.split(",") if e.strip()]

    if not from_email:
        print("ERROR: DIGEST_FROM_EMAIL is not set.", file=sys.stderr)
        return 1
    if not app_password:
        print("ERROR: DIGEST_APP_PASSWORD is not set.", file=sys.stderr)
        return 1
    if not to_emails:
        print("ERROR: DIGEST_TO_EMAILS is empty.", file=sys.stderr)
        return 1

    try:
        send_digest(
            from_email=from_email,
            app_password=app_password,
            to_emails=to_emails,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
        )
        print(f"Digest sent to {', '.join(to_emails)}: {subject}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR sending digest: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
