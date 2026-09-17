"""
Flask web application — UPS Monitoring Platform v2.

Routes:
  GET /              → Main dashboard (all UPS units)
  GET /ups/<id>      → Single UPS detail view
  GET /server        → Shortcut to UPS-1
  GET /workstation   → Shortcut to UPS-2
  GET /command_centre→ Shortcut to UPS-3

  GET /api/status           → JSON: live state for all units
  GET /api/history/<ups_id> → JSON: last N hours of telemetry (for charts)
  GET /api/alarms           → JSON: currently open alarms
"""

import json
from datetime import datetime

from flask import Flask, jsonify, request

import state
import db_store
from config import UPS_UNITS

app = Flask(__name__)


# =============================================================
# API ENDPOINTS
# =============================================================

@app.route("/api/status")
def api_status():
    with state.state_lock:
        ups_payload = {}
        for unit in UPS_UNITS:
            uid = unit["id"]
            s = state.ups_state[uid]
            ups_payload[uid] = {
                "connected":   s["connected"],
                "error":       s["error"],
                "ups":         s["ups"],
                "latency_ms":  s["latency_ms"],
                "last_update": s["last_update"],
                "last_attempt":s["last_attempt"],
                "ups_info":    state.ups_info[uid],
                "ups_rating":  state.ups_rating[uid],
                "usr":         {"ip": unit["ip"], "port": unit["port"]},
                "device_name": unit.get("device_name", uid),
            }
        data = {
            **ups_payload,
            "serial":   {"baudrate": 2400, "data_bits": 8, "parity": "None", "stop_bits": 1},
            "protocol": {"name": "Megatec Q1"},
        }
    return jsonify(data)


@app.route("/api/history/<ups_id>")
def api_history(ups_id):
    """Return last N hours of telemetry rows for charting."""
    try:
        hours = int(request.args.get("hours", 24))
        hours = max(1, min(hours, 720))   # clamp 1 h → 30 days
    except ValueError:
        hours = 24

    rows = db_store.get_history(ups_id, hours)
    return jsonify({"ups_id": ups_id, "hours": hours, "rows": rows})


@app.route("/api/alarms")
def api_alarms():
    alarms = db_store.get_open_alarms()
    # Convert datetime objects to strings for JSON
    for a in alarms:
        for k, v in a.items():
            if isinstance(v, datetime):
                a[k] = v.isoformat()
    return jsonify(alarms)


# =============================================================
# PAGE ROUTES
# =============================================================

@app.route("/")
def dashboard():
    return DASHBOARD_HTML

@app.route("/ups/<ups_id>")
def single_ups(ups_id):
    unit = next((u for u in UPS_UNITS if u["id"] == ups_id), None)
    if not unit:
        return "UPS unit not found", 404
    return _render_single(unit)

@app.route("/server")
def server_only():
    unit = next((u for u in UPS_UNITS if u["id"] == "ups1"), UPS_UNITS[0])
    return _render_single(unit)

@app.route("/workstation")
def workstation_only():
    unit = next((u for u in UPS_UNITS if u["id"] == "ups2"),
                UPS_UNITS[1] if len(UPS_UNITS) > 1 else UPS_UNITS[0])
    return _render_single(unit)

@app.route("/command_centre")
@app.route("/command-centre")
def command_centre_only():
    unit = next((u for u in UPS_UNITS if u["id"] == "ups3"),
                UPS_UNITS[2] if len(UPS_UNITS) > 2 else UPS_UNITS[0])
    return _render_single(unit)

def _render_single(unit):
    return (SINGLE_UPS_HTML
            .replace("__UPS_ID__", unit["id"])
            .replace("__UPS_TITLE__", f"{unit['device_name']} UPS")
            .replace("__UPS_IP__", f"{unit['ip']}:{unit['port']}"))


# =============================================================
# DASHBOARD HTML  — Main (all units overview)
# =============================================================

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UPS Command Center</title>
<style>
/* ── Design tokens ────────────────────────────────────────── */
:root {
  --bg:        #eef2f9;
  --surface:   #ffffff;
  --card:      #f6f8fc;
  --card2:     #eaeff7;
  --border:    #e3e8f2;
  --border2:   #d3dbe9;
  --text:      #101826;
  --text2:     #56617a;
  --text3:     #94a0b8;
  --green:     #0ea652;
  --green-dim: #dcfce7;
  --red:       #e11d3c;
  --red-dim:   #fde2e5;
  --amber:     #d97706;
  --amber-dim: #fef3c7;
  --blue:      #2563eb;
  --cyan:      #0891b2;
  --purple:    #7c3aed;
  --radius:    16px;
  --radius-sm: 10px;
  --shadow:    0 2px 10px rgba(30,41,80,.06), 0 10px 30px rgba(30,41,80,.06);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:var(--bg);color:var(--text);min-height:100vh;line-height:1.5}

/* ── Header ──────────────────────────────────────────────── */
.hdr{background:var(--surface);border-bottom:1px solid var(--border);
     padding:14px 28px;position:sticky;top:0;z-index:200;
     display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.hdr-brand{display:flex;align-items:center;gap:14px}
.hdr-logo{width:36px;height:36px;border-radius:10px;
          background:linear-gradient(135deg,#1d4ed8,#7c3aed);
          display:flex;align-items:center;justify-content:center;
          font-size:18px;flex-shrink:0}
.hdr-title{font-size:17px;font-weight:800;letter-spacing:-.3px}
.hdr-sub{font-size:12px;color:var(--text3);margin-top:1px}
.hdr-nav{display:flex;gap:6px;flex-wrap:wrap}
.nav-btn{padding:6px 14px;border-radius:20px;font-size:12px;font-weight:600;
         border:1px solid var(--border);background:var(--card);color:var(--text2);
         text-decoration:none;transition:all .18s}
.nav-btn:hover,.nav-btn.active{background:var(--blue);border-color:var(--blue);color:#fff}
.hdr-right{display:flex;align-items:center;gap:18px}
.clock{font-size:13px;color:var(--text2);font-variant-numeric:tabular-nums;font-weight:500}

/* ── Alert Banner ────────────────────────────────────────── */
#alertBanner{display:none;background:#fef1f2;
             padding:10px 28px;border-bottom:1px solid #fecdd3;
             font-size:13px;font-weight:700;color:#be123c;
             display:none;align-items:center;gap:10px}
#alertBanner.visible{display:flex}
.alert-pulse{width:10px;height:10px;border-radius:50%;background:#ef4444;
             animation:pulse 1.2s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.85)}}

/* ── Main grid ───────────────────────────────────────────── */
.main{max-width:1520px;margin:0 auto;padding:24px 28px}

/* System summary strip */
.summary-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
               gap:12px;margin-bottom:24px}
.sum-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);
          padding:16px 20px;display:flex;flex-direction:column;gap:4px}
.sum-card .lbl{font-size:11px;font-weight:700;text-transform:uppercase;
               letter-spacing:1px;color:var(--text3)}
.sum-card .val{font-size:26px;font-weight:800;font-variant-numeric:tabular-nums}
.sum-card .sub{font-size:12px;color:var(--text2)}

/* UPS panels */
.panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));gap:20px}
@media(max-width:900px){.panels{grid-template-columns:1fr}}

/* ── UPS Panel ───────────────────────────────────────────── */
.panel{background:var(--surface);border:1px solid var(--border);
       border-radius:var(--radius);overflow:hidden;box-shadow:var(--shadow);
       display:flex;flex-direction:column;transition:border-color .25s}
.panel.alarm{border-color:var(--red)!important;box-shadow:0 0 0 1px var(--red),var(--shadow)}
.panel.warning{border-color:var(--amber)!important}

.panel-head{padding:14px 20px;display:flex;align-items:center;
            justify-content:space-between;border-bottom:1px solid var(--border)}
.ph-left{display:flex;align-items:center;gap:10px}
.ph-icon{width:32px;height:32px;border-radius:8px;
         background:linear-gradient(135deg,#1d4ed8 0%,#7c3aed 100%);
         display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0}
.ph-name{font-size:15px;font-weight:700}
.ph-ip{font-size:11px;color:var(--text3);font-family:monospace;
       background:var(--card);padding:3px 8px;border-radius:5px;border:1px solid var(--border)}
.ph-detail-btn{font-size:12px;color:var(--blue);text-decoration:none;font-weight:600;
               padding:4px 10px;border-radius:6px;background:rgba(59,130,246,.1);
               border:1px solid rgba(59,130,246,.2);transition:all .2s}
.ph-detail-btn:hover{background:var(--blue);color:#fff}

/* Connection status bar */
.conn-bar{padding:8px 20px;font-size:12px;font-weight:600;
          display:flex;align-items:center;justify-content:space-between}
.conn-bar.online{background:rgba(34,197,94,.06);color:var(--green)}
.conn-bar.offline{background:rgba(239,68,68,.06);color:var(--red)}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;margin-right:8px}
.online .dot{background:var(--green);box-shadow:0 0 7px var(--green)}
.offline .dot{background:var(--red);box-shadow:0 0 7px var(--red)}
.latency{font-size:11px;font-weight:400;color:var(--text3)}

/* Utility fail banner inside panel */
.utility-fail-bar{display:none;background:var(--red-dim);
                  padding:8px 20px;font-size:13px;font-weight:700;color:#9f1239;
                  align-items:center;gap:8px;border-bottom:1px solid var(--red)}
.utility-fail-bar.show{display:flex}

/* Panel body */
.pbody{padding:18px 20px;flex:1;display:flex;flex-direction:column;gap:16px}

.sec-lbl{font-size:10px;font-weight:800;text-transform:uppercase;
         letter-spacing:1.3px;color:var(--text3);margin-bottom:8px}

/* Metrics grid */
.metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:8px}
.metric{background:var(--card);border:1px solid var(--border);
        border-radius:var(--radius-sm);padding:12px 14px;
        transition:background .15s,border-color .15s,box-shadow .2s}
