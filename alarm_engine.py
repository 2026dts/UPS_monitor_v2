"""
Alarm engine + email notification service.

For Phase 1 (as requested): utility_fail is the only alarm that
sends email. The engine is structured so adding more alarm types
later (battery_low, ups_failed, etc.) is a one-line addition.

Email is sent via the company SMTP server configured in config.py.
De-duplication: one email when the alarm OPENS, one when it CLEARS.
A cooldown period prevents re-sending while the alarm stays open.
"""

import logging
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config
import db_store

logger = logging.getLogger(__name__)


# =============================================================
# ALARM RULE TABLE
# =============================================================
# Each entry: (alarm_type, human_label, severity)
# Add new alarm types here — the engine loops over this list
# on every poll and evaluates whether the condition is active.

ALARM_RULES = [
    ("utility_fail", "Utility / Mains Fail",  "critical"),
    # Uncomment to enable additional alarms in future phases:
    # ("battery_low",  "Battery Low",            "critical"),
    # ("ups_failed",   "UPS Hardware Fault",     "critical"),
]


# =============================================================
# EVALUATE ALARMS  (called by the worker after each Q1 poll)
# =============================================================

def evaluate(ups_id: str, device_name: str, parsed: dict):
    """
    Check every alarm rule against the latest parsed Q1 reading.
    Opens / clears alarm records in Postgres and triggers email as needed.
    """
    for alarm_type, label, severity in ALARM_RULES:
        is_active = bool(parsed.get(alarm_type, False))

        if is_active:
            _handle_active(ups_id, device_name, alarm_type, label, severity, parsed)
        else:
            _handle_clear(ups_id, device_name, alarm_type, label)


def _handle_active(ups_id, device_name, alarm_type, label, severity, parsed):
    """Open alarm if not already open; send email if not already sent."""
    alarm_id = db_store.open_alarm(
        ups_id, alarm_type, severity,
        extra={"overall_status": parsed.get("overall_status"),
               "input_voltage": parsed.get("input_voltage"),
               "battery_pct": parsed.get("battery_percentage")}
    )

    if alarm_id is not None:
        # Brand new alarm — send email immediately
        _send_alarm_email(alarm_id, ups_id, device_name, alarm_type, label,
                          severity, parsed, is_clear=False)


def _handle_clear(ups_id, device_name, alarm_type, label):
    """Check if alarm was open and clear it; send a clear notification."""
    # Peek at open alarms first to decide whether we need a clear email
    open_list = db_store.get_open_alarms()
    was_open = any(
        a["ups_id"] == ups_id and a["alarm_type"] == alarm_type
        for a in open_list
    )

    db_store.clear_alarm(ups_id, alarm_type)

    if was_open:
        _send_clear_email(ups_id, device_name, alarm_type, label)


# =============================================================
# EMAIL HELPERS
# =============================================================

def _send_alarm_email(alarm_id, ups_id, device_name, alarm_type, label,
                      severity, parsed, is_clear=False):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    subject = f"🔴 ALARM | {device_name} — {label}"

    input_v  = parsed.get("input_voltage", "N/A")
    output_v = parsed.get("output_voltage", "N/A")
    batt_pct = parsed.get("battery_percentage", "N/A")
    batt_pct_str = f"{batt_pct}%" if batt_pct is not None else "N/A"
    backup   = parsed.get("estimated_backup_minutes", "N/A")
    backup_str = f"{backup} min" if backup is not None else "N/A"
    status   = parsed.get("overall_status", "N/A")

    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:20px;">
  <div style="max-width:560px; margin:0 auto;">

    <div style="background:#1e293b; border-radius:12px; overflow:hidden; border:1px solid #334155;">

      <!-- Header -->
      <div style="background:#dc2626; padding:20px 28px;">
        <div style="font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:#fca5a5; margin-bottom:4px;">
          UPS ALARM ALERT
        </div>
        <div style="font-size:22px; font-weight:800; color:#ffffff;">
          {label}
        </div>
      </div>

      <!-- Body -->
      <div style="padding:24px 28px;">

        <table style="width:100%; border-collapse:collapse; font-size:14px; margin-bottom:20px;">
          <tr>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#94a3b8; width:45%;">Unit</td>
            <td style="padding:8px 0; border-bottom:1px solid #334155; font-weight:700; color:#f1f5f9;">{device_name}</td>
          </tr>
          <tr>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#94a3b8;">Alarm</td>
            <td style="padding:8px 0; border-bottom:1px solid #334155; font-weight:700; color:#ef4444;">{label}</td>
          </tr>
          <tr>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#94a3b8;">Status</td>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#f59e0b;">{status}</td>
          </tr>
          <tr>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#94a3b8;">Input Voltage</td>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#f1f5f9;">{input_v} V</td>
          </tr>
          <tr>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#94a3b8;">Output Voltage</td>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#f1f5f9;">{output_v} V</td>
          </tr>
          <tr>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#94a3b8;">Battery</td>
            <td style="padding:8px 0; border-bottom:1px solid #334155; color:#f1f5f9;">{batt_pct_str}</td>
          </tr>
          <tr>
            <td style="padding:8px 0; color:#94a3b8;">Est. Backup</td>
            <td style="padding:8px 0; color:#f1f5f9;">{backup_str}</td>
          </tr>
        </table>

        <div style="background:#dc2626; border-radius:8px; padding:14px 18px; font-size:13px; color:#fee2e2; margin-bottom:20px;">
          ⚠️ <strong>Immediate Action Required:</strong> The UPS for <strong>{device_name}</strong>
          has switched to battery backup. Check mains supply and estimated runtime.
        </div>

        <div style="font-size:12px; color:#64748b;">Triggered at: {now_str}</div>
      </div>
    </div>

  </div>
