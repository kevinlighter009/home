"""Send the weekly digest via Gmail SMTP (TLS on port 587)."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_digest(
    *,
    from_email: str,
    app_password: str,
    to_emails: list[str],
    subject: str,
    html_body: str,
    plain_body: str,
) -> None:
    """Send one digest email to all recipients.

    Raises:
        smtplib.SMTPException: on delivery failure (caller decides whether to retry).
    """
    if not to_emails:
        raise ValueError("to_emails is empty — nothing to send")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_emails)

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(from_email, app_password)
        smtp.sendmail(from_email, to_emails, msg.as_string())
