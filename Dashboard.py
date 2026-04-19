import streamlit as st
import pandas as pd
import sqlite3

# --- 1. Page Configuration ---
st.set_page_config(page_title="AQUA-ROAD | Dashboard", layout="wide")

# --- 2. Interface Customization (CSS) ---
st.markdown("""
    <style>
    /* Light background for the whole app */
    .stApp { background-color: #FAF9F6 !important; }
    
    /* Dark Green Sidebar */
    [data-testid="stSidebar"] { background-color: #003527 !important; }
    [data-testid="stSidebar"] * { color: white !important; }
    
    /* Dark Green Headers */
    h1, h2, h3 { color: #003527 !important; font-family: 'Manrope', sans-serif; }

    /* --- Table Styling (Black/Dark Gray Text) --- */
    .stDataFrame div, .stTable td, .stTable th {
        color: #1A1C1A !important; 
    }
    
    [data-testid="stTable"] td {
        color: #333333 !important;
        font-weight: 500;
    }

    /* Table Header Styling */
    [data-testid="stTable"] th {
        background-color: #E8E8E8 !important;
        color: #003527 !important;
    }

    /* --- Alert Message Styling (Dark Gray Color) --- */
    .stAlert p {
        color: #333333 !important;
        font-weight: 500;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. Database Retrieval Function ---
def get_data_from_db():
    try:
        # Connect to the database created by the CCTV script
        conn = sqlite3.connect('aqua_road.db')
        # Fetch data and order by newest first
        query = "SELECT date as Date, time as Time, source as Source, status as Status FROM reports ORDER BY id DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        # Return empty dataframe if database doesn't exist yet
        return pd.DataFrame()

# --- 4. Page Content ---
# Note: Alignment changed to left (Standard for English)
st.markdown('<h1 style="text-align:left;">📊 DASHBOARD & ANALYTICS</h1>', unsafe_allow_html=True)
st.markdown('<h3 style="text-align:left;">📋 Archived Incident Reports</h3>', unsafe_allow_html=True)

# Fetching live data
df = get_data_from_db()

if not df.empty:
    # Display table with dark, clear text
    st.table(df)

    # --- 5. Smart Analytics ---
    st.markdown('<h3 style="text-align:left;">📈 Analytics: Most Active Cameras</h3>', unsafe_allow_html=True)
    
    # Calculate stats automatically based on reports per source
    stats_df = df['Source'].value_counts().reset_index()
    stats_df.columns = ['Source', 'Number of Reports']
    
    # Display Bar Chart in Dark Green
    st.bar_chart(stats_df, x="Source", y="Number of Reports", color="#003527")
    
    st.info("💡 Data is updated automatically based on real-time detections from the CCTV page.")
else:
    # Warning message in dark gray for better visibility
    st.warning("⚠️ No records found in the database yet. The table will populate once the first water accumulation is detected.")