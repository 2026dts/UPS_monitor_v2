# UPS Monitor v2 — Migration Guide
## ThingsBoard → Local PostgreSQL

---

## What changed

| | v1 (old) | v2 (this) |
|---|---|---|
| Data destination | ThingsBoard Cloud via MQTT | Local PostgreSQL |
| Dashboard | ThingsBoard widgets | Custom Flask + Chart.js |
| Alarm emails | ThingsBoard rule-chain | Python alarm engine (SMTP) |
| Dependencies | `paho-mqtt` | `psycopg2-binary` |
| Files removed | `mqtt_client.py` | — |
| Files added | — | `db_store.py`, `alarm_engine.py`, `db/schema.sql` |

**Field wiring, USR-W630, parsers, battery estimator — all unchanged.**

---

## Step 1 — Install PostgreSQL on your Windows machine (local dev)

Download and install **PostgreSQL 16** from https://www.postgresql.org/download/windows/

During install, set the password for the `postgres` super-user (remember it).

After install, open **pgAdmin** or **psql** and run:

```sql
CREATE USER ups_user WITH PASSWORD 'ups_password';
CREATE DATABASE ups_monitor OWNER ups_user;
```

Then run the schema:
```bash
psql -U ups_user -d ups_monitor -f db/schema.sql
```

---

## Step 2 — Install Python dependencies

```bash
# In your project folder:
pip install -r requirements.txt
```

> `psycopg2-binary` bundles the Postgres C library — no separate driver needed on Windows.

---

## Step 3 — Configure environment variables

Edit `config.py` **or** set environment variables before running:

```bash
# Database (must match what you created in Step 1)
set DB_HOST=localhost
set DB_NAME=ups_monitor
set DB_USER=ups_user
set DB_PASSWORD=ups_password

# Email — your company SMTP server
set SMTP_HOST=smtp.yourdomain.com
set SMTP_PORT=587
set SMTP_USER=alerts@yourdomain.com
set SMTP_PASSWORD=yourpassword
set SMTP_FROM=UPS Monitor <alerts@yourdomain.com>
set ALERT_RECIPIENTS=engineer@yourdomain.com
```

---

## Step 4 — Run

```bash
python main.py
```

Dashboard opens at: **http://localhost:5000**

---

## Step 5 — Docker Compose (production / on-premise server)

```bash
# Edit docker-compose.yml — fill in SMTP_PASSWORD and ALERT_RECIPIENTS
docker-compose up -d
```

This starts:
- `ups-postgres` — PostgreSQL 16 container (data persists in `postgres_data` volume)
- `ups-monitor` — the Python application

Dashboard: **http://<server-ip>:5000**

---

## Email alert behaviour

- **Utility Fail**: email sent when mains fails, another sent when it restores
- **De-duplication**: only one email per alarm *episode* (not one per poll cycle)
- **Clear notification**: a green "Resolved" email is sent when the alarm clears
- SMTP uses STARTTLS on port 587 by default (set `SMTP_USE_TLS=false` for plain SMTP)

---

## Dashboard routes

| URL | View |
|---|---|
| `/` | All UPS units overview |
| `/server` | Server UPS detail + history charts |
| `/workstation` | Workstation UPS detail + history charts |
| `/command_centre` | Command Centre UPS detail + history charts |
| `/ups/<id>` | Any unit by id (ups1, ups2, ups3) |
| `/api/status` | JSON: live state |
| `/api/alarms` | JSON: open alarms |
| `/api/history/<id>?hours=24` | JSON: telemetry history for charts |

---

## Database tables

| Table | Purpose |
|---|---|
| `assets` | One row per UPS unit |
| `telemetry` | Every Q1 poll reading (time-series) |
| `alarms` | Alarm open/close episodes |
| `connection_events` | TCP connect/disconnect log |

---

## Adding more alarm types later

Open `alarm_engine.py` and uncomment lines in `ALARM_RULES`:

```python
ALARM_RULES = [
    ("utility_fail", "Utility / Mains Fail", "critical"),
    ("battery_low",  "Battery Low",           "critical"),   # ← uncomment
    ("ups_failed",   "UPS Hardware Fault",    "critical"),   # ← uncomment
]
```

Each alarm type must match a boolean column in the `telemetry` table.

---

## Removing ThingsBoard

You can now safely:
1. Stop sending data to ThingsBoard (it's already not happening in v2)
2. Cancel your ThingsBoard subscription if not needed for anything else
3. Delete `mqtt_client.py` from any old copies (it's not in v2)