.metric:hover{background:var(--card2);border-color:var(--border2)}
.metric.alarm{border-color:var(--red)!important;background:rgba(239,68,68,.06)!important}
.metric.warning{border-color:var(--amber)!important;background:rgba(245,158,11,.05)!important}
.metric.ok{border-color:rgba(34,197,94,.2)!important}
.m-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;
        color:var(--text3);margin-bottom:5px}
.m-val{font-size:19px;font-weight:800;font-variant-numeric:tabular-nums}
.m-val.green{color:var(--green)} .m-val.red{color:var(--red)}
.m-val.amber{color:var(--amber)} .m-val.blue{color:var(--blue)}
.m-val.cyan{color:var(--cyan)}   .m-val.muted{color:var(--text2);font-size:15px}
.m-val.purple{color:var(--purple)}

/* Battery bar */
.batt-bar-wrap{margin-top:6px}
.batt-bar-track{height:5px;background:var(--card2);border-radius:4px;overflow:hidden;
                border:1px solid var(--border)}
.batt-bar-fill{height:100%;border-radius:4px;transition:width .6s ease}

/* Flags */
.flags{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:7px}
.flag{display:flex;align-items:center;gap:8px;padding:8px 11px;
      background:var(--card);border:1px solid var(--border);
      border-radius:var(--radius-sm);font-size:12px;font-weight:500;
      transition:border-color .2s,background .2s}
.flag.alarm-state{border-color:var(--red);background:rgba(239,68,68,.07)}
.flag.warn-state{border-color:var(--amber);background:rgba(245,158,11,.06)}
.fdot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.fdot.ok{background:var(--green);box-shadow:0 0 5px rgba(34,197,94,.5)}
.fdot.warn{background:var(--amber);box-shadow:0 0 5px rgba(245,158,11,.5)}
.fdot.err{background:var(--red);box-shadow:0 0 5px rgba(239,68,68,.5)}
.flbl{color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* Rating row */
.rating-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px}
.ritem{text-align:center;padding:10px 8px;background:var(--card);
       border:1px solid var(--border);border-radius:var(--radius-sm)}
.ritem .rl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--text3)}
.ritem .rv{font-size:14px;font-weight:800;margin-top:4px;color:var(--cyan)}

/* No data */
.no-data{text-align:center;padding:48px 20px;color:var(--text3)}
.no-data-icon{font-size:38px;margin-bottom:8px;opacity:.4}
.no-data-text{font-size:13px}

/* ── Footer ──────────────────────────────────────────────── */
.footer{text-align:center;padding:20px 28px;font-size:12px;color:var(--text3);
        border-top:1px solid var(--border);margin-top:32px}

/* ── Icons & light-mode polish ───────────────────────────── */
.hdr{box-shadow:0 1px 3px rgba(16,24,38,.05)}
.hdr-logo{box-shadow:0 4px 10px rgba(37,99,235,.25)}
.ic{vertical-align:-2px;margin-right:5px;flex-shrink:0}
.sec-lbl{display:flex;align-items:center;color:var(--text3)}
.m-lbl{display:flex;align-items:center}
.flbl{display:flex;align-items:center}
.no-data-icon{color:var(--border2)}
.no-data-icon svg{display:inline-block}
.sound-btn{display:inline-flex!important;align-items:center;gap:6px}
.sound-btn.active{color:var(--blue);border-color:var(--blue);background:rgba(37,99,235,.08)}
.panel{transition:border-color .25s,box-shadow .25s}
.panel:hover{box-shadow:0 6px 22px rgba(30,41,80,.10)}
.metric{box-shadow:0 1px 2px rgba(16,24,38,.03)}
.sum-card{box-shadow:0 1px 2px rgba(16,24,38,.03)}

/* Vibrant colour chips behind every icon — "out of the box" accent set */
.ic-chip{display:inline-flex;align-items:center;justify-content:center;
         width:30px;height:30px;border-radius:9px;margin-right:7px;flex-shrink:0}
