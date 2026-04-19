"""
AQUA-ROAD | Live CCTV Monitoring
Run the whole app with:  streamlit run CCTV.py
The Dashboard page lives in pages/Dashboard.py and shares aqua_road.db
"""

import streamlit as st
import cv2
from ultralytics import YOLO
import numpy as np
import requests
import datetime
import time
import urllib.parse
import sqlite3
import os

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AQUA-ROAD | Live Monitor",
    page_icon="🌊",
    layout="wide",
)

# ── Shared DB path (both pages use this) ─────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "aqua_road.db")

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap');

.stApp { background-color: #FAF9F6; font-family: 'Manrope', sans-serif; }

[data-testid="stSidebar"] { background-color: #003527 !important; }
[data-testid="stSidebar"] *,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div { color: #ffffff !important; }
[data-testid="stSidebar"] .stSlider [data-testid="stMarkdownContainer"] p { color: #ffffff !important; }

.main-title {
    font-family: 'Manrope', sans-serif;
    font-weight: 800;
    color: #003527 !important;
    text-transform: uppercase;
    letter-spacing: 2px;
    font-size: 2.2rem;
    margin-bottom: 0;
}
.subtitle {
    color: #003527 !important;
    font-size: 13px;
    font-weight: 600;
    margin-top: -4px;
    letter-spacing: 1px;
    text-transform: uppercase;
}
.metric-card {
    background-color: #ffffff;
    padding: 18px 20px;
    border-left: 5px solid #003527;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    margin-bottom: 14px;
    border-radius: 0 6px 6px 0;
}
.metric-card-danger { border-left-color: #ba1a1a !important; }
.card-label { font-size: 10px; color: #888; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }
.card-value { font-weight: 700; font-size: 15px; color: #1A1C1A; margin-top: 2px; }
.card-sub   { font-size: 11px; color: #474747; margin-top: 1px; }

.sev-badge {
    display: inline-block;
    padding: 3px 14px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: white;
}
</style>
""", unsafe_allow_html=True)

# ── Database helpers ──────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS reports (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        date    TEXT,
        time    TEXT,
        source  TEXT,
        status  TEXT,
        severity TEXT DEFAULT 'N/A',
        classes  TEXT DEFAULT ''
    )""")
    conn.commit()
    conn.close()

def save_report(source, status, severity="Detected", classes=""):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.datetime.now()
    conn.execute(
        "INSERT INTO reports (date, time, source, status, severity, classes) VALUES (?,?,?,?,?,?)",
        (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), source, status, severity, classes)
    )
    conn.commit()
    conn.close()

init_db()

# ── Telegram alert ────────────────────────────────────────────────────────────
def send_telegram(token, chat_id, source, severity, classes, frame=None):
    if not token or not chat_id:
        return
    msg = (
        f"🚨 AQUA-ROAD ALERT\n"
        f"📍 Source   : {source}\n"
        f"⚠️  Severity : {severity}\n"
        f"🔍 Detected : {classes}\n"
        f"🕐 Time     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    base = f"https://api.telegram.org/bot{token}"
    try:
        if frame is not None:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            requests.post(
                f"{base}/sendPhoto",
                data={"chat_id": chat_id, "caption": msg},
                files={"photo": ("snap.jpg", buf.tobytes(), "image/jpeg")},
                timeout=8,
            )
        else:
            requests.get(
                f"{base}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(msg)}",
                timeout=8,
            )
    except Exception:
        pass

# ── Model loading ─────────────────────────────────────────────────────────────
@st.cache_resource
def load_model(path):
    return YOLO(path)

# ── Severity scoring ──────────────────────────────────────────────────────────
HAZARD_CLASSES  = {"pond", "water", "flood", "puddle", "pool", "waterlog"}
SEVERITY_WEIGHT = {"puddle": 1, "water": 2, "pool": 2, "pond": 3, "waterlog": 3, "flood": 4}
SEV_LEVELS = [
    (0,  "CLEAR",    "#2e7d32"),
    (1,  "LOW",      "#f9a825"),
    (3,  "MODERATE", "#e65100"),
    (5,  "HIGH",     "#b71c1c"),
    (99, "CRITICAL", "#6a1b9a"),
]

def get_severity(hazard_cls_list):
    score = sum(SEVERITY_WEIGHT.get(c, 1) for c in hazard_cls_list)
    for threshold, label, color in SEV_LEVELS:
        if score <= threshold:
            return label, color, score
    return "CRITICAL", "#6a1b9a", score

# ── Camera source map ─────────────────────────────────────────────────────────
CAMERA_META = {
    "Camera #402": ("Al-Hada District, Riyadh",  "24.71°N, 46.67°E", 0),
    "Camera #105": ("Al-Malqa District, Riyadh", "24.82°N, 46.61°E", 1),
    "Trial Stream": ("Test Zone, Riyadh",         "00.00°N, 00.00°E", "demo"),
}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ SETTINGS")
    source_option = st.selectbox("CHOOSE SOURCE", list(CAMERA_META.keys()))
    threshold     = st.slider("CONFIDENCE THRESHOLD", 0.0, 1.0, 0.50, 0.05)
    iou_val       = st.slider("IoU THRESHOLD",        0.0, 1.0, 0.45, 0.05)
    confirm_n     = st.slider("CONFIRM FRAMES (anti-flicker)", 1, 10, 3)
    cooldown_sec  = st.slider("ALERT COOLDOWN (s)",   60, 1800, 600, 60)
    use_roi       = st.checkbox("Enable ROI (ignore top 25%)", value=True)

    st.markdown("---")
    st.markdown("**Telegram Alerts**")
    tg_token   = st.text_input("Bot Token",  value="8524001645:AAFCZbanUp8kJVKxoV0SGkMWYSVGw1kD9Wo", type="password")
    tg_chat_id = st.text_input("Chat ID",    value="954637036")
    send_snap  = st.checkbox("Send snapshot with alert", value=True)

# ── Header ────────────────────────────────────────────────────────────────────
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown('<h1 class="main-title">🌊 AQUA-ROAD</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Automated Water Accumulation Monitoring System</p>', unsafe_allow_html=True)
with c2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Restart Feed", use_container_width=True):
        st.rerun()
st.divider()

# ── Layout ────────────────────────────────────────────────────────────────────
col_video, col_info = st.columns([2, 1])
location_name, coordinates, cam_index = CAMERA_META[source_option]

with col_video:
    st.markdown('<p style="font-weight:700; color:#5E5E5E; font-size:13px; text-transform:uppercase; letter-spacing:1px;">Live Monitoring Feed</p>', unsafe_allow_html=True)
    feed_placeholder   = st.empty()
    feed_msg_placeholder = st.empty()

with col_info:
    st.markdown('<p style="font-weight:700; color:#5E5E5E; font-size:13px; text-transform:uppercase; letter-spacing:1px;">Control & Monitoring Panel</p>', unsafe_allow_html=True)
    status_placeholder  = st.empty()
    badge_placeholder   = st.empty()

    st.markdown(f"""
    <div class="metric-card">
        <div class="card-label">Exact Location</div>
        <div class="card-value">{location_name}</div>
        <div class="card-sub">{coordinates}</div>
    </div>
    """, unsafe_allow_html=True)

    report_placeholder = st.empty()

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [("last_alert_time", 0), ("last_report_html", ""),
             ("frame_buf", []), ("hazard_start", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Model ─────────────────────────────────────────────────────────────────────
model_path = os.path.join(os.path.dirname(__file__), "best.pt")
if not os.path.exists(model_path):
    st.error(f"❌ Model file not found: {model_path}")
    st.stop()

model = load_model(model_path)

# ── ROI helper ────────────────────────────────────────────────────────────────
def apply_roi(frame):
    if not use_roi:
        return frame, None
    h, w = frame.shape[:2]
    y1 = int(0.25 * h)
    masked = frame.copy()
    masked[:y1, :] = 0
    return masked, (0, y1, w, h)

# ── Demo frame generator (when no camera) ────────────────────────────────────
def make_demo_frame(tick):
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[:] = (30, 50, 30)
    cv2.putText(img, "DEMO MODE — No Camera Connected", (60, 200),
                cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 220, 180), 2)
    cv2.putText(img, "Connect a webcam and select Camera #402 / #105", (30, 250),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)
    cv2.putText(img, datetime.datetime.now().strftime("%H:%M:%S"), (270, 340),
                cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 200, 100), 2)
    return img

# ── Open camera ───────────────────────────────────────────────────────────────
is_demo = (cam_index == "demo")

if not is_demo:
    cap = cv2.VideoCapture(cam_index)
    # Try alternative indices if the selected one fails
    if not cap.isOpened():
        for idx in [0, 1, 2]:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                feed_msg_placeholder.info(f"ℹ️ Camera #{cam_index} unavailable — using device index {idx}")
                break
    if not cap.isOpened():
        is_demo = True
        feed_msg_placeholder.warning(
            "⚠️ No physical camera found. Running in **Demo Mode** — YOLO detection still active on simulated frames. "
            "Connect a USB/webcam and restart."
        )

# ── Main processing loop ──────────────────────────────────────────────────────
MAX_FRAMES = 100_000   # prevent infinite loop in Streamlit cloud

for _tick in range(MAX_FRAMES):

    # ── Grab frame ────────────────────────────────────────────────────────────
    if is_demo:
        frame = make_demo_frame(_tick)
        time.sleep(0.05)
    else:
        ret, frame = cap.read()
        if not ret:
            feed_msg_placeholder.warning("⚠️ Lost camera feed. Retrying…")
            time.sleep(0.5)
            continue

    # ── ROI ───────────────────────────────────────────────────────────────────
    masked_frame, roi_coords = apply_roi(frame)

    # ── YOLO inference ────────────────────────────────────────────────────────
    results     = model.predict(masked_frame, conf=threshold, iou=iou_val, verbose=False)
    yolo_result = results[0]

    all_labels  = [model.names[int(b.cls[0])].lower() for b in yolo_result.boxes]
    hazard_cls  = [l for l in all_labels if l in HAZARD_CLASSES]
    raw_hazard  = len(hazard_cls) > 0

    # ── Frame-buffer confirmation ─────────────────────────────────────────────
    st.session_state.frame_buf.append(raw_hazard)
    if len(st.session_state.frame_buf) > confirm_n:
        st.session_state.frame_buf.pop(0)
    confirmed_hazard = (
        len(st.session_state.frame_buf) == confirm_n
        and all(st.session_state.frame_buf)
    )

    # ── Severity ──────────────────────────────────────────────────────────────
    if confirmed_hazard:
        sev_label, sev_color, sev_score = get_severity(hazard_cls)
    else:
        sev_label, sev_color, sev_score = "CLEAR", "#2e7d32", 0

    # ── Annotate frame ────────────────────────────────────────────────────────
    annotated = yolo_result.plot()
    h, w = annotated.shape[:2]

    # Status banner
    banner_overlay = annotated.copy()
    banner_color   = tuple(int(sev_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    banner_bgr     = (banner_color[2], banner_color[1], banner_color[0])
    cv2.rectangle(banner_overlay, (0, 0), (w, 38), banner_bgr, -1)
    cv2.addWeighted(banner_overlay, 0.55, annotated, 0.45, 0, annotated)
    cv2.putText(annotated,
                f"STATUS: {sev_label}  |  Score: {sev_score}  |  {source_option}",
                (10, 25), cv2.FONT_HERSHEY_DUPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    # Timestamp bottom-right
    ts = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    cv2.putText(annotated, ts, (w - 230, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (210, 210, 210), 1, cv2.LINE_AA)

    # ROI outline
    if roi_coords:
        cv2.rectangle(annotated, (roi_coords[0], roi_coords[1]),
                      (roi_coords[2], roi_coords[3]), (0, 255, 255), 2)
        cv2.putText(annotated, "ROI", (roi_coords[0]+6, roi_coords[1]+18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)

    # ── Display ───────────────────────────────────────────────────────────────
    feed_placeholder.image(
        cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB),
        use_container_width=True,
    )

    # ── Status panel ─────────────────────────────────────────────────────────
    if confirmed_hazard:
        status_placeholder.error(f"🚨 ALERT: Water Accumulation Detected")
        badge_placeholder.markdown(
            f'<span class="sev-badge" style="background:{sev_color};">'
            f'Severity: {sev_label} &nbsp;|&nbsp; Score: {sev_score}'
            f'</span>',
            unsafe_allow_html=True,
        )
        st.session_state.hazard_start = st.session_state.hazard_start or time.time()

        # ── Alert + DB write (respecting cooldown) ────────────────────────────
        now_ts = time.time()
        if now_ts - st.session_state.last_alert_time > cooldown_sec:
            classes_str = ", ".join(set(hazard_cls)) or "Unknown"
            time_str    = datetime.datetime.now().strftime("%H:%M:%S")

            save_report(source_option, "Detected", sev_label, classes_str)

            snap = annotated if send_snap else None
            send_telegram(tg_token, tg_chat_id, source_option, sev_label, classes_str, snap)

            st.session_state.last_alert_time = now_ts
            st.session_state.last_report_html = f"""
            <div class="metric-card metric-card-danger">
                <div class="card-label" style="color:#ba1a1a;">📅 Latest Archived Report</div>
                <div class="card-sub" style="margin-top:6px;">
                    <b>Source:</b> {source_option}<br>
                    <b>Time:</b> {time_str}<br>
                    <b>Detected:</b> {classes_str}<br>
                    <b>Severity:</b> <span style="color:{sev_color}; font-weight:700;">{sev_label}</span>
                </div>
                <div style="color:#2e7d32; font-weight:700; font-size:12px; margin-top:8px;">
                    ✓ Saved to Database &amp; Alert Sent
                </div>
            </div>
            """
            st.toast(f"🚨 Alert saved — {source_option} [{sev_label}]")

    else:
        st.session_state.hazard_start = None
        status_placeholder.success("✔️ SYSTEM STATUS: Road is Clear")
        badge_placeholder.empty()

    if st.session_state.last_report_html:
        report_placeholder.markdown(st.session_state.last_report_html, unsafe_allow_html=True)

# ── Cleanup ───────────────────────────────────────────────────────────────────
if not is_demo and "cap" in dir():
    cap.release()
