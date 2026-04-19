import streamlit as st
import cv2
from ultralytics import YOLO
import numpy as np
import requests
import datetime
import time
import urllib.parse
import sqlite3
import pandas as pd
import tempfile
import av # ضروري لمعالجة إطارات الفيديو في WebRTC
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, WebRtcMode

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
    raw_message = f"🚨 AQUA-ROAD ALERT:\nSource: {source_option}\nTime: {time_now}\nStatus: Water Accumulation Detected"
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(raw_message)}"
    try:
        requests.get(url, timeout=5)
    except:
        pass

if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = 0
if 'last_report_html' not in st.session_state:
    st.session_state.last_report_html = ""

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
    input_type = st.radio("SELECT INPUT MODE", ["Live Camera (WebRTC)", "Upload Video", "Upload Image"])
    source_option = st.selectbox("LOCATION TAG", ("Camera #402", "Camera #105", "Test Unit"))
    threshold = st.slider("CONFIDENCE", 0.0, 1.0, 0.5)
    iou_val = st.slider("IoU THRESHOLD", 0.0, 1.0, 0.45)

# --- 8. Page Tabs (The Dashboard Logic) ---
tab1, tab2 = st.tabs(["🎥 Real-time Monitoring", "📊 Analytics Dashboard"])

with tab1:
    col_video, col_info = st.columns([2, 1])

    with col_video:
        st.markdown('<p style="font-weight:bold; color:#5E5E5E;">Visual Intelligence Feed</p>', unsafe_allow_html=True)
        
        # --- CASE A: Live Camera (WebRTC) ---
        if input_type == "Live Camera (WebRTC)":
            class VideoProcessor(VideoProcessorBase):
                def recv(self, frame):
                    img = frame.to_ndarray(format="bgr24")
                    results = model.predict(img, conf=threshold, iou=iou_val)
                    annotated_frame = results[0].plot()
                    
                    # Logic to trigger alert based on labels
                    current_labels = [model.names[int(box.cls[0])].lower() for box in results[0].boxes]
                    if any(label in current_labels for label in ["pond", "water", "flood", "puddle"]):
                        # Note: Complex UI updates inside WebRTC are limited, we rely on annotated frame
                        pass
                    
                    return av.VideoFrame.from_ndarray(annotated_frame, format="bgr24")

            webrtc_streamer(
                key="aqua-road-live",
                mode=WebRtcMode.SENDRECV,
                video_processor_factory=VideoProcessor,
                rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
                media_stream_constraints={"video": True, "audio": False},
            )

        # --- CASE B: Upload Video ---
        elif input_type == "Upload Video":
            uploaded_video = st.file_uploader("Upload MP4/AVI", type=['mp4', 'avi', 'mov'])
            if uploaded_video:
                tfile = tempfile.NamedTemporaryFile(delete=False)
                tfile.write(uploaded_video.read())
                cap = cv2.VideoCapture(tfile.name)
                st_frame = st.empty()
                
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret: break
                    results = model.predict(frame, conf=threshold, iou=iou_val)
                    st_frame.image(cv2.cvtColor(results[0].plot(), cv2.COLOR_BGR2RGB), use_container_width=True)
                    
                    # Alert Logic
                    current_labels = [model.names[int(box.cls[0])].lower() for box in results[0].boxes]
                    if any(label in current_labels for label in ["pond", "water", "flood", "puddle"]):
                        curr_time = time.time()
                        if curr_time - st.session_state.last_alert_time > 600:
                            time_now = datetime.datetime.now().strftime('%H:%M:%S')
                            send_telegram_alert(source_option, time_now)
                            save_report_to_db(source_option, "Hazard Detected")
                            st.session_state.last_alert_time = curr_time
                            st.toast("🚨 Incident Reported!")
                cap.release()

        # --- CASE C: Upload Image ---
        elif input_type == "Upload Image":
            uploaded_img = st.file_uploader("Upload Road Image", type=['jpg', 'jpeg', 'png'])
            if uploaded_img:
                file_bytes = np.asarray(bytearray(uploaded_img.read()), dtype=np.uint8)
                image = cv2.imdecode(file_bytes, 1)
                results = model.predict(image, conf=threshold)
                st.image(cv2.cvtColor(results[0].plot(), cv2.COLOR_BGR2RGB), caption="Analysis Result")

    with col_info:
        st.markdown('<p style="font-weight:bold; color:#5E5E5E;">Location Details</p>', unsafe_allow_html=True)
        if source_option == "Camera #402":
            loc, coords = "Al-Hada District, Riyadh", "24.71°N, 46.67°E"
        elif source_option == "Camera #105":
            loc, coords = "Al-Malqa District, Riyadh", "24.82°N, 46.61°E"
        else:
            loc, coords = "Mobile Unit", "Live GPS Coordinates"

        st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 10px; color: gray; font-weight: bold; text-transform: uppercase;">Exact Location</div>
                <div style="font-weight:bold; font-size:14px; color:#1A1C1A;">{loc}</div>
                <div style="font-size: 11px; color: #474747;">{coords}</div>
            </div>
        """, unsafe_allow_html=True)
        
        # Display the persistent alert log
        if st.session_state.last_report_html:
            st.markdown(st.session_state.last_report_html, unsafe_allow_html=True)

with tab2:
    st.markdown('<h3 style="color:#003527;">📊 Historical Incident Reports</h3>', unsafe_allow_html=True)
    
    # Connect to DB and show results
    try:
        conn = sqlite3.connect('aqua_road.db')
        df = pd.read_sql_query("SELECT * FROM reports ORDER BY id DESC", conn)
        conn.close()
        
        if not df.empty:
            col1, col2 = st.columns([2, 1])
            with col1:
                st.dataframe(df, use_container_width=True)
            with col2:
                st.metric("Total Incidents", len(df))
                st.info("The dashboard above updates in real-time as hazards are detected by the YOLOv8 model.")
        else:
            st.write("No incidents archived yet. Monitoring is active.")
    except:
        st.warning("Database is initializing...")
