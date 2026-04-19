"""
AQUA-ROAD | CCTV Monitoring Interface
======================================
Upgraded version using detection_engine.py for robust flood detection.
Run with: streamlit run CCTV.py
"""

import streamlit as st
import cv2
import datetime
from detection_engine import FloodDetectionEngine, DetectionConfig, CameraDiagnostics

# ──────────────────────────────────────────────
# 1. Page Configuration
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="AQUA-ROAD | Autonomous Monitoring",
    layout="wide"
)

# ──────────────────────────────────────────────
# 2. Styling
# ──────────────────────────────────────────────
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;700;800&display=swap');
    .stApp { background-color: #FAF9F6; }
    [data-testid="stSidebar"] { background-color: #003527 !important; }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] h3 { color: white !important; }
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
    .severity-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 13px;
    }
    </style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# 3. Sidebar Settings
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown('<h3>⚙️ SETTINGS</h3>', unsafe_allow_html=True)

    source_option = st.selectbox("CHOOSE SOURCE", ("Camera #402", "Camera #105", "Trial Stream"))
    threshold   = st.slider("CONFIDENCE THRESHOLD", 0.0, 1.0, 0.50, 0.05)
    iou_val     = st.slider("IoU THRESHOLD", 0.0, 1.0, 0.45, 0.05)
    confirm_n   = st.slider("CONFIRM FRAMES (anti-flicker)", 1, 10, 3)
    cooldown    = st.slider("ALERT COOLDOWN (seconds)", 60, 1800, 600, 60)
    use_roi     = st.checkbox("Enable ROI (ignore top 25%)", value=True)

    st.markdown("---")
    st.markdown("**Telegram Alerts**")
    tg_token   = st.text_input("Bot Token", value="8524001645:AAFCZbanUp8kJVKxoV0SGkMWYSVGw1kD9Wo", type="password")
    tg_chat_id = st.text_input("Chat ID", value="954637036")

# ──────────────────────────────────────────────
# 4. Header
# ──────────────────────────────────────────────
st.markdown('<h1 class="main-title">🌊 AQUA-ROAD</h1>', unsafe_allow_html=True)
st.markdown('<p style="color:#003527; font-size:14px; margin-top:-10px; font-weight:bold;">Automated Water Accumulation Monitoring System</p>', unsafe_allow_html=True)
st.divider()

# ──────────────────────────────────────────────
# 5. Location Metadata
# ──────────────────────────────────────────────
CAMERA_META = {
    "Camera #402": ("Al-Hada District, Riyadh",  "24.71°N, 46.67°E"),
    "Camera #105": ("Al-Malqa District, Riyadh", "24.82°N, 46.61°E"),
    "Trial Stream": ("Test Zone, Riyadh",         "00.00°N, 00.00°E"),
}
location_name, coordinates = CAMERA_META[source_option]

# ──────────────────────────────────────────────
# 6. Layout
# ──────────────────────────────────────────────
col_video, col_info = st.columns([2, 1])

with col_video:
    st.markdown('<p style="font-weight:bold; color:#5E5E5E;">Live Monitoring Feed</p>', unsafe_allow_html=True)
    st_frame = st.empty()

with col_info:
    st.markdown('<p style="font-weight:bold; color:#5E5E5E;">Control & Monitoring Panel</p>', unsafe_allow_html=True)
    status_indicator = st.empty()
    severity_display = st.empty()

    st.markdown(f"""
        <div class="metric-card">
            <div style="font-size:10px; color:gray; font-weight:bold; text-transform:uppercase;">Exact Location</div>
            <div style="font-weight:bold; font-size:14px; color:#1A1C1A;">{location_name}</div>
            <div style="font-size:11px; color:#474747;">{coordinates}</div>
        </div>
    """, unsafe_allow_html=True)

    alert_log_placeholder = st.empty()

# ──────────────────────────────────────────────
# 7. Build Engine (cached to survive reruns)
# ──────────────────────────────────────────────
@st.cache_resource
def get_engine(conf, iou, confirm, cooldown_sec, roi_enabled, token, chat):
    config = DetectionConfig(
        model_path             = "best.pt",
        db_path                = "aqua_road.db",
        confidence             = conf,
        iou                    = iou,
        confirm_frames         = confirm,
        alert_cooldown_seconds = cooldown_sec,
        roi                    = (0.0, 0.25, 1.0, 1.0) if roi_enabled else None,
        telegram_token         = token,
        telegram_chat_id       = chat,
        send_snapshot          = True,
    )
    engine = FloodDetectionEngine(config)
    engine.load_model()
    return engine

engine = get_engine(threshold, iou_val, confirm_n, cooldown, use_roi, tg_token, tg_chat_id)

# ──────────────────────────────────────────────
# 8. Session State
# ──────────────────────────────────────────────
if "last_report_html" not in st.session_state:
    st.session_state.last_report_html = ""

# ──────────────────────────────────────────────
# 9. Main Loop
# ──────────────────────────────────────────────
SEVERITY_COLORS = {
    "CLEAR":    "#2e7d32",
    "LOW":      "#f9a825",
    "MODERATE": "#e65100",
    "HIGH":     "#b71c1c",
    "CRITICAL": "#6a1b9a",
}

diag = CameraDiagnostics.check(0)
if not diag["ok"]:
    st.error(f"❌ Camera Error: {diag['error']}")
    st.stop()

cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        st.warning("⚠️ Frame read failed — retrying...")
        break

    result = engine.process_frame(frame, source=source_option)

    # ── Display annotated frame ──────────────
    st_frame.image(
        cv2.cvtColor(result.annotated_frame, cv2.COLOR_BGR2RGB),
        use_container_width=True
    )

    # ── Status + Severity badge ──────────────
    sev_label = result.severity[0]
    sev_color = SEVERITY_COLORS.get(sev_label, "#333")

    if result.is_hazard:
        status_indicator.error(f"🚨 ALERT: Water Accumulation Detected")
        severity_display.markdown(
            f'<span class="severity-badge" style="background:{sev_color}; color:white;">'
            f'Severity: {sev_label} (Score: {result.severity_score})'
            f'</span>',
            unsafe_allow_html=True
        )

        engine.handle_alert(source_option, result)

        time_now = result.timestamp.strftime("%H:%M:%S")
        classes_str = ", ".join(result.detected_classes) or "Unknown"
        st.session_state.last_report_html = f"""
            <div class="metric-card" style="border-left-color: #ba1a1a;">
                <b style="color:#ba1a1a;">📅 Latest Archived Report:</b><br>
                <span style="font-size:13px; color:#474747;">Source: {source_option}</span><br>
                <span style="font-size:13px; color:#474747;">Time: {time_now}</span><br>
                <span style="font-size:13px; color:#474747;">Detected: {classes_str}</span><br>
                <span style="font-size:13px; color:#474747;">Severity: {sev_label}</span><br>
                <span style="color:green; font-weight:bold; font-size:13px;">✓ Saved to Database</span>
            </div>
        """
    else:
        engine.handle_clear(source_option)
        status_indicator.success("✔️ SYSTEM STATUS: Road is Clear")
        severity_display.empty()

    if st.session_state.last_report_html:
        alert_log_placeholder.markdown(st.session_state.last_report_html, unsafe_allow_html=True)

cap.release()
