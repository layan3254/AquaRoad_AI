
# 🌊 AQUA-ROAD AI: Autonomous Water Accumulation Monitoring

**AquaRoad AI** is an intelligent early-warning system designed to enhance smart city infrastructure. It utilizes Computer Vision to detect road hazards like puddles and floods in real-time, providing automated alerts to authorities to ensure public safety.

---

## 🌊 The Concept: Problem & Solution

### 🚨 The Problem
During rainy seasons, undetected water accumulations on roads lead to severe traffic congestion and increased accident risks. Current monitoring methods suffer from:
* **Manual Oversight:** Human operators cannot monitor hundreds of CCTV feeds 24/7 without fatigue.
* **Delayed Response:** Emergency services are often notified only *after* an incident or accident occurs.
* **Lack of Data:** Absence of automated logging makes it difficult for city planners to identify flood-prone zones.

### 💡 The Solution
**AquaRoad AI** introduces an autonomous monitoring layer that transforms standard cameras into smart sensors:
* **Autonomous Vigilance:** 24/7 monitoring using YOLOv8 to detect water hazards instantly.
* **Instant Action:** Triggers automated **Telegram Alerts** with precise location data, reducing response time from hours to seconds.
* **Smart Filtering:** A specialized logic that distinguishes between a **Clear Road** and **Hazards**, ensuring alerts are only sent when an actual risk is detected.
* **Digital Archiving:** Every incident is automatically logged into an **SQLite Database** for historical analysis and urban planning.

---

## 📊 Model Comparison & Selection

To ensure the highest reliability, we conducted a benchmark comparing three different generations of the YOLO (You Only Look Once) architecture.

### Benchmark Results:

| Model Architecture | Precision (P) | Recall (R) | mAP50 | mAP50-95 |
| :--- | :--- | :--- | :--- | :--- |
| **YOLOv8 Segentation** | 0.6182 | 0.3776  | 0.4914 | 0.3242 |
| **coco Segentation** | 0.1690 | 0.2780 | 0.2755 | 0.1689 |
| **YOLOv8 (Selected)** | **0.7895** | **0.5062** | **0.5468** | **0.3915** |

### 🏆 Why YOLOv8?
Based on our experimental data, **YOLOv8** was the superior choice because:
1. **Highest Precision (78.9%):** Crucial for minimizing false alarms in complex outdoor environments.
2. **Best mAP50 (54.6%):** Demonstrates exceptional accuracy in identifying various sizes of water accumulations.
3. **Optimized Speed:** Provides the smoothest real-time inference for our interactive Streamlit dashboard.

---

## 🛠️ Tech Stack
* **AI Model:** YOLOv8 (Ultralytics)
* **Interface:** Streamlit
* **Programming:** Python
* **Computer Vision:** OpenCV
* **Database:** SQLite3
* **Notifications:** Telegram Bot API

---

## ⚙️ How it Works
1. **Input:** The system captures live video feeds from road-monitoring cameras.
2. **Processing:** YOLOv8 identifies the road condition (Clear vs. Water Accumulation).
3. **Filtering:** If a hazard (Pond/Flood) is detected, the **Emergency Logic** is triggered.
4. **Output:** - Dashboard turns **Red** with an alert message.
   - An automated notification is sent via **Telegram**.
   - The incident is permanently saved in the **SQLite Database**.
  
---

## Team:
1.Layan Almohammadi
2.
3.
4.

