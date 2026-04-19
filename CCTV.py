import streamlit as st
import cv2
from ultralytics import YOLO
import numpy as np
import requests
import datetime
import time
import urllib.parse
import sqlite3

# --- 1. Page Configuration ---
st.set_page_config(
    page_title="AQUA-ROAD | Autonomous Monitoring",
    layout="wide"
)

# --- 2. Interface Customization (CSS) ---
st.markdown("""
    <style>
    .stApp { background-color: #FAF9F6; }
    [data-testid="stSidebar"] { background-color: #003527 !important; }
    [data-testid="stSidebar"] .stMarkdown p, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h3 {
        color: white !important;
    }
    .main-title {
        font-family: 'Manrope', sans-serif;
        font-weight: 800;
        color: #003527 !important;
        text-transform: uppercase;
    }
    .metric-card {
        background-color: #ffffff;
        padding: 20px;
        border-left: 5px solid #003527;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 15px;
    }
    .details-text { color: #474747 !important; font-size: 13px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. Database Management ---
def init_db():
    conn = sqlite3.connect('aqua_road.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS reports 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, time TEXT, source TEXT, status TEXT)''')
    conn.commit()
    conn.close()

def save_report_to_db(source, status):
    conn = sqlite3.connect('aqua_road.db')
    c = conn.cursor()
    now = datetime.datetime.now()
    c.execute("INSERT INTO reports (date, time, source, status) VALUES (?, ?, ?, ?)",
              (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), source, status))
    conn.commit()
    conn.close()

init_db()

# --- 4. Alert Function & Session State ---
def send_telegram_alert(source_option, time_now):
    token = "8524001645:AAFCZbanUp8kJVKxoV0SGkMWYSVGw1kD9Wo"
    chat_id = "954637036"
    raw_message = f"Latest Report Sent:\nSource: {source_option}\nTime: {time_now}"
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(raw_message)}"
    try:
        requests.get(url, timeout=5)
    except:
        pass

if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = 0

if 'last_report_html' not in st.session_state:
    st.session_state.last_report_html = ""

if 'running' not in st.session_state:
    st.session_state.running = False

# --- 5. Model Loading ---
@st.cache_resource
def load_model():
    return YOLO('best.pt')

model = load_model()

# --- 6. Top Header ---
st.markdown('<h1 class="main-title">🌊 AQUA-ROAD</h1>', unsafe_allow_html=True)
st.markdown('<p style="color: #003527; font-size: 14px; margin-top:-10px; font-weight:bold;">Automated Water Accumulation Monitoring System</p>', unsafe_allow_html=True)
st.divider()

# --- 7. Sidebar ---
with st.sidebar:
    st.markdown('<h3>⚙️ SETTINGS</h3>', unsafe_allow_html=True)

    source_option = st.selectbox("CHOOSE SOURCE", ("Camera #402", "Camera #105", "Trial Stream"))
    threshold = st.slider("CONFIDENCE", 0.0, 1.0, 0.5)
    iou_val = st.slider("IoU THRESHOLD", 0.0, 1.0, 0.45)

    st.markdown("---")

    # ── FIX: "Trial Stream" lets the user paste any RTSP/HTTP URL ──
    trial_url = ""
    if source_option == "Trial Stream":
        trial_url = st.text_input(
            "Stream URL (RTSP / HTTP)",
            placeholder="rtsp://user:pass@192.168.1.1:554/stream"
        )

    # ── Start / Stop controls ──
    col_start, col_stop = st.columns(2)
    with col_start:
        if st.button("▶ Start", use_container_width=True):
            st.session_state.running = True
    with col_stop:
        if st.button("⏹ Stop", use_container_width=True):
            st.session_state.running = False

# --- 8. Source → OpenCV index or URL mapping ---
# FIX: Each camera name maps to a real device index or stream URL.
# Change index 0 / 1 to match your physical camera ports.
SOURCE_MAP = {
    "Camera #402": 0,        # change to RTSP URL if it's a network camera
    "Camera #105": 1,        # change to RTSP URL if it's a network camera
    "Trial Stream": trial_url if source_option == "Trial Stream" else "",
}

# --- 9. Main Content ---
col_video, col_info = st.columns([2, 1])

with col_video:
    st.markdown('<p style="font-weight:bold; color:#5E5E5E;">Live Monitoring Feed</p>', unsafe_allow_html=True)
    st_frame = st.empty()

with col_info:
    st.markdown('<p style="font-weight:bold; color:#5E5E5E;">Control & Monitoring Panel</p>', unsafe_allow_html=True)
    status_indicator = st.empty()

    if source_option == "Camera #402":
        location_name, coordinates = "Al-Hada District, Riyadh", "24.71°N, 46.67°E"
    elif source_option == "Camera #105":
        location_name, coordinates = "Al-Malqa District, Riyadh", "24.82°N, 46.61°E"
    else:
        location_name, coordinates = "Test Zone, Riyadh", "00.00°N, 00.00°E"

    st.markdown(f"""
        <div class="metric-card">
            <div style="font-size: 10px; color: gray; font-weight: bold; text-transform: uppercase;">Exact Location</div>
            <div style="font-weight:bold; font-size:14px; color:#1A1C1A;">{location_name}</div>
            <div style="font-size: 11px; color: #474747;">{coordinates}</div>
        </div>
    """, unsafe_allow_html=True)

    alert_log_placeholder = st.empty()

# --- 10. Processing Execution ---
if not st.session_state.running:
    status_indicator.info("⏸ Press ▶ Start in the sidebar to begin monitoring.")
else:
    video_source = SOURCE_MAP[source_option]

    # FIX: Guard against empty Trial Stream URL
    if source_option == "Trial Stream" and not video_source:
        status_indicator.warning("⚠️ Please enter a stream URL in the sidebar before starting.")
        st.stop()

    cap = cv2.VideoCapture(video_source)

    # FIX: Explicit camera-open check with a clear error message
    if not cap.isOpened():
        status_indicator.error(
            f"❌ Cannot open source: *{source_option}* "
            f"(index/URL: {video_source}). "
            "Check that the camera is connected and not used by another app."
        )
        st.session_state.running = False
        st.stop()

    # FIX: MJPEG backend hint — improves stability for many USB webcams
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    while st.session_state.running:
        ret, frame = cap.read()

        # FIX: Retry a few times before giving up (handles transient frame drops)
        if not ret:
            for _ in range(5):
                ret, frame = cap.read()
                if ret:
                    break
                time.sleep(0.1)

        if not ret:
            status_indicator.error(
                "❌ Lost connection to the camera feed. "
                "Check the cable / network and press ▶ Start again."
            )
            break

        results = model.predict(frame, conf=threshold, iou=iou_val)

        current_labels = [model.names[int(box.cls[0])].lower() for box in results[0].boxes]
        is_danger = any(label in current_labels for label in ["pond", "water", "flood", "puddle"])

        st_frame.image(
            cv2.cvtColor(results[0].plot(), cv2.COLOR_BGR2RGB),
            use_container_width=True
        )

        if is_danger:
            status_indicator.error("🚨 ALERT: Water Accumulation Detected")
            current_time = time.time()

            if current_time - st.session_state.last_alert_time > 600:
                time_now = datetime.datetime.now().strftime('%H:%M:%S')
                send_telegram_alert(source_option, time_now)
                save_report_to_db(source_option, "Detected")
                st.session_state.last_alert_time = current_time

                st.session_state.last_report_html = f"""
                    <div class="metric-card" style="border-left-color: #ba1a1a;">
                        <b style="color:#ba1a1a;">📅 Latest Archived Report:</b><br>
                        <span class="details-text">Source: {source_option}</span><br>
                        <span class="details-text">Time: {time_now}</span><br>
                        <span style="color:green; font-weight:bold; font-size:13px;">✓ Reported & Saved Successfully</span>
                    </div>
                """
                st.toast(f'Alert Saved: {source_option}')
        else:
            status_indicator.success("✔️ SYSTEM STATUS: Road is Clear")

        if st.session_state.last_report_html:
            alert_log_placeholder.markdown(st.session_state.last_report_html, unsafe_allow_html=True)

    cap.release()
