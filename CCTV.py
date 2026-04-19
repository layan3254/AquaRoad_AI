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

# --- 4. Alert Function ---
def send_telegram_alert(source_option, time_now):
    token = "8524001645:AAFCZbanUp8kJVKxoV0SGkMWYSVGw1kD9Wo"
    chat_id = "954637036"
    raw_message = f"Latest Report Sent:\nSource: {source_option}\nTime: {time_now}"
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(raw_message)}"
    try:
        requests.get(url, timeout=5)
    except:
        pass

# --- 5. Session State Initialization ---
if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = 0
if 'last_report_html' not in st.session_state:
    st.session_state.last_report_html = ""
if 'is_running' not in st.session_state:
    st.session_state.is_running = False

# --- 6. Model Loading ---
@st.cache_resource
def load_model():
    return YOLO('best.pt')

model = load_model()

# ---------------------------------------------------------------
# VIDEO SOURCE ROUTING
# Replace the RTSP URLs below with your actual camera stream URLs.
# Format: rtsp://username:password@ip_address:port/stream_path
# For local webcam testing use integer 0 (Trial Stream).
# ---------------------------------------------------------------
CAMERA_SOURCES = {
    "Camera #402": "rtsp://USERNAME:PASSWORD@CAMERA_402_IP:PORT/stream",
    "Camera #105": "rtsp://USERNAME:PASSWORD@CAMERA_105_IP:PORT/stream",
    "Trial Stream": 0,
}

CAMERA_LOCATIONS = {
    "Camera #402": ("Al-Hada District, Riyadh",  "24.71 N, 46.67 E"),
    "Camera #105": ("Al-Malqa District, Riyadh", "24.82 N, 46.61 E"),
    "Trial Stream": ("Test Zone, Riyadh",         "00.00 N, 00.00 E"),
}

# --- 7. Top Header ---
st.markdown('<h1 class="main-title">AQUA-ROAD</h1>', unsafe_allow_html=True)
st.markdown('<p style="color: #003527; font-size: 14px; margin-top:-10px; font-weight:bold;">Automated Water Accumulation Monitoring System</p>', unsafe_allow_html=True)
st.divider()

# --- 8. Sidebar ---
with st.sidebar:
    st.markdown('<h3>SETTINGS</h3>', unsafe_allow_html=True)
    source_option = st.selectbox("CHOOSE SOURCE", list(CAMERA_SOURCES.keys()))
    threshold = st.slider("CONFIDENCE", 0.0, 1.0, 0.5)
    iou_val   = st.slider("IoU THRESHOLD", 0.0, 1.0, 0.45)
    st.markdown("---")

    if st.session_state.is_running:
        if st.button("Stop Monitoring", use_container_width=True):
            st.session_state.is_running = False
            st.rerun()
    else:
        if st.button("Start Monitoring", use_container_width=True):
            st.session_state.is_running = True
            st.rerun()

# --- 9. Main Content Layout ---
col_video, col_info = st.columns([2, 1])

with col_video:
    st.markdown('<p style="font-weight:bold; color:#5E5E5E;">Live Monitoring Feed</p>', unsafe_allow_html=True)
    st_frame = st.empty()

with col_info:
    st.markdown('<p style="font-weight:bold; color:#5E5E5E;">Control & Monitoring Panel</p>', unsafe_allow_html=True)
    status_indicator = st.empty()

    location_name, coordinates = CAMERA_LOCATIONS[source_option]
    st.markdown(f"""
        <div class="metric-card">
            <div style="font-size: 10px; color: gray; font-weight: bold; text-transform: uppercase;">Exact Location</div>
            <div style="font-weight:bold; font-size:14px; color:#1A1C1A;">{location_name}</div>
            <div style="font-size: 11px; color: #474747;">{coordinates}</div>
        </div>
    """, unsafe_allow_html=True)

    alert_log_placeholder = st.empty()

# --- 10. Idle State ---
if not st.session_state.is_running:
    st_frame.info("Press Start Monitoring in the sidebar to begin the live feed.")
    status_indicator.info("Monitoring is paused.")
    if st.session_state.last_report_html:
        alert_log_placeholder.markdown(st.session_state.last_report_html, unsafe_allow_html=True)
    st.stop()

# --- 11. Open Video Source ---
video_source = CAMERA_SOURCES[source_option]
cap = cv2.VideoCapture(video_source)

if not cap.isOpened():
    st.error(
        f"Cannot open source: {source_option}\n\n"
        "Possible reasons:\n"
        "- For Camera #402 / #105: the RTSP URL, username, password, or IP in CAMERA_SOURCES is incorrect.\n"
        "- For Trial Stream: no webcam is connected to this machine.\n\n"
        "Please update the CAMERA_SOURCES dictionary in CCTV.py with the correct stream URLs."
    )
    st.session_state.is_running = False
    st.stop()

# --- 12. Live Detection Loop ---
status_indicator.warning("Connecting to stream...")

try:
    while st.session_state.is_running:
        ret, frame = cap.read()

        if not ret:
            status_indicator.error("Stream lost or video ended. Retrying in 2s...")
            time.sleep(2)
            cap.release()
            cap = cv2.VideoCapture(video_source)
            continue

        results = model.predict(frame, conf=threshold, iou=iou_val)

        current_labels = [
            model.names[int(box.cls[0])].lower()
            for box in results[0].boxes
        ]
        is_danger = any(
            label in current_labels
            for label in ["pond", "water", "flood", "puddle"]
        )

        annotated = cv2.cvtColor(results[0].plot(), cv2.COLOR_BGR2RGB)
        st_frame.image(annotated, use_container_width=True)

        if is_danger:
            status_indicator.error("ALERT: Water Accumulation Detected")
            current_time = time.time()

            if current_time - st.session_state.last_alert_time > 600:
                time_now = datetime.datetime.now().strftime('%H:%M:%S')
                send_telegram_alert(source_option, time_now)
                save_report_to_db(source_option, "Detected")
                st.session_state.last_alert_time = current_time

                st.session_state.last_report_html = f"""
                    <div class="metric-card" style="border-left-color: #ba1a1a;">
                        <b style="color:#ba1a1a;">Latest Archived Report:</b><br>
                        <span class="details-text">Source: {source_option}</span><br>
                        <span class="details-text">Time: {time_now}</span><br>
                        <span style="color:green; font-weight:bold; font-size:13px;">Reported and Saved Successfully</span>
                    </div>
                """
                st.toast(f'Alert Saved: {source_option}')
        else:
            status_indicator.success("SYSTEM STATUS: Road is Clear")

        if st.session_state.last_report_html:
            alert_log_placeholder.markdown(
                st.session_state.last_report_html, unsafe_allow_html=True
            )

finally:
    cap.release()
