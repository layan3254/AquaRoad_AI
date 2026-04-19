"""
AQUA-ROAD Detection Engine
==========================
A modular, production-ready backend for flood and water accumulation detection.
Designed to be imported by CCTV.py and any future interfaces.

Features:
- YOLO-based water/flood detection with configurable thresholds
- Severity classification (Clear → Puddle → Pond → Flood)
- Frame buffering to eliminate false positives (consecutive-frame confirmation)
- ROI (Region of Interest) masking — ignore irrelevant parts of the frame
- Cooldown-aware alert management with de-duplication
- Thread-safe SQLite logging with extended schema
- Telegram alerting with image snapshots
- Health check and camera diagnostics utility
"""

import cv2
import numpy as np
import sqlite3
import datetime
import time
import threading
import logging
import urllib.parse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from collections import deque

import requests

# ──────────────────────────────────────────────
# 0. Logging Setup
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AquaRoad")


# ──────────────────────────────────────────────
# 1. Configuration Dataclass
# ──────────────────────────────────────────────
@dataclass
class DetectionConfig:
    """All tuneable parameters in one place."""

    model_path: str = "best.pt"
    db_path: str = "aqua_road.db"

    # Detection thresholds
    confidence: float = 0.50
    iou: float = 0.45

    # Hazard class names (lowercase). Any detected label in this set = danger.
    hazard_classes: tuple = ("pond", "water", "flood", "puddle", "pool", "waterlog")

    # Severity scoring per class (used for risk level classification)
    severity_weights: dict = field(default_factory=lambda: {
        "puddle":   1,
        "water":    2,
        "pool":     2,
        "pond":     3,
        "waterlog": 3,
        "flood":    4,
    })

    # Frame buffer: how many consecutive positive frames before triggering alert
    confirm_frames: int = 3

    # Alert cooldown in seconds (avoid spamming)
    alert_cooldown_seconds: int = 600

    # Optional ROI: (x1, y1, x2, y2) as fractions of frame size (0.0–1.0)
    # Example: (0.0, 0.3, 1.0, 1.0) ignores the sky (top 30%)
    roi: Optional[tuple] = None  # None = use full frame

    # Telegram credentials (set via environment or here)
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # Send annotated snapshot to Telegram on alert
    send_snapshot: bool = True


# ──────────────────────────────────────────────
# 2. Severity Level
# ──────────────────────────────────────────────
class Severity:
    CLEAR    = ("CLEAR",    (0,   200, 0))    # green
    LOW      = ("LOW",      (0,   200, 200))  # yellow-ish
    MODERATE = ("MODERATE", (0,   140, 255))  # orange
    HIGH     = ("HIGH",     (0,   0,   255))  # red
    CRITICAL = ("CRITICAL", (180, 0,   255))  # deep red/magenta

    @staticmethod
    def from_score(score: int):
        if score == 0:          return Severity.CLEAR
        elif score <= 1:        return Severity.LOW
        elif score <= 2:        return Severity.MODERATE
        elif score <= 4:        return Severity.HIGH
        else:                   return Severity.CRITICAL


# ──────────────────────────────────────────────
# 3. Detection Result Container
# ──────────────────────────────────────────────
@dataclass
class DetectionResult:
    is_hazard: bool
    severity: tuple                      # e.g. ("HIGH", (0, 0, 255))
    severity_score: int
    detected_classes: list[str]
    confidence_scores: list[float]
    annotated_frame: np.ndarray
    raw_frame: np.ndarray
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)


