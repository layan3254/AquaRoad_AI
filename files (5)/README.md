# 🌊 AQUA-ROAD — Setup & Run Guide

## Project Structure
```
aqua_road/
├── CCTV.py            ← Main app entry point (Live Monitor)
├── pages/
│   └── Dashboard.py   ← Analytics dashboard (auto-linked by Streamlit)
├── best.pt            ← YOLO flood detection model
└── aqua_road.db       ← SQLite database (auto-created on first run)
```

## Installation
```bash
pip install streamlit ultralytics opencv-python-headless requests pandas
```

## Running
```bash
cd aqua_road/
streamlit run CCTV.py
```
Streamlit will automatically show both pages in the sidebar:
- 🌊 **CCTV** (Live Monitor)
- 📊 **Dashboard** (Analytics)

## Camera Troubleshooting
| Error | Fix |
|---|---|
| "Cannot open source" | App falls back to **Demo Mode** automatically. Connect a USB webcam and restart. |
| Wrong camera index | App tries indices 0, 1, 2 automatically |
| RTSP stream | Change `cam_index` in `CAMERA_META` to your RTSP URL string |

## Key Features
- **Demo Mode** — runs with simulated frames when no camera is found (no crash)
- **Frame confirmation** — requires N consecutive positive frames before alerting (anti-flicker)
- **Severity scoring** — 5 levels: Clear → Low → Moderate → High → Critical
- **Telegram alerts** — sends annotated snapshot image
- **Dashboard** — real-time table, bar charts, daily trend, CSV export, auto-refresh
- **Shared DB** — both pages read/write the same `aqua_road.db`

## Telegram Setup
1. Create a bot via [@BotFather](https://t.me/BotFather)
2. Paste the token into the sidebar **Bot Token** field
3. Get your Chat ID from [@userinfobot](https://t.me/userinfobot)
4. Paste it into the **Chat ID** field
