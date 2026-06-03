"""Weekly food-memory digest — renders and sends a summary email via Gmail SMTP."""

from home_photo_repo.digest.renderer import render_digest
from home_photo_repo.digest.sender import send_digest

__all__ = ["render_digest", "send_digest"]