# ──────────────────────────────────────────────
# 4. Database Manager (Thread-Safe)
# ──────────────────────────────────────────────
class DatabaseManager:
    """
    Thread-safe SQLite wrapper.
    Extended schema includes severity, confidence, and detected classes.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            c = conn.cursor()

            # Original table (kept for backward compatibility with Dashboard.py)
            c.execute("""CREATE TABLE IF NOT EXISTS reports (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                date     TEXT,
                time     TEXT,
                source   TEXT,
                status   TEXT
            )""")

            # Extended table for richer analytics
            c.execute("""CREATE TABLE IF NOT EXISTS detections (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        TEXT NOT NULL,
                source           TEXT NOT NULL,
                severity         TEXT NOT NULL,
                severity_score   INTEGER NOT NULL,
                detected_classes TEXT,
                max_confidence   REAL,
                duration_seconds REAL DEFAULT 0
            )""")

            conn.commit()
            conn.close()
        logger.info(f"Database ready: {self.db_path}")

    def save_report(self, source: str, status: str):
        """Write to the original `reports` table (used by Dashboard.py)."""
        with self._lock:
            conn = self._connect()
            now = datetime.datetime.now()
            conn.execute(
                "INSERT INTO reports (date, time, source, status) VALUES (?, ?, ?, ?)",
                (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), source, status)
            )
            conn.commit()
            conn.close()

    def save_detection(self, source: str, result: DetectionResult, duration: float = 0.0):
        """Write to the extended `detections` table."""
        with self._lock:
            conn = self._connect()
            conn.execute(
                """INSERT INTO detections
                   (timestamp, source, severity, severity_score, detected_classes, max_confidence, duration_seconds)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.timestamp.isoformat(),
                    source,
                    result.severity[0],
                    result.severity_score,
                    ", ".join(result.detected_classes),
                    max(result.confidence_scores) if result.confidence_scores else 0.0,
                    round(duration, 2),
                )
            )
            conn.commit()
            conn.close()

    def get_reports_df(self):
        """Return all reports as a list of dicts (for Dashboard)."""
        import pandas as pd
        conn = self._connect()
        df = pd.read_sql_query(
            "SELECT date as Date, time as Time, source as Source, status as Status "
            "FROM reports ORDER BY id DESC",
            conn
        )
        conn.close()
        return df

    def get_detections_df(self):
        """Return extended detections for analytics."""
        import pandas as pd
        conn = self._connect()
        df = pd.read_sql_query(
            "SELECT * FROM detections ORDER BY id DESC",
            conn
        )
        conn.close()
        return df

    def get_stats(self) -> dict:
        """Quick summary stats."""
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM detections")
        total = c.fetchone()[0]
        c.execute("SELECT severity, COUNT(*) FROM detections GROUP BY severity")
        by_severity = dict(c.fetchall())
        c.execute("SELECT source, COUNT(*) FROM detections GROUP BY source ORDER BY COUNT(*) DESC LIMIT 1")
        top_camera = c.fetchone()
        conn.close()
        return {
            "total_detections": total,
            "by_severity": by_severity,
            "busiest_camera": top_camera[0] if top_camera else "N/A",
        }


