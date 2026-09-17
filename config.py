"""
Configuration for UPS Monitoring Platform v2.
ThingsBoard removed — data goes directly to PostgreSQL.
All secrets can be overridden with environment variables.
"""

import os

# =============================================================
# UPS UNITS  (same as before — USR-W630 TCP endpoints)
# =============================================================

UPS_UNITS = [
    {
        "id": "ups1",
        "device_name": "Server",
        "ip": os.environ.get("UPS1_IP", "10.10.10.75"),
        "port": int(os.environ.get("UPS1_PORT", "8899")),
        "protocol": "legacy_megatec",
        "battery_voltage_empty": 168.0,
        "battery_voltage_full": 218.0,
        "reference_runtime_at_full_load_minutes": 8,
    },
    {
        "id": "ups2",
        "device_name": "Workstation",
        "ip": os.environ.get("UPS2_IP", "10.10.10.74"),
        "port": int(os.environ.get("UPS2_PORT", "8899")),
        "protocol": "legacy_megatec",
        "battery_voltage_empty": 168.0,
        "battery_voltage_full": 218.0,
        "reference_runtime_at_full_load_minutes": 12,
    },
    {
        "id": "ups3",
        "device_name": "UPS-Command Centre",
        "ip": os.environ.get("UPS3_IP", "10.10.10.76"),
        "port": int(os.environ.get("UPS3_PORT", "8899")),
        "protocol": "microtex_10kva",
        "battery_voltage_empty": 168.0,
        "battery_voltage_full": 218.0,
        "reference_runtime_at_full_load_minutes": 12,
    },
]

# =============================================================
# POLL SETTINGS
# =============================================================

TCP_TIMEOUT     = int(os.environ.get("TCP_TIMEOUT", "5"))
POLL_INTERVAL   = int(os.environ.get("POLL_INTERVAL", "3"))

# =============================================================
# WEB SERVER
# =============================================================

WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("WEB_PORT", "5000"))

# =============================================================
# POSTGRESQL  (replaces ThingsBoard)
# =============================================================

DB_HOST     = os.environ.get("DB_HOST", "localhost")
DB_PORT     = int(os.environ.get("DB_PORT", "5432"))
DB_NAME     = os.environ.get("DB_NAME", "ups_monitor")
DB_USER     = os.environ.get("DB_USER", "ups_user")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "ups_password")

# Connection string for psycopg2 / SQLAlchemy
DB_DSN = (
    f"host={DB_HOST} port={DB_PORT} "
    f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}"
)

# How many rows to batch-insert before committing (reduces DB round-trips)
DB_BATCH_SIZE = int(os.environ.get("DB_BATCH_SIZE", "1"))

# =============================================================
# EMAIL / SMTP NOTIFICATIONS  (company SMTP server)
# =============================================================

SMTP_HOST       = os.environ.get("SMTP_HOST", "smtp.yourdomain.com")
SMTP_PORT       = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER       = os.environ.get("SMTP_USER", "alerts@yourdomain.com")
SMTP_PASSWORD   = os.environ.get("SMTP_PASSWORD", "")
SMTP_USE_TLS    = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
SMTP_FROM       = os.environ.get("SMTP_FROM", "UPS Monitor <alerts@yourdomain.com>")

# Comma-separated list of recipient emails
ALERT_RECIPIENTS = [
    e.strip()
    for e in os.environ.get(
        "ALERT_RECIPIENTS", "engineer@yourdomain.com"
    ).split(",")
    if e.strip()
]

# Minimum seconds between repeat emails for the SAME open alarm
# (prevents flooding if a UPS keeps flapping)
ALARM_EMAIL_COOLDOWN_SECONDS = int(
    os.environ.get("ALARM_EMAIL_COOLDOWN_SECONDS", "300")   # 5 minutes
)

# =============================================================
# PC / LAPTOP SPEAKER AUDIO ALARM
# =============================================================

# Enable audible alarm sound via Windows PC/laptop speaker
ENABLE_PC_SPEAKER_ALARM = os.environ.get("ENABLE_PC_SPEAKER_ALARM", "true").lower() == "true"

# Sound style options:
#   "chime"   -> pleasant Windows chime (C:\Windows\Media\chimes.wav)
#   "alarm"   -> Windows alarm sound   (C:\Windows\Media\Alarm01.wav)
#   "notify"  -> notification sound    (C:\Windows\Media\notify.wav)
#   "ding"    -> short ding            (C:\Windows\Media\ding.wav)
#   "ring"    -> phone ring            (C:\Windows\Media\Ring01.wav)
#   "beep"    -> synthetic frequency beep
#   Or specify any full path to a custom .wav file: r"C:\path\to\my_sound.wav"
SOUND_STYLE = os.environ.get("SOUND_STYLE", "beep")

# Fallback beep settings (used if SOUND_STYLE = "beep")
PC_SPEAKER_BEEP_FREQ = int(os.environ.get("PC_SPEAKER_BEEP_FREQ", "1000"))
PC_SPEAKER_BEEP_MS   = int(os.environ.get("PC_SPEAKER_BEEP_MS", "400"))