</body>
</html>
"""

    plain_body = (
        f"UPS ALARM: {label}\n"
        f"Unit       : {device_name}\n"
        f"Status     : {status}\n"
        f"Input V    : {input_v} V\n"
        f"Output V   : {output_v} V\n"
        f"Battery    : {batt_pct_str}\n"
        f"Est. Backup: {backup_str}\n"
        f"Time       : {now_str}\n"
    )

    sent = _send(subject, html_body, plain_body)
    if sent and alarm_id:
        db_store.mark_alarm_notified(alarm_id)


def _send_clear_email(ups_id, device_name, alarm_type, label):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = f"✅ RESOLVED | {device_name} — {label}"

    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:20px;">
  <div style="max-width:560px; margin:0 auto;">
    <div style="background:#1e293b; border-radius:12px; overflow:hidden; border:1px solid #334155;">
      <div style="background:#059669; padding:20px 28px;">
        <div style="font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:#a7f3d0; margin-bottom:4px;">
          UPS ALARM RESOLVED
        </div>
        <div style="font-size:22px; font-weight:800; color:#ffffff;">
          {label} — Cleared
        </div>
      </div>
      <div style="padding:24px 28px;">
        <p style="font-size:15px; color:#e2e8f0; margin-bottom:20px;">
          The alarm <strong>{label}</strong> for <strong>{device_name}</strong>
          has been automatically cleared. The UPS has returned to normal operation.
        </p>
        <div style="font-size:12px; color:#64748b;">Resolved at: {now_str}</div>
      </div>
    </div>
  </div>
</body>
</html>
"""

    plain_body = (
        f"RESOLVED: {label}\n"
        f"Unit: {device_name}\n"
        f"Time: {now_str}\n"
        "The UPS has returned to normal operation.\n"
    )

    _send(subject, html_body, plain_body)


def _send(subject: str, html_body: str, plain_body: str) -> bool:
    """
    Send an email via the company SMTP server.
    Returns True if sent successfully, False on failure.
    """
    if not config.ALERT_RECIPIENTS:
        logger.warning("[EMAIL] No recipients configured — skipping")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = config.SMTP_FROM
    msg["To"]      = ", ".join(config.ALERT_RECIPIENTS)

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if config.SMTP_USE_TLS:
            context = ssl.create_default_context()
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                if config.SMTP_USER and config.SMTP_PASSWORD:
                    smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
                smtp.sendmail(config.SMTP_FROM, config.ALERT_RECIPIENTS, msg.as_string())
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as smtp:
                smtp.ehlo()
                if config.SMTP_USER and config.SMTP_PASSWORD:
                    smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
                smtp.sendmail(config.SMTP_FROM, config.ALERT_RECIPIENTS, msg.as_string())

        logger.info("[EMAIL] Sent '%s' to %s", subject, config.ALERT_RECIPIENTS)
        return True

    except Exception as exc:
        logger.error("[EMAIL] Failed to send '%s': %s", subject, exc)
        return False
