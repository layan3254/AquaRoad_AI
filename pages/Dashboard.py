import streamlit as st
import pandas as pd
import sqlite3
import os

# --- 1. Page Configuration ---
st.set_page_config(page_title="AQUA-ROAD | Dashboard", layout="wide")

# --- SHARED DB PATH (always points to the project root, regardless of which page runs) ---
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(_file_)), '..', 'aqua_road.db')
DB_PATH = os.path.normpath(DB_PATH)

# --- 2. Interface Customization (CSS) ---
st.markdown("""
    <style>
    .stApp { background-color: #FAF9F6 !important; }
    [data-testid="stSidebar"] { background-color: #003527 !important; }
    [data-testid="stSidebar"] * { color: white !important; }
    h1, h2, h3 { color: #003527 !important; font-family: 'Manrope', sans-serif; }
    .stDataFrame div, .stTable td, .stTable th { color: #1A1C1A !important; }
    [data-testid="stTable"] td { color: #333333 !important; font-weight: 500; }
    [data-testid="stTable"] th { background-color: #E8E8E8 !important; color: #003527 !important; }
    .stAlert p { color: #333333 !important; font-weight: 500; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. Database Retrieval Function ---
def get_data_from_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT date as Date, time as Time, source as Source, status as Status FROM reports ORDER BY id DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.caption(f"DB path used: {DB_PATH} — Error: {e}")
        return pd.DataFrame()

# --- 4. Page Content ---
st.markdown('<h1 style="text-align:left;">📊 DASHBOARD & ANALYTICS</h1>', unsafe_allow_html=True)
st.markdown('<h3 style="text-align:left;">📋 Archived Incident Reports</h3>', unsafe_allow_html=True)

df = get_data_from_db()

if not df.empty:
    st.table(df)

    st.markdown('<h3 style="text-align:left;">📈 Analytics: Most Active Cameras</h3>', unsafe_allow_html=True)
    stats_df = df['Source'].value_counts().reset_index()
    stats_df.columns = ['Source', 'Number of Reports']
    st.bar_chart(stats_df, x="Source", y="Number of Reports", color="#003527")
    st.info("💡 Data is updated automatically based on real-time detections from the CCTV page.")
else:
    st.warning("⚠️ No records found in the database yet. The table will populate once the first water accumulation is detected.")