.ic-chip svg{width:18px;height:18px}
.sec-lbl .ic-chip{width:26px;height:26px;border-radius:8px;margin-right:6px}
.sec-lbl .ic-chip svg{width:16px;height:16px}
.flbl .ic-chip{width:25px;height:25px;border-radius:8px;margin-right:6px}
.flbl .ic-chip svg{width:16px;height:16px}
.c-cyan   {background:#cffafe;color:#0e7490}
.c-blue   {background:#dbeafe;color:#1d4ed8}
.c-purple {background:#f3e8ff;color:#7c3aed}
.c-pink   {background:#fce7f3;color:#db2777}
.c-orange {background:#ffedd5;color:#c2410c}
.c-green  {background:#dcfce7;color:#15803d}
.c-teal   {background:#ccfbf1;color:#0f766e}
.c-indigo {background:#e0e7ff;color:#4338ca}
.c-red    {background:#fee2e2;color:#b91c1c}
.c-amber  {background:#fef3c7;color:#b45309}
.c-violet {background:#ede9fe;color:#6d28d9}
.c-slate  {background:#e2e8f0;color:#334155}
.hdr-logo{background:linear-gradient(135deg,#2563eb 0%,#7c3aed 55%,#db2777 100%)}
.ph-icon{background:linear-gradient(135deg,#2563eb 0%,#7c3aed 100%)}
.metric.alarm .m-val{color:var(--red)}
.chart-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
             flex-direction:column;gap:8px;color:var(--text3);font-size:13px;text-align:center;
             background:var(--surface);border-radius:var(--radius-sm)}
.chart-empty svg{opacity:.35}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-brand">
    <div class="hdr-logo"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M11 1 3 12h6l-1 9 8-11H10z"/></svg></div>
    <div>
      <div class="hdr-title">UPS Command Center</div>
      <div class="hdr-sub">Megatec Q1 · Local PostgreSQL · Real-time</div>
    </div>
  </div>
  <nav class="hdr-nav">
    <a href="/" class="nav-btn active">All Units</a>
    <a href="/server" class="nav-btn">Server</a>
    <a href="/workstation" class="nav-btn">Workstation</a>
    <a href="/command_centre" class="nav-btn">Command Centre</a>
  </nav>
  <div class="hdr-right">
    <button id="audioToggleBtn" onclick="toggleAudio()" class="nav-btn sound-btn active" style="cursor:pointer" title="Toggle audio alarms"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6"/></svg><span>Sound: ON</span></button>
    <div class="clock" id="clock"></div>
  </div>
</header>

<!-- Global alert banner -->
<div id="alertBanner">
  <span class="alert-pulse"></span>
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 20h20z"/><path d="M12 10v4"/><circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none"/></svg>
  <span id="alertText">Active alarms detected</span>
</div>

<main class="main">

  <!-- Summary strip -->
  <div class="summary-strip" id="summaryStrip">
    <div class="sum-card">
      <div class="lbl">Units Online</div>
      <div class="val" id="sumOnline" style="color:var(--green)">—</div>
      <div class="sub" id="sumTotal">of — units</div>
    </div>
    <div class="sum-card">
      <div class="lbl">Utility Status</div>
      <div class="val" id="sumUtility" style="color:var(--green)">OK</div>
      <div class="sub" id="sumUtilitySub">All on mains</div>
    </div>
    <div class="sum-card">
      <div class="lbl">Open Alarms</div>
      <div class="val" id="sumAlarms" style="color:var(--green)">0</div>
      <div class="sub">active alerts</div>
    </div>
    <div class="sum-card">
      <div class="lbl">Avg Battery</div>
      <div class="val" id="sumBattery" style="color:var(--green)">—</div>
      <div class="sub">across all units</div>
    </div>
    <div class="sum-card">
      <div class="lbl">Last Updated</div>
      <div class="val" id="sumTime" style="font-size:14px;margin-top:4px;color:var(--text2)">—</div>
      <div class="sub">auto-refresh 3 s</div>
    </div>
  </div>

  <!-- UPS Panels -->
  <div class="panels" id="upsPanels"></div>

</main>

<footer class="footer">
  UPS Monitoring Platform v2 &bull; PostgreSQL backend &bull; No ThingsBoard dependency
</footer>

<script>
// ── Helpers ────────────────────────────────────────────────
function el(id){return document.getElementById(id)}
function ce(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function fmt(v,unit='',decimals=1){return v!=null?Number(v).toFixed(decimals)+unit:'—'}

function updateClock(){
  el('clock').textContent=new Date().toLocaleString('en-IN',
    {hour:'2-digit',minute:'2-digit',second:'2-digit',day:'2-digit',month:'short',year:'numeric'});
}

// ── Icon set (inline SVG, stroke=currentColor) ──────────────
const ICONS = {
  bolt:   '<path d="M11 1 3 12h6l-1 9 8-11H10z"/>',
  plug:   '<path d="M8 3v4M14 3v4M6 8h10l-1 5a4 4 0 0 1-4 3.5A4 4 0 0 1 7 13z"/><path d="M10 16.5V21"/>',
  gauge:  '<path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15l4-5"/><circle cx="12" cy="15" r="1"/>',
  wave:   '<path d="M2 12h3l2-7 4 14 3-10 2 3h4"/>',
  therm:  '<path d="M12 3a2 2 0 0 0-2 2v9.5a4 4 0 1 0 4 0V5a2 2 0 0 0-2-2z"/><circle cx="12" cy="18" r="1.6"/>',
  power:  '<path d="M12 3v7"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/>',
  battery:'<rect x="2" y="8" width="16" height="8" rx="1.5"/><path d="M20 10.5v3"/><path d="M5 8v8" stroke-opacity=".0"/>',
  cell:   '<path d="M5 3v4M9 3v4M3 7h8l-1 4a3 3 0 0 1-3 2.5A3 3 0 0 1 6 11z"/><path d="M7 13.5V17"/>',
  bank:   '<rect x="3" y="10" width="18" height="8" rx="1"/><path d="M6 10V7l6-4 6 4v3"/>',
  clock:  '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  check:  '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',
  alert:  '<path d="M12 3 2 20h20z"/><path d="M12 10v4"/><circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none"/>',
  shield: '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/>',
  bell:   '<path d="M12 3a5 5 0 0 0-5 5v3l-2 4h14l-2-4V8a5 5 0 0 0-5-5z"/><path d="M9.5 19a2.5 2.5 0 0 0 5 0"/>',
  flag:   '<circle cx="12" cy="12" r="9"/>',
  test:   '<path d="M9 2v6L4 19a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-5-11V2"/>',
  server: '<rect x="3" y="4" width="18" height="7" rx="1.5"/><rect x="3" y="13" width="18" height="7" rx="1.5"/><circle cx="7" cy="7.5" r="1" fill="currentColor" stroke="none"/><circle cx="7" cy="16.5" r="1" fill="currentColor" stroke="none"/>',
  sound:  '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6"/>',
  soundOff:'<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M17 9l4 6M21 9l-4 6"/>',
};
function svgIcon(name,size=14){
  return `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]||''}</svg>`;
}
const ICON_COLORS = {
  bolt:'cyan', plug:'blue', gauge:'purple', wave:'pink', therm:'orange', power:'slate',
  battery:'green', cell:'teal', bank:'indigo', clock:'cyan', shield:'blue', check:'green',
  alert:'red', bell:'amber', test:'violet', server:'indigo', flag:'slate',
};
function ic(name,size=13){
  const color=ICON_COLORS[name]||'slate';
  return `<span class="ic-chip c-${color}"><svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]||''}</svg></span>`;
}

// ── Metric card HTML ───────────────────────────────────────
function metricHTML(label,value,cls='',alarmCls='',icon=''){
  return `<div class="metric ${alarmCls}">
    <div class="m-lbl">${icon?ic(icon,12):''}${label}</div>
    <div class="m-val ${cls}">${value}</div>
  </div>`;
}

// ── Battery colour logic ───────────────────────────────────
function battColour(pct){
  if(pct==null)return'muted';
  if(pct>60)return'green';
  if(pct>25)return'amber';
  return'red';
}
function battBarColour(pct){
  if(pct==null)return'#94a0b8';
  if(pct>60)return'#0ea652';
  if(pct>25)return'#d97706';
  return'#e11d3c';
}

// ── Render one UPS panel body ──────────────────────────────
function renderPanelBody(bodyId, failBarId, panelEl, unitData){
  const body=el(bodyId);
  const failBar=el(failBarId);
  if(!body)return;

  if(!unitData||!unitData.ups){
    body.innerHTML=`<div class="no-data">
      <div class="no-data-icon">${svgIcon('bolt',30)}</div>
      <div class="no-data-text">${unitData&&unitData.error?unitData.error:'Waiting for first poll…'}</div>
    </div>`;
    return;
  }

  const ups=unitData.ups;
  const rating=unitData.ups_rating||{};
  const info=unitData.ups_info||{};

  // Panel-level alarm class
  if(ups.utility_fail||ups.ups_failed||ups.battery_low){
    panelEl.classList.add('alarm');panelEl.classList.remove('warning');
  } else if(ups.avr_active||(ups.output_load_pct>80)){
    panelEl.classList.add('warning');panelEl.classList.remove('alarm');
  } else {
    panelEl.classList.remove('alarm','warning');
  }

  // Utility fail banner inside panel
  if(ups.utility_fail){
    failBar.classList.add('show');
    failBar.innerHTML=svgIcon('alert',14)+'<span>UTILITY FAIL — Running on Battery</span>';
  } else {
    failBar.classList.remove('show');
  }

  const bPct=ups.battery_percentage;
  const bPctStr=bPct!=null?bPct.toFixed(1)+'%':'—';
  const bCol=battColour(bPct);
  const loadPct=ups.output_load_pct;
  const loadCls=loadPct>80?'red':loadPct>50?'amber':'green';
  const modeCls=ups.operating_mode==='Online'?'green':'amber';
  const statusCls=ups.overall_status==='OK'?'green':ups.overall_status==='ON BATTERY'?'amber':'red';

  let html='';

  // ── Electrical ────────────────────────────────────────────
  html+=`<div><div class="sec-lbl">${ic('bolt')}Electrical</div><div class="metrics">`;
  html+=metricHTML('EB Input', fmt(ups.input_voltage,'V'), 'cyan', '', 'bolt');
  html+=metricHTML('To Office', fmt(ups.output_voltage,'V'), 'blue', '', 'plug');
  html+=metricHTML('Load', loadPct!=null?loadPct+'%':'—', loadCls, loadCls==='red'?'alarm':loadCls==='amber'?'warning':'', 'gauge');
  html+=metricHTML('Frequency', fmt(ups.input_frequency,' Hz'), '', '', 'wave');
  html+=metricHTML('Temperature', fmt(ups.temperature,'°C'), ups.temperature>45?'red':'', '', 'therm');
  html+=metricHTML('Mode', ups.operating_mode||'—', modeCls, '', 'power');
  html+=`</div></div>`;

  // ── Battery ───────────────────────────────────────────────
  const bBarW=bPct!=null?Math.max(2,bPct)+'%':'0%';
  const bBarC=battBarColour(bPct);
  html+=`<div><div class="sec-lbl">${ic('battery')}Battery</div><div class="metrics">`;
  html+=`<div class="metric${bCol==='red'?' alarm':bCol==='amber'?' warning':''}">
    <div class="m-lbl">${ic('battery',12)}Charge</div>
    <div class="m-val ${bCol}">${bPctStr}</div>
    <div class="batt-bar-wrap">
      <div class="batt-bar-track">
        <div class="batt-bar-fill" style="width:${bBarW};background:${bBarC}"></div>
      </div>
    </div>
  </div>`;
  html+=metricHTML('Cell V', fmt(ups.battery_voltage,'V'), '', '', 'cell');
  html+=metricHTML('Bank V', ups.battery_bank_voltage_est!=null?fmt(ups.battery_bank_voltage_est,'V'):'N/A', '', '', 'bank');
  html+=metricHTML('Backup', ups.estimated_backup_minutes!=null?ups.estimated_backup_minutes+' min':'—', 'cyan', '', 'clock');
  html+=`</div></div>`;

  // ── Status flags ──────────────────────────────────────────
  html+=`<div><div class="sec-lbl">${ic('shield')}Status & Flags</div><div class="flags">`;
  const flag=(lbl,txt,state,alarmCls='',icon='flag')=>`<div class="flag ${alarmCls}">
    <span class="fdot ${state}"></span>
    <span class="flbl">${ic(icon,12)}${lbl}: <strong>${txt}</strong></span>
  </div>`;

  html+=flag('Status', ups.overall_status||'—',
    statusCls==='green'?'ok':statusCls==='amber'?'warn':'err',
    statusCls==='red'?'alarm-state':statusCls==='amber'?'warn-state':'', 'check');
  html+=flag('Utility', ups.utility_fail?'FAIL':'OK',
    ups.utility_fail?'err':'ok', ups.utility_fail?'alarm-state':'', 'plug');
  html+=flag('Battery', ups.battery_low?'LOW':'OK',
    ups.battery_low?'err':'ok', ups.battery_low?'alarm-state':'', 'battery');
  html+=flag('AVR', ups.avr_active?'ACTIVE':'OFF',
    ups.avr_active?'warn':'ok', ups.avr_active?'warn-state':'', 'shield');
  html+=flag('UPS Fault', ups.ups_failed?'FAULT':'OK',
    ups.ups_failed?'err':'ok', ups.ups_failed?'alarm-state':'', 'alert');
  html+=flag('Beeper', ups.beeper_sounding?'SOUNDING':(ups.beeper_on?'ARMED':'OFF'),
    ups.beeper_sounding?'err':ups.beeper_on?'warn':'ok',
    ups.beeper_sounding?'alarm-state':ups.beeper_on?'warn-state':'', 'bell');
  html+=flag('Shutdown', ups.shutdown_active?'ACTIVE':'OFF',
    ups.shutdown_active?'err':'ok', ups.shutdown_active?'alarm-state':'', 'power');
  html+=flag('Test', ups.test_in_progress?'RUNNING':'OFF',
    ups.test_in_progress?'warn':'ok', ups.test_in_progress?'warn-state':'', 'test');
  html+=`</div></div>`;

  // ── Rating / identity ─────────────────────────────────────
  const hasRating=rating&&(rating.rated_voltage||rating.rated_current);
  const hasInfo=info&&info.model&&info.model!=='Not reported by UPS';
  if(hasRating||hasInfo){
    html+=`<div><div class="sec-lbl">Identity & Rating</div><div class="rating-row">`;
    if(rating.rated_voltage!=null)   html+=`<div class="ritem"><div class="rl">Voltage</div><div class="rv">${rating.rated_voltage} V</div></div>`;
    if(rating.rated_current!=null)   html+=`<div class="ritem"><div class="rl">Current</div><div class="rv">${rating.rated_current} A</div></div>`;
    if(rating.rated_battery_voltage!=null) html+=`<div class="ritem"><div class="rl">Batt V</div><div class="rv">${rating.rated_battery_voltage} V</div></div>`;
    if(rating.rated_frequency!=null) html+=`<div class="ritem"><div class="rl">Freq</div><div class="rv">${rating.rated_frequency} Hz</div></div>`;
    if(hasInfo)                      html+=`<div class="ritem"><div class="rl">Model</div><div class="rv" style="font-size:11px">${info.model}</div></div>`;
    html+=`</div></div>`;
  }

  body.innerHTML=html;
}

// ── Main update loop ───────────────────────────────────────
let unitIds=[];

async function updateDashboard(){
  try{
    const [statusRes, alarmsRes]=await Promise.all([
      fetch('/api/status',{cache:'no-store'}),
      fetch('/api/alarms',{cache:'no-store'}),
    ]);
    const data=await statusRes.json();
    const alarms=await alarmsRes.json();

    // Filter real unit keys
    unitIds=Object.keys(data).filter(k=>k!=='serial'&&k!=='protocol');

    // ── Update summary strip ─────────────────────────────────
    let online=0, utilFails=0, battSum=0, battCount=0;
    unitIds.forEach(id=>{
      const u=data[id];
      if(u.connected)online++;
      if(u.ups&&u.ups.utility_fail)utilFails++;
      if(u.ups&&u.ups.battery_percentage!=null){battSum+=u.ups.battery_percentage;battCount++;}
    });

    el('sumOnline').textContent=online;
    el('sumTotal').textContent=`of ${unitIds.length} units`;
    el('sumOnline').style.color=online===unitIds.length?'var(--green)':'var(--amber)';

    if(utilFails>0){
      el('sumUtility').textContent=`${utilFails} FAIL`;
      el('sumUtility').style.color='var(--red)';
      el('sumUtilitySub').textContent='On battery backup';
    }else{
      el('sumUtility').textContent='OK';
      el('sumUtility').style.color='var(--green)';
      el('sumUtilitySub').textContent='All on mains';
    }

    el('sumAlarms').textContent=alarms.length;
    el('sumAlarms').style.color=alarms.length?'var(--red)':'var(--green)';

    if(battCount){
      const avg=(battSum/battCount).toFixed(1);
      el('sumBattery').textContent=avg+'%';
      el('sumBattery').style.color=battColour(parseFloat(avg))==='green'?'var(--green)':battColour(parseFloat(avg))==='amber'?'var(--amber)':'var(--red)';
    }
    el('sumTime').textContent=new Date().toLocaleTimeString('en-IN');

    // ── Alert banner ─────────────────────────────────────────
    const banner=el('alertBanner');
    if(alarms.length){
      const names=[...new Set(alarms.map(a=>a.device_name))].join(', ');
      el('alertText').textContent=`${alarms.length} active alarm${alarms.length>1?'s':''}: ${names} — Utility Fail`;
      banner.classList.add('visible');
    }else{
      banner.classList.remove('visible');
    }

    // ── Audio Alert Trigger ─────────────────────────────────
    let hasCritical = false, hasWarning = false;
    unitIds.forEach(id => {
      const u = data[id];
      if (u && u.ups) {
        if (u.ups.battery_low || u.ups.ups_failed) hasCritical = true;
        if (u.ups.utility_fail || u.ups.beeper_sounding) hasWarning = true;
      }
    });
    if (alarms.length > 0) hasWarning = true;

    if (hasCritical) {
      playBrowserAlarm(true);
    } else if (hasWarning) {
      playBrowserAlarm(false);
    }

    // ── Render / update panels ───────────────────────────────
    const container=el('upsPanels');
    unitIds.forEach(id=>{
      const unit=data[id];
      let panel=el('panel-'+id);

      if(!panel){
        panel=document.createElement('div');
        panel.id='panel-'+id;
        panel.className='panel';

        const title=(unit.device_name||id)+' UPS';
        const ipStr=unit.usr?`${unit.usr.ip}:${unit.usr.port}`:'';
        panel.innerHTML=`
          <div class="panel-head">
            <div class="ph-left">
              <div class="ph-icon">${svgIcon('server',17)}</div>
              <div class="ph-name">${title}</div>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span class="ph-ip">${ipStr}</span>
              <a href="/ups/${id}" class="ph-detail-btn">Detail →</a>
            </div>
          </div>
          <div id="conn-${id}" class="conn-bar offline">
            <span class="dot"></span><span>Connecting…</span>
          </div>
          <div id="fail-${id}" class="utility-fail-bar"></div>
          <div class="pbody" id="body-${id}">
            <div class="no-data">
              <div class="no-data-icon">${svgIcon('bolt',30)}</div>
              <div class="no-data-text">Waiting for first poll…</div>
            </div>
          </div>`;
        container.appendChild(panel);
      }

      // Connection bar
      const connEl=el('conn-'+id);
      if(unit.connected){
        connEl.className='conn-bar online';
        connEl.innerHTML=`<span class="dot"></span><span>Online</span>
          <span class="latency">${unit.latency_ms?unit.latency_ms+' ms':''}</span>`;
      }else{
        connEl.className='conn-bar offline';
        connEl.innerHTML=`<span class="dot"></span>
          <span>Disconnected${unit.error?' — '+unit.error:''}</span>`;
      }

      renderPanelBody('body-'+id,'fail-'+id,panel,unit);
    });

  }catch(err){console.error('Dashboard update error:',err)}
}

// ── Web Audio Synthesized Alarm ───────────────────────────
let audioCtx = null;
let audioEnabled = true;

function toggleAudio() {
  audioEnabled = !audioEnabled;
  const btn = el('audioToggleBtn');
  if (btn) {
    btn.innerHTML = audioEnabled
      ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6"/></svg><span>Sound: ON</span>'
      : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M17 9l4 6M21 9l-4 6"/></svg><span>Sound: OFF</span>';
    btn.classList.toggle('active', audioEnabled);
  }
}

function playBrowserAlarm(isCritical) {
  if (!audioEnabled) return;
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    const t = audioCtx.currentTime;
    const tones = isCritical ? [880, 1175] : [659, 880];
    const dur = isCritical ? 0.35 : 0.55;

    tones.forEach((freq, idx) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      const startTime = t + (idx * 0.12);

      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, startTime);
      gain.gain.setValueAtTime(0.09, startTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, startTime + dur);

      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(startTime);
      osc.stop(startTime + dur);
    });
  } catch(e) {
    console.debug('Audio error:', e);
  }
}

// ── Boot ───────────────────────────────────────────────────
updateClock();
updateDashboard();
setInterval(updateClock,1000);
setInterval(updateDashboard,3000);
</script>
</body>
</html>"""


# =============================================================
# SINGLE UPS DETAIL PAGE  (with history chart)
# =============================================================

SINGLE_UPS_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__UPS_TITLE__ · UPS Monitor</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/hammer.js/2.0.8/hammer.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-annotation/3.0.1/chartjs-plugin-annotation.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-zoom/2.2.0/chartjs-plugin-zoom.min.js"></script>
<style>
:root{
  --bg:#eef2f9;--surface:#ffffff;--card:#f6f8fc;--card2:#eaeff7;
  --border:#e3e8f2;--border2:#d3dbe9;--text:#101826;--text2:#56617a;--text3:#94a0b8;
  --green:#0ea652;--red:#e11d3c;--amber:#d97706;--blue:#2563eb;--cyan:#0891b2;
  --radius:16px;--radius-sm:10px;--shadow:0 2px 10px rgba(30,41,80,.06), 0 10px 30px rgba(30,41,80,.06);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:var(--bg);color:var(--text);min-height:100vh;padding:0}

.hdr{background:var(--surface);border-bottom:1px solid var(--border);
     padding:14px 28px;display:flex;align-items:center;justify-content:space-between;
     position:sticky;top:0;z-index:100;flex-wrap:wrap;gap:12px}
.hdr-left{display:flex;align-items:center;gap:14px}
.back-btn{display:inline-flex;align-items:center;gap:6px;color:var(--blue);
          text-decoration:none;font-size:13px;font-weight:700;
          background:rgba(59,130,246,.1);border:1px solid rgba(59,130,246,.2);
          padding:6px 14px;border-radius:20px;transition:all .2s}
.back-btn:hover{background:var(--blue);color:#fff}
.page-title{font-size:18px;font-weight:800}
.page-sub{font-size:12px;color:var(--text3);margin-top:1px}
.clock{font-size:13px;color:var(--text2);font-variant-numeric:tabular-nums}

/* Utility fail strip at top */
#utilityFailStrip{display:none;background:#fef1f2;
  padding:12px 28px;border-bottom:1px solid #fecdd3;
  font-size:14px;font-weight:700;color:#be123c;align-items:center;gap:10px}
#utilityFailStrip.show{display:flex}
.pulse-dot{width:12px;height:12px;border-radius:50%;background:#ef4444;
           animation:pulse 1s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(.7)}}

.main{max-width:1200px;margin:0 auto;padding:24px 28px;display:flex;flex-direction:column;gap:20px}

/* Status card grid at top */
.status-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);
           padding:16px 18px;display:flex;flex-direction:column;gap:4px;transition:border-color .2s}
.stat-card.alarm{border-color:var(--red);background:rgba(239,68,68,.05)}
.stat-card.warning{border-color:var(--amber);background:rgba(245,158,11,.04)}
.stat-lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text3);
          display:flex;align-items:center;gap:5px}
.ic{flex-shrink:0}
.ic-chip{display:inline-flex;align-items:center;justify-content:center;
         width:30px;height:30px;border-radius:9px;flex-shrink:0}
.ic-chip svg{width:18px;height:18px}
.sec-lbl .ic-chip{width:26px;height:26px;border-radius:8px;margin-right:6px}
.flbl .ic-chip{width:25px;height:25px;border-radius:8px}
.chart-title .ic-chip{width:34px;height:34px;border-radius:11px}
.c-cyan   {background:#cffafe;color:#0e7490}
.c-blue   {background:#dbeafe;color:#1d4ed8}
.c-purple {background:#f3e8ff;color:#7c3aed}
.c-pink   {background:#fce7f3;color:#db2777}
.c-orange {background:#ffedd5;color:#c2410c}
.c-green  {background:#dcfce7;color:#15803d}
.c-teal   {background:#ccfbf1;color:#0f766e}
.c-indigo {background:#e0e7ff;color:#4338ca}
.c-red    {background:#fee2e2;color:#b91c1c}
.c-amber  {background:#fef3c7;color:#b45309}
.c-violet {background:#ede9fe;color:#6d28d9}
.c-slate  {background:#e2e8f0;color:#334155}
.chart-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
             flex-direction:column;gap:8px;color:var(--text3);font-size:13px;text-align:center;
             background:var(--surface)}
.chart-empty svg{opacity:.35}
.stat-card{box-shadow:0 1px 2px rgba(16,24,38,.03)}
.stat-card:hover{box-shadow:0 4px 14px rgba(30,41,80,.08)}
.flbl{display:flex;align-items:center;gap:6px}
.sound-btn{display:inline-flex!important;align-items:center;gap:6px}
.sound-btn.active{color:var(--blue);border-color:var(--blue);background:rgba(37,99,235,.08)}
.chart-title{display:flex;align-items:center;gap:7px}
.chart-title .ic{color:var(--blue)}
.chart-card{box-shadow:0 1px 3px rgba(16,24,38,.05)}
.ritem{box-shadow:0 1px 2px rgba(16,24,38,.03)}
.stat-val{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums}
.stat-val.green{color:var(--green)} .stat-val.red{color:var(--red)}
.stat-val.amber{color:var(--amber)} .stat-val.blue{color:var(--blue)}
.stat-val.cyan{color:var(--cyan)}   .stat-val.muted{color:var(--text2);font-size:16px}

/* Battery progress */
.batt-progress{margin-top:8px}
.batt-track{height:6px;background:var(--card2);border-radius:4px;overflow:hidden;border:1px solid var(--border)}
.batt-fill{height:100%;border-radius:4px;transition:width .6s ease}

/* Flags */
.flags-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:8px}
.flag{display:flex;align-items:center;gap:9px;padding:10px 13px;
      background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);
      font-size:13px;font-weight:500;transition:all .2s}
.flag.alarm-st{border-color:var(--red);background:rgba(239,68,68,.07)}
.flag.warn-st{border-color:var(--amber);background:rgba(245,158,11,.06)}
.fdot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.fdot.ok{background:var(--green);box-shadow:0 0 5px rgba(34,197,94,.5)}
.fdot.warn{background:var(--amber);box-shadow:0 0 5px rgba(245,158,11,.5)}
.fdot.err{background:var(--red);box-shadow:0 0 5px rgba(239,68,68,.5)}
.flbl{color:var(--text2)}
.chart-reset{padding:5px 10px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;
             background:var(--card);border:1px solid var(--border);color:var(--text2);transition:all .18s}
.chart-reset:hover{background:var(--text2);border-color:var(--text2);color:#fff}

/* Chart card */
.chart-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
            padding:20px 24px;box-shadow:var(--shadow)}
.chart-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px}
.chart-title{font-size:15px;font-weight:700}
.range-btns{display:flex;gap:6px}
.range-btn{padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;
           background:var(--card);border:1px solid var(--border);color:var(--text2);
           transition:all .18s}
.range-btn:hover,.range-btn.active{background:var(--blue);border-color:var(--blue);color:#fff}
.chart-wrap{position:relative;height:240px}

/* Rating */
.rating-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px}
.rating-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-top:12px}
.ritem{text-align:center;padding:12px 8px;background:var(--card);
       border:1px solid var(--border);border-radius:var(--radius-sm)}
.ritem .rl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--text3)}
.ritem .rv{font-size:15px;font-weight:800;margin-top:4px;color:var(--cyan)}

.sec-lbl{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:1.2px;
         color:var(--text3);margin-bottom:10px;display:flex;align-items:center}
</style>
</head>
<body>

<header class="hdr">
  <div class="hdr-left">
    <a href="/" class="back-btn">← All Units</a>
    <div>
      <div class="page-title">__UPS_TITLE__</div>
      <div class="page-sub">__UPS_IP__</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:16px">
    <button id="audioToggleBtn" onclick="toggleAudio()" class="back-btn sound-btn active" style="cursor:pointer" title="Toggle audio alarms"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6"/></svg><span>Sound: ON</span></button>
    <div class="clock" id="clock"></div>
  </div>
</header>

<div id="utilityFailStrip">
  <span class="pulse-dot"></span>
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 20h20z"/><path d="M12 10v4"/><circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none"/></svg>
  <span>UTILITY FAIL — This UPS is running on battery backup</span>
</div>

<main class="main">

  <!-- Live metrics -->
  <div>
    <div class="sec-lbl"><span class="ic-chip c-blue"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15l4-5"/></svg></span>Live Metrics</div>
    <div class="status-grid" id="statusGrid">
      <div class="stat-card"><div class="stat-lbl"><span class="ic-chip c-green"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg></span>Status</div><div class="stat-val muted" id="sv-status">—</div></div>
      <div class="stat-card" id="sc-utility"><div class="stat-lbl"><span class="ic-chip c-blue"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v4M14 3v4M6 8h10l-1 5a4 4 0 0 1-4 3.5A4 4 0 0 1 7 13z"/><path d="M10 16.5V21"/></svg></span>Utility</div><div class="stat-val" id="sv-utility">—</div></div>
      <div class="stat-card"><div class="stat-lbl"><span class="ic-chip c-cyan"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 1 3 12h6l-1 9 8-11H10z"/></svg></span>EB Input</div><div class="stat-val cyan" id="sv-input">—</div></div>
      <div class="stat-card"><div class="stat-lbl"><span class="ic-chip c-blue"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3v4M14 3v4M6 8h10l-1 5a4 4 0 0 1-4 3.5A4 4 0 0 1 7 13z"/><path d="M10 16.5V21"/></svg></span>To Office</div><div class="stat-val blue" id="sv-output">—</div></div>
      <div class="stat-card" id="sc-load"><div class="stat-lbl"><span class="ic-chip c-purple"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15l4-5"/></svg></span>Load</div><div class="stat-val" id="sv-load">—</div></div>
      <div class="stat-card"><div class="stat-lbl"><span class="ic-chip c-pink"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h3l2-7 4 14 3-10 2 3h4"/></svg></span>Frequency</div><div class="stat-val" id="sv-freq">—</div></div>
      <div class="stat-card"><div class="stat-lbl"><span class="ic-chip c-orange"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a2 2 0 0 0-2 2v9.5a4 4 0 1 0 4 0V5a2 2 0 0 0-2-2z"/><circle cx="12" cy="18" r="1.6"/></svg></span>Temperature</div><div class="stat-val" id="sv-temp">—</div></div>
      <div class="stat-card" id="sc-batt">
        <div class="stat-lbl"><span class="ic-chip c-green"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="8" width="16" height="8" rx="1.5"/><path d="M20 10.5v3"/></svg></span>Battery</div>
        <div class="stat-val" id="sv-batt">—</div>
        <div class="batt-progress">
          <div class="batt-track"><div class="batt-fill" id="sv-batt-bar" style="width:0%;background:var(--green)"></div></div>
        </div>
      </div>
      <div class="stat-card"><div class="stat-lbl"><span class="ic-chip c-teal"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3v4M9 3v4M3 7h8l-1 4a3 3 0 0 1-3 2.5A3 3 0 0 1 6 11z"/><path d="M7 13.5V17"/></svg></span>Cell V</div><div class="stat-val" id="sv-cellv">—</div></div>
      <div class="stat-card"><div class="stat-lbl"><span class="ic-chip c-indigo"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="10" width="18" height="8" rx="1"/><path d="M6 10V7l6-4 6 4v3"/></svg></span>Bank V</div><div class="stat-val" id="sv-bankv">—</div></div>
      <div class="stat-card"><div class="stat-lbl"><span class="ic-chip c-cyan"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/></svg></span>Backup</div><div class="stat-val cyan" id="sv-backup">—</div></div>
      <div class="stat-card"><div class="stat-lbl"><span class="ic-chip c-slate"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v7"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/></svg></span>Mode</div><div class="stat-val" id="sv-mode">—</div></div>
    </div>
  </div>

  <!-- Status flags -->
  <div>
    <div class="sec-lbl"><span class="ic-chip c-indigo"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/></svg></span>Status Flags</div>
    <div class="flags-grid" id="flagsGrid">
      <div class="flag" id="fl-overall"><span class="fdot ok"></span><span class="flbl">Overall: —</span></div>
      <div class="flag" id="fl-utility"><span class="fdot ok"></span><span class="flbl">Utility: —</span></div>
      <div class="flag" id="fl-batlow"><span class="fdot ok"></span><span class="flbl">Battery Low: —</span></div>
      <div class="flag" id="fl-avr"><span class="fdot ok"></span><span class="flbl">AVR: —</span></div>
      <div class="flag" id="fl-fault"><span class="fdot ok"></span><span class="flbl">UPS Fault: —</span></div>
      <div class="flag" id="fl-beeper"><span class="fdot ok"></span><span class="flbl">Beeper: —</span></div>
      <div class="flag" id="fl-shutdown"><span class="fdot ok"></span><span class="flbl">Shutdown: —</span></div>
      <div class="flag" id="fl-test"><span class="fdot ok"></span><span class="flbl">Test: —</span></div>
    </div>
  </div>

  <!-- Input/Output voltage history chart -->
  <div class="chart-card">
    <div class="chart-hdr">
      <div class="chart-title"><span class="ic-chip c-pink"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h3l2-7 4 14 3-10 2 3h4"/></svg></span>EB Input vs UPS Output Voltage — History</div>
      <div class="range-btns">
        <button class="chart-reset" onclick="resetChartZoom()" title="Reset chart zoom">Reset</button>
        <button class="range-btn" onclick="loadChart(1)">1h</button>
        <button class="range-btn active" onclick="loadChart(6)">6h</button>
        <button class="range-btn" onclick="loadChart(24)">24h</button>
        <button class="range-btn" onclick="loadChart(72)">3d</button>
        <button class="range-btn" onclick="loadChart(168)">7d</button>
      </div>
    </div>
    <div class="chart-wrap"><canvas id="voltChart"></canvas>
      <div class="chart-empty" id="voltChartEmpty" style="display:none">
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h3l2-7 4 14 3-10 2 3h4"/></svg>
        <span id="voltChartEmptyMsg">No historical readings yet for this range.</span>
      </div>
    </div>
  </div>

  <!-- Battery & load chart -->
  <div class="chart-card">
    <div class="chart-hdr">
      <div class="chart-title"><span class="ic-chip c-green"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="8" width="16" height="8" rx="1.5"/><path d="M20 10.5v3"/></svg></span>Battery Backup & Load — History</div>
      <div class="range-btns">
        <button class="chart-reset" onclick="resetChartZoom()" title="Reset chart zoom">Reset</button>
        <button class="range-btn" onclick="loadBattChart(1)">1h</button>
        <button class="range-btn active" onclick="loadBattChart(6)">6h</button>
        <button class="range-btn" onclick="loadBattChart(24)">24h</button>
        <button class="range-btn" onclick="loadBattChart(72)">3d</button>
      </div>
    </div>
    <div class="chart-wrap"><canvas id="battChart"></canvas>
      <div class="chart-empty" id="battChartEmpty" style="display:none">
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="8" width="16" height="8" rx="1.5"/><path d="M20 10.5v3"/></svg>
        <span id="battChartEmptyMsg">No historical readings yet for this range.</span>
      </div>
    </div>
  </div>

  <!-- Rating & Identity -->
  <div class="rating-card" id="ratingCard" style="display:none">
    <div class="sec-lbl"><span class="ic-chip c-violet"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="10" width="18" height="8" rx="1"/><path d="M6 10V7l6-4 6 4v3"/></svg></span>Identity & Rating</div>
    <div class="rating-row" id="ratingRow"></div>
  </div>

</main>

<script>
const UPS_ID = '__UPS_ID__';

function el(id){return document.getElementById(id)}
function fmt(v,u='',d=1){return v!=null?Number(v).toFixed(d)+u:'—'}

function updateClock(){
  el('clock').textContent=new Date().toLocaleString('en-IN',
    {hour:'2-digit',minute:'2-digit',second:'2-digit',day:'2-digit',month:'short'});
}

// ── Colour helpers ─────────────────────────────────────────
function battColour(p){if(p==null)return'var(--text2)';if(p>60)return'var(--green)';if(p>25)return'var(--amber)';return'var(--red)'}
function battClass(p){if(p==null)return'muted';if(p>60)return'green';if(p>25)return'amber';return'red'}

// ── Update live metrics ────────────────────────────────────
function updateMetrics(ups){
  if(!ups){return}

  // Status
  const statusCls=ups.overall_status==='OK'?'green':ups.overall_status==='ON BATTERY'?'amber':'red';
  el('sv-status').textContent=ups.overall_status||'—';
  el('sv-status').className='stat-val '+statusCls;

  // Utility
  el('sv-utility').textContent=ups.utility_fail?'FAIL':'OK';
  el('sv-utility').className='stat-val '+(ups.utility_fail?'red':'green');
  el('sc-utility').className='stat-card '+(ups.utility_fail?'alarm':'');

  // Electrical
  el('sv-input').textContent=fmt(ups.input_voltage,'V');
  el('sv-output').textContent=fmt(ups.output_voltage,'V');

  const lp=ups.output_load_pct;
  el('sv-load').textContent=lp!=null?lp+'%':'—';
  el('sv-load').className='stat-val '+(lp>80?'red':lp>50?'amber':'green');
  el('sc-load').className='stat-card '+(lp>80?'alarm':lp>50?'warning':'');

  el('sv-freq').textContent=fmt(ups.input_frequency,' Hz');
  el('sv-temp').textContent=fmt(ups.temperature,'°C');

  // Battery
  const bp=ups.battery_percentage;
  el('sv-batt').textContent=bp!=null?bp.toFixed(1)+'%':'—';
  el('sv-batt').className='stat-val '+battClass(bp);
  el('sv-batt-bar').style.width=(bp!=null?Math.max(2,bp)+'%':'0%');
  el('sv-batt-bar').style.background=battColour(bp);
  el('sc-batt').className='stat-card '+(bp!=null&&bp<=25?'alarm':bp!=null&&bp<=60?'warning':'');

  el('sv-cellv').textContent=fmt(ups.battery_voltage,'V');
  el('sv-bankv').textContent=ups.battery_bank_voltage_est!=null?fmt(ups.battery_bank_voltage_est,'V'):'N/A';
  el('sv-backup').textContent=ups.estimated_backup_minutes!=null?ups.estimated_backup_minutes+' min':'—';

  el('sv-mode').textContent=ups.operating_mode||'—';
  el('sv-mode').className='stat-val '+(ups.operating_mode==='Online'?'green':'amber');

  // Utility fail strip
  if(ups.utility_fail){el('utilityFailStrip').classList.add('show')}
  else{el('utilityFailStrip').classList.remove('show')}

  // Flags
  setFlag('fl-overall','Overall',ups.overall_status,statusCls==='green'?'ok':statusCls==='amber'?'warn':'err',statusCls==='red'?'alarm-st':statusCls==='amber'?'warn-st':'');
  setFlag('fl-utility','Utility',ups.utility_fail?'FAIL':'OK',ups.utility_fail?'err':'ok',ups.utility_fail?'alarm-st':'');
  setFlag('fl-batlow','Battery Low',ups.battery_low?'LOW':'OK',ups.battery_low?'err':'ok',ups.battery_low?'alarm-st':'');
  setFlag('fl-avr','AVR',ups.avr_active?'ACTIVE':'OFF',ups.avr_active?'warn':'ok',ups.avr_active?'warn-st':'');
  setFlag('fl-fault','UPS Fault',ups.ups_failed?'FAULT':'OK',ups.ups_failed?'err':'ok',ups.ups_failed?'alarm-st':'');
  setFlag('fl-beeper','Beeper',ups.beeper_sounding?'SOUNDING':(ups.beeper_on?'ARMED':'OFF'),
    ups.beeper_sounding?'err':ups.beeper_on?'warn':'ok',ups.beeper_sounding?'alarm-st':ups.beeper_on?'warn-st':'');
  setFlag('fl-shutdown','Shutdown',ups.shutdown_active?'ACTIVE':'OFF',ups.shutdown_active?'err':'ok',ups.shutdown_active?'alarm-st':'');
  setFlag('fl-test','Test',ups.test_in_progress?'RUNNING':'OFF',ups.test_in_progress?'warn':'ok',ups.test_in_progress?'warn-st':'');
}

function setFlag(id,lbl,txt,dot,cls){
  const e=el(id);
  if(!e)return;
  e.className='flag '+cls;
  const icons={
    Overall:'shield',Utility:'plug','Battery Low':'battery',AVR:'gauge',
    'UPS Fault':'alert',Beeper:'bell',Shutdown:'power',Test:'test'
  };
  const colors={Overall:'indigo',Utility:'blue','Battery Low':'orange',AVR:'purple',
    'UPS Fault':'red',Beeper:'amber',Shutdown:'slate',Test:'violet'};
  const paths={
    shield:'<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/>',
    plug:'<path d="M8 3v4M14 3v4M6 8h10l-1 5a4 4 0 0 1-4 3.5A4 4 0 0 1 7 13z"/><path d="M10 16.5V21"/>',
    battery:'<rect x="2" y="8" width="16" height="8" rx="1.5"/><path d="M20 10.5v3"/>',
    gauge:'<path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15l4-5"/>',
    alert:'<path d="M12 3 2 20h20z"/><path d="M12 10v4"/><circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none"/>',
    bell:'<path d="M12 3a5 5 0 0 0-5 5v3l-2 4h14l-2-4V8a5 5 0 0 0-5-5z"/><path d="M9.5 19a2.5 2.5 0 0 0 5 0"/>',
    power:'<path d="M12 3v7"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/>',
    test:'<path d="M9 2v6L4 19a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-5-11V2"/>'
  };
  const icon=icons[lbl]||'flag';
  e.innerHTML=`<span class="fdot ${dot}"></span><span class="flbl"><span class="ic-chip c-${colors[lbl]||'slate'}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[icon]||'<circle cx="12" cy="12" r="9"/>'}</svg></span>${lbl}: <strong>${txt}</strong></span>`;
}

// ── Charts (Yahoo-Finance style: gradient area fill + red   ──
//    "danger zone" segments + safe-band reference lines) ────
let voltChartObj=null, battChartObj=null;

// Safe operating band for mains/output voltage — tweak to your site's spec.
const VOLT_SAFE_MIN = 200;   // below this = brown-out risk
const VOLT_SAFE_MAX = 250;   // above this = spike risk
const BATT_WARN_PCT = 50;    // amber below this
const BATT_CRIT_PCT = 25;    // red below this

const chartDefaults={
  responsive:true,maintainAspectRatio:false,
  plugins:{
    legend:{labels:{color:'#56617a',boxWidth:12,padding:16,font:{size:11,weight:'600'}}},
    tooltip:{
      mode:'index',intersect:false,
      backgroundColor:'#ffffff',titleColor:'#101826',bodyColor:'#101826',
      borderColor:'#e3e8f2',borderWidth:1,padding:10,
      titleFont:{size:11,weight:'700'},bodyFont:{size:11},
      boxPadding:4,
    },
    zoom:{
      pan:{enabled:true,mode:'x'},
      zoom:{wheel:{enabled:true},pinch:{enabled:true},drag:{enabled:true},mode:'x'}
    },
  },
  scales:{
    x:{ticks:{color:'#94a0b8',maxTicksLimit:8,font:{size:10}},grid:{color:'#eef1f7',drawTicks:false}},
    y:{ticks:{color:'#94a0b8',font:{size:10}},grid:{color:'#eef1f7',drawTicks:false},border:{display:false}}
  },
  interaction:{mode:'index',intersect:false},
  elements:{point:{radius:0,hitRadius:8,hoverRadius:4}}
};

// The CDN build can expose the plugin under either global name. Keep the
// dashboard usable when an external script is blocked or unavailable.
const chartZoomPlugin=window.zoomPlugin||window.ChartZoom;
if(chartZoomPlugin)Chart.register(chartZoomPlugin);

function resetChartZoom(){
  if(voltChartObj)voltChartObj.resetZoom();
  if(battChartObj)battChartObj.resetZoom();
}

function downsample(rows,maxPts=500){
  if(rows.length<=maxPts)return rows;
  const step=Math.ceil(rows.length/maxPts);
  return rows.filter((_,i)=>i%step===0);
}

function fmtTs(iso){
  const d=new Date(iso);
  return d.toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'short'});
}

// Gradient fill under the line, like a stock-price chart
function areaGradient(ctx,hexRgb){
  const {chartArea}=ctx.chart;
  if(!chartArea)return hexRgb+'22';
  const g=ctx.chart.ctx.createLinearGradient(0,chartArea.top,0,chartArea.bottom);
  g.addColorStop(0,hexRgb+'55');
  g.addColorStop(1,hexRgb+'02');
  return g;
}

// Segment coloring: red for out-of-safe-band voltage, else the base colour
function voltSegmentColor(baseColor){
  return {
    borderColor:(ctx)=>{
      const v=ctx.p1.parsed.y;
      if(v==null)return baseColor;
      return (v<VOLT_SAFE_MIN||v>VOLT_SAFE_MAX)?'#e11d3c':baseColor;
    },
  };
}

async function loadChart(hours){
  document.querySelectorAll('#voltChart+.range-btns .range-btn, .chart-card:nth-child(3) .range-btn').forEach(b=>{
    b.classList.remove('active');
    if(b.textContent===hours+'h'||(hours===168&&b.textContent==='7d')||(hours===72&&b.textContent==='3d'))b.classList.add('active');
  });

  const emptyEl=el('voltChartEmpty'), emptyMsg=el('voltChartEmptyMsg');
  try{
    const res=await fetch(`/api/history/${UPS_ID}?hours=${hours}`,{cache:'no-store'});
    if(!res.ok){
      emptyMsg.textContent=`Backend returned HTTP ${res.status} for /api/history/${UPS_ID} — check the web_app/db_store logs.`;
      emptyEl.style.display='flex';
      if(voltChartObj){voltChartObj.destroy();voltChartObj=null;}
      return;
    }
    const {rows}=await res.json();

    if(!rows||rows.length===0){
      // Genuinely queried the DB — it just has no rows in this window yet.
      emptyMsg.textContent='No rows returned from the telemetry table for this range — confirm worker.py is running and writing to Postgres.';
      emptyEl.style.display='flex';
      if(voltChartObj){voltChartObj.destroy();voltChartObj=null;}
      return;
    }
    emptyEl.style.display='none';

    const ds=downsample(rows);

    const labels=ds.map(r=>fmtTs(r.ts));
    const inV=ds.map(r=>r.input_voltage);
    const outV=ds.map(r=>r.output_voltage);

    if(voltChartObj){voltChartObj.destroy()}
    voltChartObj=new Chart(el('voltChart'),{
      type:'line',
      data:{
        labels,
        datasets:[
          {label:'EB Input (V)',data:inV,borderColor:'#db2777',
           backgroundColor:(ctx)=>areaGradient(ctx,'#db2777'),
           borderWidth:2,tension:.3,fill:true,segment:voltSegmentColor('#db2777')},
          {label:'UPS Output → Office (V)',data:outV,borderColor:'#0f766e',
           backgroundColor:(ctx)=>areaGradient(ctx,'#0f766e'),
           borderWidth:2,tension:.3,fill:true,segment:voltSegmentColor('#0f766e')},
        ]
      },
      options:{...chartDefaults,scales:{...chartDefaults.scales,
        y:{...chartDefaults.scales.y,title:{display:true,text:'Voltage (V)',color:'#94a0b8',font:{size:10}}}},
        plugins:{...chartDefaults.plugins,
          annotation:{annotations:{
            safeBand:{type:'box',yMin:VOLT_SAFE_MIN,yMax:VOLT_SAFE_MAX,
              backgroundColor:'rgba(14,166,82,.05)',borderWidth:0},
            minLine:{type:'line',yMin:VOLT_SAFE_MIN,yMax:VOLT_SAFE_MIN,
              borderColor:'#d97706',borderWidth:1,borderDash:[5,4],
              label:{display:true,content:'Safe min '+VOLT_SAFE_MIN+'V',position:'start',
                backgroundColor:'#d97706',color:'#fff',font:{size:9,weight:'700'},padding:4}},
            maxLine:{type:'line',yMin:VOLT_SAFE_MAX,yMax:VOLT_SAFE_MAX,
              borderColor:'#e11d3c',borderWidth:1,borderDash:[5,4],
              label:{display:true,content:'Spike guard '+VOLT_SAFE_MAX+'V',position:'end',
                backgroundColor:'#e11d3c',color:'#fff',font:{size:9,weight:'700'},padding:4}},
          }}}
      }
    });
  }catch(e){console.error('voltChart error',e)}
}

async function loadBattChart(hours){
  const emptyEl=el('battChartEmpty'), emptyMsg=el('battChartEmptyMsg');
  try{
    const res=await fetch(`/api/history/${UPS_ID}?hours=${hours}`,{cache:'no-store'});
    if(!res.ok){
      emptyMsg.textContent=`Backend returned HTTP ${res.status} for /api/history/${UPS_ID} — check the web_app/db_store logs.`;
      emptyEl.style.display='flex';
      if(battChartObj){battChartObj.destroy();battChartObj=null;}
      return;
    }
    const {rows}=await res.json();

    if(!rows||rows.length===0){
      emptyMsg.textContent='No rows returned from the telemetry table for this range — confirm worker.py is running and writing to Postgres.';
      emptyEl.style.display='flex';
      if(battChartObj){battChartObj.destroy();battChartObj=null;}
      return;
    }
    emptyEl.style.display='none';

    const ds=downsample(rows);

    const labels=ds.map(r=>fmtTs(r.ts));
    const batt=ds.map(r=>r.battery_percentage);
    const load=ds.map(r=>r.output_load_pct);

    const battSegment={
      borderColor:(ctx)=>{
        const v=ctx.p1.parsed.y;
        if(v==null)return'#0ea652';
        if(v<=BATT_CRIT_PCT)return'#e11d3c';
        if(v<=BATT_WARN_PCT)return'#d97706';
        return'#0ea652';
      },
    };

    if(battChartObj){battChartObj.destroy()}
    battChartObj=new Chart(el('battChart'),{
      type:'line',
      data:{
        labels,
        datasets:[
          {label:'Battery Backup %',data:batt,borderColor:'#0ea652',
           backgroundColor:(ctx)=>areaGradient(ctx,'#0ea652'),
           borderWidth:2,tension:.3,fill:true,yAxisID:'y',segment:battSegment},
          {label:'Load %',data:load,borderColor:'#d97706',
           backgroundColor:'transparent',
           borderWidth:1.5,borderDash:[4,3],tension:.3,fill:false,yAxisID:'y'},
        ]
      },
      options:{...chartDefaults,scales:{
        x:{...chartDefaults.scales.x},
        y:{...chartDefaults.scales.y,min:0,max:100,title:{display:true,text:'Percent (%)',color:'#94a0b8',font:{size:10}}},
      },
      plugins:{...chartDefaults.plugins,
        annotation:{annotations:{
          warnLine:{type:'line',yMin:BATT_WARN_PCT,yMax:BATT_WARN_PCT,
            borderColor:'#d97706',borderWidth:1,borderDash:[5,4],
            label:{display:true,content:'Low '+BATT_WARN_PCT+'%',position:'start',
              backgroundColor:'#d97706',color:'#fff',font:{size:9,weight:'700'},padding:4}},
          critLine:{type:'line',yMin:BATT_CRIT_PCT,yMax:BATT_CRIT_PCT,
            borderColor:'#e11d3c',borderWidth:1,borderDash:[5,4],
            label:{display:true,content:'Critical '+BATT_CRIT_PCT+'%',position:'start',
              backgroundColor:'#e11d3c',color:'#fff',font:{size:9,weight:'700'},padding:4}},
        }}}}
    });
  }catch(e){console.error('battChart error',e)}
}

// ── Rating card ────────────────────────────────────────────
function renderRating(rating,info){
  const card=el('ratingCard');
  const row=el('ratingRow');
  let html='';
  if(rating.rated_voltage!=null)html+=`<div class="ritem"><div class="rl">Voltage</div><div class="rv">${rating.rated_voltage} V</div></div>`;
  if(rating.rated_current!=null)html+=`<div class="ritem"><div class="rl">Current</div><div class="rv">${rating.rated_current} A</div></div>`;
  if(rating.rated_battery_voltage!=null)html+=`<div class="ritem"><div class="rl">Batt V</div><div class="rv">${rating.rated_battery_voltage} V</div></div>`;
  if(rating.rated_frequency!=null)html+=`<div class="ritem"><div class="rl">Freq</div><div class="rv">${rating.rated_frequency} Hz</div></div>`;
  if(info&&info.model&&info.model!=='Not reported by UPS')html+=`<div class="ritem"><div class="rl">Model</div><div class="rv" style="font-size:12px">${info.model}</div></div>`;
  if(info&&info.company_name&&info.company_name!=='Not reported by UPS')html+=`<div class="ritem"><div class="rl">Mfr</div><div class="rv" style="font-size:11px">${info.company_name}</div></div>`;
  if(html){row.innerHTML=html;card.style.display='block';}
}

// ── Web Audio Synthesized Alarm ───────────────────────────
let audioCtx = null;
let audioEnabled = true;

function toggleAudio() {
  audioEnabled = !audioEnabled;
  const btn = el('audioToggleBtn');
  if (btn) {
    btn.innerHTML = audioEnabled
      ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16 9a4 4 0 0 1 0 6"/></svg><span>Sound: ON</span>'
      : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M17 9l4 6M21 9l-4 6"/></svg><span>Sound: OFF</span>';
    btn.classList.toggle('active', audioEnabled);
  }
}

function playBrowserAlarm(isCritical) {
  if (!audioEnabled) return;
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    const t = audioCtx.currentTime;
    const tones = isCritical ? [880, 1175] : [659, 880];
    const dur = isCritical ? 0.35 : 0.55;

    tones.forEach((freq, idx) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      const startTime = t + (idx * 0.12);

      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, startTime);
      gain.gain.setValueAtTime(0.09, startTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, startTime + dur);

      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(startTime);
      osc.stop(startTime + dur);
    });
  } catch(e) {
    console.debug('Audio error:', e);
  }
}

// ── Live update ────────────────────────────────────────────
async function update(){
  try{
    const res=await fetch('/api/status',{cache:'no-store'});
    const data=await res.json();
    const unit=data[UPS_ID];
    if(unit&&unit.ups){
      updateMetrics(unit.ups);
      if(unit.ups_rating)renderRating(unit.ups_rating,unit.ups_info||{});

      // Sound trigger
      const isCritical = Boolean(unit.ups.battery_low || unit.ups.ups_failed);
      const isWarning = Boolean(unit.ups.utility_fail || unit.ups.beeper_sounding);
      if (isCritical) {
        playBrowserAlarm(true);
      } else if (isWarning) {
        playBrowserAlarm(false);
      }
    }
  }catch(e){console.error(e)}
}

// ── Boot ───────────────────────────────────────────────────
updateClock();
update();
loadChart(6);
loadBattChart(6);
setInterval(updateClock,1000);
setInterval(update,3000);
</script>
</body>
</html>"""