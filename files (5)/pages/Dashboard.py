"""
AQUA-ROAD | Dashboard & Analytics
Lives in the pages/ folder so Streamlit's multipage router picks it up.
Reads aqua_road.db written by CCTV.py (one folder up).
"""

import streamlit as st
import pandas as pd
import sqlite3
import datetime
import os

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AQUA-ROAD | Dashboard",
    page_icon="📊",
    layout="wide",
)

# ── Shared DB path ─────────────────────────────────────────────────────────────
# pages/ is one level below CCTV.py, so go up one directory
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "aqua_road.db")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap');

.stApp { background-color: #FAF9F6 !important; font-family: 'Manrope', sans-serif; }

[data-testid="stSidebar"] { background-color: #003527 !important; }
[data-testid="stSidebar"] * { color: #ffffff !important; }

h1, h2, h3 { color: #003527 !important; font-family: 'Manrope', sans-serif; }

/* Table */
[data-testid="stTable"] td  { color: #1A1C1A !important; font-weight: 500; font-size: 13px; }
[data-testid="stTable"] th  { background-color: #E8F0EB !important; color: #003527 !important;
                               font-weight: 700; font-size: 12px; text-transform: uppercase; }

/* Alerts */
.stAlert p { color: #333333 !important; font-weight: 500; }

/* Stat cards */
.stat-card {
    background: #ffffff;
    border-left: 5px solid #003527;
    border-radius: 0 8px 8px 0;
    padding: 16px 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    margin-bottom: 10px;
}
.stat-num   { font-size: 2rem; font-weight: 800; color: #003527; line-height: 1; }
.stat-label { font-size: 11px; color: #666; font-weight: 600; text-transform: uppercase;
              letter-spacing: 0.8px; margin-top: 4px; }

.sev-pill {
    display: inline-block; padding: 2px 10px; border-radius: 20px;
    font-size: 11px; font-weight: 700; color: white; margin: 1px;
}
</style>
""", unsafe_allow_html=True)

SEV_COLORS = {
    "CLEAR":    "#2e7d32",
    "LOW":      "#f9a825",
    "MODERATE": "#e65100",
    "HIGH":     "#b71c1c",
    "CRITICAL": "#6a1b9a",
    "Detected": "#003527",
    "N/A":      "#888888",
}

# ── DB helpers ────────────────────────────────────────────────────────────────
def load_reports() -> pd.DataFrame:
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            """SELECT
                 date    AS Date,
                 time    AS Time,
                 source  AS Source,
                 status  AS Status,
                 COALESCE(severity, 'N/A') AS Severity,
                 COALESCE(classes,  '')    AS "Detected Classes"
               FROM reports
               ORDER BY id DESC""",
            conn,
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

def db_stats() -> dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM reports")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM reports WHERE date = ?",
                  (datetime.date.today().isoformat(),))
        today = c.fetchone()[0]
        c.execute("SELECT source, COUNT(*) AS n FROM reports GROUP BY source ORDER BY n DESC LIMIT 1")
        top = c.fetchone()
        c.execute("SELECT severity, COUNT(*) FROM reports GROUP BY severity")
        sev = dict(c.fetchall())
        conn.close()
        return {"total": total, "today": today,
                "top_cam": top[0] if top else "—",
                "by_severity": sev}
    except Exception:
        return {"total": 0, "today": 0, "top_cam": "—", "by_severity": {}}

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📊 FILTERS")
    auto_refresh  = st.checkbox("Auto-refresh (10 s)", value=True)
    filter_source = st.multiselect("Filter by Source",
                                   ["Camera #402", "Camera #105", "Trial Stream"],
                                   default=[])
    filter_sev    = st.multiselect("Filter by Severity",
                                   ["CLEAR", "LOW", "MODERATE", "HIGH", "CRITICAL", "Detected", "N/A"],
                                   default=[])
    st.markdown("---")
    st.markdown("**🔗 Navigation**")
    st.page_link("CCTV.py",           label="▶ Live Monitor", icon="🌊")
    st.page_link("pages/Dashboard.py", label="📊 Dashboard",  icon="📈")

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("# 📊 DASHBOARD & ANALYTICS")
st.markdown(
    '<p style="color:#666; font-size:13px; margin-top:-10px;">Real-time incident data from the CCTV monitoring system</p>',
    unsafe_allow_html=True,
)
st.divider()

# ── Load data ─────────────────────────────────────────────────────────────────
df   = load_reports()
stats = db_stats()

# Apply filters
if not df.empty:
    if filter_source:
        df = df[df["Source"].isin(filter_source)]
    if filter_sev:
        df = df[df["Severity"].isin(filter_sev)]

# ── KPI Cards ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
kpi_data = [
    (k1, stats["total"],   "Total Detections",  "#003527"),
    (k2, stats["today"],   "Detections Today",  "#e65100"),
    (k3, stats["top_cam"], "Most Active Camera", "#1a6b4a"),
    (k4, len(df),          "Showing Records",   "#444444"),
]
for col, val, label, color in kpi_data:
    with col:
        st.markdown(f"""
        <div class="stat-card" style="border-left-color:{color};">
            <div class="stat-num" style="color:{color};">{val}</div>
            <div class="stat-label">{label}</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# ── Incident Table ────────────────────────────────────────────────────────────
st.markdown("### 📋 Archived Incident Reports")

if df.empty:
    st.warning("⚠️ No records found. The table populates once water accumulation is detected by the CCTV page.")
else:
    # Colour-coded severity pills in the table
    def sev_pill(val):
        c = SEV_COLORS.get(val, "#888")
        return f'<span class="sev-pill" style="background:{c};">{val}</span>'

    display_df = df.copy()
    display_df["Severity"] = display_df["Severity"].apply(sev_pill)

    st.write(
        display_df.to_html(escape=False, index=False),
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Charts ─────────────────────────────────────────────────────────────────
    ch1, ch2 = st.columns(2)

    with ch1:
        st.markdown("### 📈 Detections per Camera")
        cam_counts = df["Source"].value_counts().reset_index()
        cam_counts.columns = ["Source", "Detections"]
        st.bar_chart(cam_counts, x="Source", y="Detections", color="#003527")

    with ch2:
        st.markdown("### 🟡 Severity Distribution")
        if "Severity" in df.columns:
            # Strip HTML from severity column for chart
            raw_sev = load_reports()
            if filter_source:
                raw_sev = raw_sev[raw_sev["Source"].isin(filter_source)]
            sev_counts = raw_sev["Severity"].value_counts().reset_index()
            sev_counts.columns = ["Severity", "Count"]
            colors = [SEV_COLORS.get(s, "#888") for s in sev_counts["Severity"]]
            st.bar_chart(sev_counts, x="Severity", y="Count", color="#b71c1c")

    # ── Time series (detections per day) ───────────────────────────────────────
    st.markdown("### 📅 Daily Detection Trend")
    raw_df = load_reports()
    if filter_source:
        raw_df = raw_df[raw_df["Source"].isin(filter_source)]
    if not raw_df.empty:
        raw_df["Date"] = pd.to_datetime(raw_df["Date"])
        daily = raw_df.groupby("Date").size().reset_index(name="Detections")
        st.line_chart(daily, x="Date", y="Detections", color="#003527")

    st.info("💡 Data updates in real time from detections logged by the CCTV monitoring page.")

# ── Export ────────────────────────────────────────────────────────────────────
if not df.empty:
    export_df = load_reports()  # raw version without HTML
    csv = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Export Reports as CSV",
        data=csv,
        file_name=f"aqua_road_reports_{datetime.date.today()}.csv",
        mime="text/csv",
    )

# ── Auto-refresh ─────────────────────────────────────────────────────────────
if auto_refresh:
    time_module = __import__("time")
    time_module.sleep(10)
    st.rerun()