# ──────────────────────────────────────────────
# 5. Alert Manager
# ──────────────────────────────────────────────
class AlertManager:
    """
    Manages Telegram alerts with:
    - Per-source cooldown tracking
    - Snapshot attachment support
    """

    def __init__(self, config: DetectionConfig):
        self.config = config
        self._last_alert: dict[str, float] = {}  # source → epoch time
        self._lock = threading.Lock()

    def _is_on_cooldown(self, source: str) -> bool:
        with self._lock:
            last = self._last_alert.get(source, 0)
            return (time.time() - last) < self.config.alert_cooldown_seconds

    def _record_alert(self, source: str):
        with self._lock:
            self._last_alert[source] = time.time()

    def send_alert(self, source: str, result: DetectionResult) -> bool:
        """
        Send a Telegram alert (with optional snapshot).
        Returns True if alert was sent, False if on cooldown or credentials missing.
        """
        if not self.config.telegram_token or not self.config.telegram_chat_id:
            logger.warning("Telegram credentials not set — alert skipped.")
            return False

        if self._is_on_cooldown(source):
            logger.debug(f"Alert for {source} suppressed (cooldown active).")
            return False

        severity_label = result.severity[0]
        classes_str = ", ".join(result.detected_classes) if result.detected_classes else "Unknown"
        message = (
            f"🚨 AQUA-ROAD ALERT\n"
            f"{'─' * 30}\n"
            f"📍 Source    : {source}\n"
            f"⚠️  Severity  : {severity_label}\n"
            f"🔍 Detected  : {classes_str}\n"
            f"📊 Score     : {result.severity_score}\n"
            f"🕐 Time      : {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'─' * 30}\n"
            f"Immediate inspection recommended."
        )

        base_url = f"https://api.telegram.org/bot{self.config.telegram_token}"
        success = False

        try:
            if self.config.send_snapshot:
                # Encode annotated frame as JPEG and send as photo
                _, buffer = cv2.imencode(".jpg", result.annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                files = {"photo": ("snapshot.jpg", buffer.tobytes(), "image/jpeg")}
                data  = {"chat_id": self.config.telegram_chat_id, "caption": message}
                resp  = requests.post(f"{base_url}/sendPhoto", data=data, files=files, timeout=10)
            else:
                encoded = urllib.parse.quote(message)
                resp = requests.get(
                    f"{base_url}/sendMessage?chat_id={self.config.telegram_chat_id}&text={encoded}",
                    timeout=10
                )

            success = resp.status_code == 200
            if success:
                self._record_alert(source)
                logger.info(f"Telegram alert sent for {source} ({severity_label})")
            else:
                logger.error(f"Telegram error {resp.status_code}: {resp.text[:200]}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error sending alert: {e}")

        return success


# ──────────────────────────────────────────────
# 6. Core Detection Engine
# ──────────────────────────────────────────────
class FloodDetectionEngine:
    """
    Main detection engine. Usage:

        engine = FloodDetectionEngine(config)
        result = engine.process_frame(frame)

        if result.is_hazard:
            engine.handle_alert(source_name, result)
    """

    def __init__(self, config: DetectionConfig):
        self.config = config
        self.db = DatabaseManager(config.db_path)
        self.alerts = AlertManager(config)

        # Frame confirmation buffer: track recent hazard flags per camera
        self._frame_buffer: dict[str, deque] = {}

        # Per-source hazard duration tracking
        self._hazard_start: dict[str, Optional[float]] = {}

        # Load YOLO model lazily (call load_model() before processing)
        self.model = None

        logger.info("FloodDetectionEngine initialised.")

    # ── 6a. Model Loading ──────────────────────
    def load_model(self):
        """Load YOLO model. Call once at startup."""
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.config.model_path)
            logger.info(f"Model loaded: {self.config.model_path}")
            logger.info(f"Classes: {list(self.model.names.values())}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    # ── 6b. ROI Masking ────────────────────────
    def _apply_roi(self, frame: np.ndarray) -> tuple[np.ndarray, Optional[tuple]]:
        """
        If ROI is configured, black-out areas outside the region.
        Returns (masked_frame, roi_pixel_coords).
        """
        if self.config.roi is None:
            return frame, None

        h, w = frame.shape[:2]
        x1 = int(self.config.roi[0] * w)
        y1 = int(self.config.roi[1] * h)
        x2 = int(self.config.roi[2] * w)
        y2 = int(self.config.roi[3] * h)

        mask = np.zeros_like(frame)
        mask[y1:y2, x1:x2] = frame[y1:y2, x1:x2]
        return mask, (x1, y1, x2, y2)

    # ── 6c. Severity Scoring ───────────────────
    def _compute_severity(self, detected_classes: list[str]) -> tuple[int, tuple]:
        """
        Sum severity weights of all detected hazard classes.
        Returns (total_score, Severity level tuple).
        """
        score = sum(
            self.config.severity_weights.get(cls, 1)
            for cls in detected_classes
        )
        return score, Severity.from_score(score)

    # ── 6d. Frame Confirmation ─────────────────
    def _confirm_hazard(self, source: str, is_hazard_this_frame: bool) -> bool:
        """
        Return True only if the last N frames all detected a hazard.
        Eliminates single-frame false positives.
        """
        if source not in self._frame_buffer:
            self._frame_buffer[source] = deque(maxlen=self.config.confirm_frames)

        self._frame_buffer[source].append(is_hazard_this_frame)

        # Need buffer to be full AND all True
        buf = self._frame_buffer[source]
        return len(buf) == self.config.confirm_frames and all(buf)

    # ── 6e. Overlay Rendering ──────────────────
    def _render_overlay(
        self,
        frame: np.ndarray,
        result,
        severity: tuple,
        score: int,
        roi_coords: Optional[tuple],
    ) -> np.ndarray:
        """Draw severity banner, ROI outline, and stats on annotated frame."""
        annotated = result.plot()  # YOLO bounding boxes

        h, w = annotated.shape[:2]
        sev_label, sev_color = severity

        # Top status banner
        banner_h = 40
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (w, banner_h), sev_color[::-1], -1)  # BGR
        cv2.addWeighted(overlay, 0.6, annotated, 0.4, 0, annotated)

        status_text = f"STATUS: {sev_label}  |  Score: {score}"
        cv2.putText(annotated, status_text, (10, 27),
                    cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)

        # Timestamp
        ts = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        cv2.putText(annotated, ts, (w - 220, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)

        # ROI boundary (dashed-style via dotted rectangle)
        if roi_coords:
            x1, y1, x2, y2 = roi_coords
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
            cv2.putText(annotated, "ROI", (x1 + 5, y1 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        return annotated

    # ── 6f. Main Processing ────────────────────
    def process_frame(self, frame: np.ndarray, source: str = "Unknown") -> DetectionResult:
        """
        Run full detection pipeline on a single frame.

        Args:
            frame:  BGR image from cv2.VideoCapture
            source: camera identifier string

        Returns:
            DetectionResult with all metadata + annotated frame
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call engine.load_model() first.")

        raw_frame = frame.copy()
        masked_frame, roi_coords = self._apply_roi(frame)

        # YOLO inference
        results = self.model.predict(
            masked_frame,
            conf=self.config.confidence,
            iou=self.config.iou,
            verbose=False,
        )
        yolo_result = results[0]

        # Parse detections
        detected_classes = []
        confidence_scores = []
        for box in yolo_result.boxes:
            cls_name = self.model.names[int(box.cls[0])].lower()
            conf     = float(box.conf[0])
            detected_classes.append(cls_name)
            confidence_scores.append(conf)

        # Determine hazard classes present
        hazard_classes = [c for c in detected_classes if c in self.config.hazard_classes]
        raw_hazard = len(hazard_classes) > 0

        # Confirmed hazard (requires N consecutive frames)
        is_hazard = self._confirm_hazard(source, raw_hazard)

        # Severity scoring
        score, severity = self._compute_severity(hazard_classes)
        if not is_hazard:
            score, severity = 0, Severity.CLEAR

        # Render annotated frame
        annotated = self._render_overlay(yolo_result, yolo_result, severity, score, roi_coords)

        return DetectionResult(
            is_hazard=is_hazard,
            severity=severity,
            severity_score=score,
            detected_classes=hazard_classes,
            confidence_scores=[c for c, n in zip(confidence_scores, detected_classes)
                                if n in self.config.hazard_classes],
            annotated_frame=annotated,
            raw_frame=raw_frame,
        )

    # ── 6g. Alert Handler ──────────────────────
    def handle_alert(self, source: str, result: DetectionResult):
        """
        Persist detection to DB and dispatch Telegram alert if off cooldown.
        Call this when result.is_hazard is True.
        """
        # Track hazard duration
        if self._hazard_start.get(source) is None:
            self._hazard_start[source] = time.time()

        duration = time.time() - self._hazard_start[source]

        # Always save to the extended table
        self.db.save_detection(source, result, duration)

        # Write to original `reports` table so Dashboard.py still works
        self.db.save_report(source, f"Detected ({result.severity[0]})")

        # Attempt Telegram alert (respects cooldown internally)
        self.alerts.send_alert(source, result)

    def handle_clear(self, source: str):
        """Reset hazard duration tracking when road clears."""
        self._hazard_start[source] = None


# ──────────────────────────────────────────────
# 7. Camera Diagnostics Utility
# ──────────────────────────────────────────────
class CameraDiagnostics:
    """
    Quick health check for camera sources.
    Call before starting the main loop.
    """

    @staticmethod
    def check(source) -> dict:
        """
        Test a camera source (int index or RTSP URL).
        Returns a status dict.
        """
        logger.info(f"Diagnosing camera source: {source}")
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            return {"ok": False, "error": "Cannot open source", "source": source}

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return {"ok": False, "error": "No frame received", "source": source}

        h, w = frame.shape[:2]
        return {
            "ok": True,
            "source": source,
            "resolution": f"{w}x{h}",
            "channels": frame.shape[2] if len(frame.shape) == 3 else 1,
        }


# ──────────────────────────────────────────────
# 8. Drop-in Upgrade for CCTV.py
# ──────────────────────────────────────────────
"""
HOW TO INTEGRATE WITH YOUR EXISTING CCTV.py
=============================================

Replace the relevant section in CCTV.py with the following:

    from detection_engine import FloodDetectionEngine, DetectionConfig, CameraDiagnostics

    # Build config (pass your Telegram creds here)
    config = DetectionConfig(
        model_path     = "best.pt",
        db_path        = "aqua_road.db",
        confidence     = threshold,          # from st.slider
        iou            = iou_val,            # from st.slider
        confirm_frames = 3,                  # require 3 consecutive positive frames
        alert_cooldown_seconds = 600,
        telegram_token   = "YOUR_TOKEN",
        telegram_chat_id = "YOUR_CHAT_ID",
        send_snapshot    = True,
        # Optional: ignore sky/top 25% of frame
        roi = (0.0, 0.25, 1.0, 1.0),
    )

    engine = FloodDetectionEngine(config)
    engine.load_model()

    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        result = engine.process_frame(frame, source=source_option)

        # Display
        st_frame.image(
            cv2.cvtColor(result.annotated_frame, cv2.COLOR_BGR2RGB),
            use_container_width=True
        )

        if result.is_hazard:
            engine.handle_alert(source_option, result)
            status_indicator.error(f"🚨 ALERT: {result.severity[0]} — {', '.join(result.detected_classes)}")
        else:
            engine.handle_clear(source_option)
            status_indicator.success("✔️ SYSTEM STATUS: Road is Clear")

    cap.release()
"""
