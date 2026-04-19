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
import av
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, WebRtcMode

# --- 1. Page Configuration ---
st.set_page_config(
    page_title="AQUA-ROAD | System",
    layout="wide"
)

# --- 2. Interface Customization (CSS) ---
st.markdown("""
    <style>
    .stApp { background-color: #FAF9F6 !important; }
    [data-testid="stSidebar"] { background-color: #003527 !important; }
    [data-testid="stSidebar"] * { color: white !important; }
    .main-title { font-family: 'Manrope', sans-serif; font-weight: 800; color: #003527 !important; text-transform: uppercase; }
    .metric-card { background-color: #ffffff; padding: 20px; border-left: 5px solid #003527; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 15px; }
    /* Dashboard Table Styling */
    .stTable td { color: #333333 !important; font-weight: 500; }
    .stTable th { background-color: #E8E8E8 !important; color: #003527 !important; }
    /* تغميق نصوص السايد بار */
    .sidebar-bold { font-weight: bold; font-size: 16px; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. Database Functions ---
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

# --- 4. Alert Logic ---
def send_telegram_alert(source_option, time_now):
    token = "8524001645:AAFCZbanUp8kJVKxoV0SGkMWYSVGw1kD9Wo" 
    chat_id = "954637036"
    raw_message = f"🚨 AQUA-ROAD ALERT:\nSource: {source_option}\nTime: {time_now}\nStatus: Hazard Detected"
    url = f"https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={urllib.parse.quote(raw_message)}"
    try:
        requests.get(url, timeout=5)
    except: pass

@st.cache_resource
def load_model():
    return YOLO('best.pt')

model = load_model()

# Session States لضمان بقاء التقارير والرسائل
if 'last_alert_time' not in st.session_state: st.session_state.last_alert_time = 0
if 'last_report_html' not in st.session_state: st.session_state.last_report_html = ""

# --- 5. Main UI Layout ---
st.markdown('<h1 class="main-title">🌊 AQUA-ROAD AI</h1>', unsafe_allow_html=True)

# الـ Tabs لدمج الداشبورد
tab1, tab2 = st.tabs(["🎥 LIVE MONITORING", "📊 ANALYTICS DASHBOARD"])

# --- 7. Sidebar ---
with st.sidebar:
    st.markdown('<h3>⚙️ SETTINGS</h3>', unsafe_allow_html=True)
    # جعل اسم الكاميرا غامق باستخدام Markdown
    st.markdown('<p class="sidebar-bold">DEVICE SELECTION</p>', unsafe_allow_html=True)
    source_option = st.selectbox("", ("Camera #402", "Camera #105", "Test Unit"), label_visibility="collapsed")
    
    st.markdown('<p class="sidebar-bold">INPUT MODE</p>', unsafe_allow_html=True)
    mode = st.radio("", ["Live Web-Camera", "Upload Video File"], label_visibility="collapsed")
    
    threshold = st.slider("Confidence Threshold", 0.0, 1.0, 0.5)
    iou_val = st.slider("IoU Threshold", 0.0, 1.0, 0.45)

# --- TAB 1: LIVE MONITORING ---
with tab1:
    col_vid, col_data = st.columns([2, 1])
    
    with col_vid:
        if mode == "Live Web-Camera":
            st.info("💡 If camera doesn't start, please check browser permissions or use HTTPS.")
            
            # محرك الكاميرا الحية
            webrtc_streamer(
                key="aqua-cam-v3",
                mode=WebRtcMode.SENDRECV,
                rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
                video_frame_callback=lambda frame: av.VideoFrame.from_ndarray(
                    model.predict(frame.to_ndarray(format="bgr24"), conf=threshold, iou=iou_val)[0].plot(), 
                    format="bgr24"
                ),
                media_stream_constraints={"video": True, "audio": False},
                async_processing=True,
            )
        
        else:
            uploaded_file = st.file_uploader("Upload Video for Analysis", type=['mp4', 'mov', 'avi'])
            if uploaded_file:
                tfile = tempfile.NamedTemporaryFile(delete=False)
                tfile.write(uploaded_file.read())
                cap = cv2.VideoCapture(tfile.name)
                st_frame = st.empty()
                
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret: break
                    
                    results = model.predict(frame, conf=threshold)
                    st_frame.image(cv2.cvtColor(results[0].plot(), cv2.COLOR_BGR2RGB))
                    
                    # التحقق من وجود فيضان (Pond/Flood)
                    current_labels = [model.names[int(box.cls[0])].lower() for box in results[0].boxes]
                    is_danger = any(label in current_labels for label in ["pond", "water", "flood", "puddle"])
                    
                    if is_danger:
                        now = time.time()
                        if now - st.session_state.last_alert_time > 600: # تنبيه كل 10 دقائق
                            time_str = datetime.datetime.now().strftime('%H:%M:%S')
                            send_telegram_alert(source_option, time_str)
                            save_report_to_db(source_option, "Detected")
                            st.session_state.last_alert_time = now
                            
                            # بناء رسالة التحقق وحفظها في الـ session_state لتبقى ثابتة
                            st.session_state.last_report_html = f"""
                                <div class="metric-card" style="border-left-color: #ba1a1a;">
                                    <b style="color:#ba1a1a;">📅 Latest Hazard Verified:</b><br>
                                    <span style="font-size:13px; color:#333;">Source: {source_option}</span><br>
                                    <span style="font-size:13px; color:#333;">Time: {time_str}</span><br>
                                    <span style="color:green; font-weight:bold; font-size:12px;">✓ Telegram Sent & Logged</span>
                                </div>
                            """
                cap.release()

    with col_data:
        st.markdown(f"""
            <div class="metric-card">
                <div style="font-size: 10px; color: gray; font-weight: bold; text-transform: uppercase;">Current Unit</div>
                <div style="font-weight:bold; font-size:16px; color:#003527;">{source_option}</div>
            </div>
        """, unsafe_allow_html=True)
        
        # عرض رسالة التحقق دائماً إذا كانت موجودة
        if st.session_state.last_report_html:
            st.markdown(st.session_state.last_report_html, unsafe_allow_html=True)
        else:
            st.write("No active hazards reported.")

# --- TAB 2: DASHBOARD & ANALYTICS (دمج كودك هنا) ---
with tab2:
    st.markdown('<h1 style="text-align:left; font-size:24px;">📊 ANALYTICS DASHBOARD</h1>', unsafe_allow_html=True)
    
    conn = sqlite3.connect('aqua_road.db')
    df = pd.read_sql_query("SELECT date as Date, time as Time, source as Source, status as Status FROM reports ORDER BY id DESC", conn)
    conn.close()

    if not df.empty:
        st.table(df)
        st.markdown("### 📈 Incident Distribution")
        stats_df = df['Source'].value_counts().reset_index()
        stats_df.columns = ['Source', 'Number of Reports']
        st.bar_chart(stats_df, x="Source", y="Number of Reports", color="#003527")
    else:
        st.warning("⚠️ No records found in the database yet.")
