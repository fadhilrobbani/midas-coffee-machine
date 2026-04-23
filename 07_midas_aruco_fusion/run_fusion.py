"""
run_fusion.py — ArUco + MiDaS + YOLO Cup Height Estimator
=============================================================
Sistem estimasi tinggi gelas dengan ArUco sebagai jangkar jarak absolut
dan MiDaS + YOLO untuk pemetaan kedalaman relatif bibir gelas.

Fitur:
  - Auto-calibration 1-Point: --calibrate 1 --true-height 7.6
  - Auto-calibration 2-Point: --calibrate 2 --true-height 7.6 --true-height-2 10.2
  - Mode live otomatis membaca calibration.json (format bebas 1-pt / 2-pt)
  - Recording (R), Screenshot (S), Report (Q/ESC)
"""

import os
import sys
import argparse
import time
import json
import shutil
from datetime import datetime

import cv2
import numpy as np
import matplotlib.pyplot as plt

# ── Root project path ───────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR  = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# ── Import dari sub-modul proyek (via ROOT_DIR) ─────────────────────────────
try:
    from midas_volumecup.depth    import MidasDepthEstimator
    from midas_volumecup.detector import YoloDetector
    from midas_volumecup.volume_math import calculate_z_rim_alpha
except ImportError as e:
    print(f"[ERROR] Gagal import midas_volumecup: {e}")
    sys.exit(1)

try:
    _ARUCO_DIR = os.path.join(ROOT_DIR, "06_aruco_marker")
    if _ARUCO_DIR not in sys.path:
        sys.path.insert(0, _ARUCO_DIR)
    from aruco_detector import ArucoDetector
except ImportError as e:
    print(f"[ERROR] Gagal import ArucoDetector: {e}")
    sys.exit(1)


# ── Persiapan Direktori Hasil ─────────────────────────────────────────────
RESULT_DIR     = os.path.join(_THIS_DIR, "results")
REPORT_DIR     = os.path.join(RESULT_DIR, "report")
VIDEO_DIR      = os.path.join(RESULT_DIR, "video")
SCREENSHOT_DIR = os.path.join(RESULT_DIR, "live_cam")
CALIB_PATH     = os.path.join(_THIS_DIR, "calibration.json")

for d in [REPORT_DIR, VIDEO_DIR, SCREENSHOT_DIR]:
    os.makedirs(d, exist_ok=True)


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  KALIBRASI: Save / Load                                                 ║
# ╚═════════════════════════════════════════════════════════════════════════╝

def load_calibration() -> dict:
    """Load config calibration.json."""
    if not os.path.exists(CALIB_PATH):
        return {}
    try:
        with open(CALIB_PATH) as f:
            data = json.load(f)
        ctype = data.get("type", 1)
        labels = {
            1: f"1-Point K-Factor  (K={data.get('K',0):.5f})",
            2: f"2-Point Linear    (m={data.get('m',0):.5f}, c={data.get('c',0):.5f})",
            3: f"3-Point Z-Grid    (poly_K degree={len(data.get('poly_K',[]))-1})",
            4: f"4-BBox Area Compen (m_ref={data.get('m_ref',0):.5f})",
            5: f"5-Geometric Proj.  (K_geom={data.get('K_geom',0):.5f})",
        }
        print(f"[CALIB] ✅ Loaded calibration model: {labels.get(ctype, 'Unknown')}")
        return data
    except Exception as e:
        print(f"[CALIB] ⚠ Failed to read calibration.json: {e}")
        return {}


def save_calibration_1p(K: float, z_tray_ref: float, ratio_ref: float, true_height: float):
    data = {
        "type": 1,
        "K": K,
        "z_tray_ref_cm": z_tray_ref,
        "ratio_ref": ratio_ref,
        "true_height_cm": true_height,
        "calibrated_at": datetime.now().isoformat()
    }
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Tersimpan 1-Point → {CALIB_PATH}")


def save_calibration_2p(m: float, c: float, data1: dict, data2: dict):
    data = {
        "type": 2,
        "m": m,
        "c": c,
        "data1": data1,
        "data2": data2,
        "calibrated_at": datetime.now().isoformat()
    }
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved 2-Point → {CALIB_PATH}")


def save_calibration_3p(poly_K: list, z_grid: list, true_height: float):
    data = {
        "type": 3,
        "poly_K": poly_K,
        "z_grid_points": z_grid,
        "true_height_cm": true_height,
        "calibrated_at": datetime.now().isoformat()
    }
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved Z-Grid (type 3) → {CALIB_PATH}")


def save_calibration_4p(m_ref: float, c_ref: float, ref_area: float, z_low: float, z_high: float, true_height: float):
    data = {
        "type": 4,
        "m_ref": m_ref,
        "c_ref": c_ref,
        "ref_bbox_area_px": ref_area,
        "z_ref": z_low,
        "z_high": z_high,
        "true_height_cm": true_height,
        "calibrated_at": datetime.now().isoformat()
    }
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved BBox Area (type 4) → {CALIB_PATH}")


def save_calibration_5p(K_geom: float, true_height: float):
    data = {
        "type": 5,
        "K_geom": K_geom,
        "true_height_cm": true_height,
        "calibrated_at": datetime.now().isoformat()
    }
    with open(CALIB_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CALIB] 💾 Saved Geometric Projection (type 5) → {CALIB_PATH}")


def calc_height_1point(m_rim: float, m_tray: float, z_tray: float, K: float) -> float:
    if m_tray <= 0 or z_tray <= 0: return 0.0
    ratio = m_rim / m_tray
    if ratio <= 0: return 0.0
    cup_height = z_tray * (1.0 - K / ratio)
    return cup_height if cup_height > 0 else 0.0


def calc_height_2point(m_rim: float, m_tray: float, z_tray: float, m: float, c: float) -> float:
    # H/Z = m * R + c
    if m_tray <= 0 or z_tray <= 0: return 0.0
    ratio = m_rim / m_tray
    if ratio <= 0: return 0.0
    cup_height = z_tray * (m * ratio + c)
    return cup_height if cup_height > 0 else 0.0


def calc_height_zgrid(m_rim: float, m_tray: float, z_tray: float, poly_K: list) -> float:
    """Option 2: Z-Grid Polynomial. K-factor is evaluated from polynomial at current z_tray."""
    if m_tray <= 0 or z_tray <= 0: return 0.0
    ratio = m_rim / m_tray
    if ratio <= 0: return 0.0
    K_live = float(np.polyval(poly_K, z_tray))
    cup_height = z_tray * (1.0 - K_live / ratio)
    return cup_height if cup_height > 0 else 0.0


def calc_height_bbox(m_rim: float, m_tray: float, z_tray: float, bbox: tuple,
                     m_ref: float, c_ref: float, ref_area: float) -> float:
    """Option 3: YOLO BBox Area Compensation — corrects m by the ratio of calibrated area vs live area."""
    if m_tray <= 0 or z_tray <= 0: return 0.0
    ratio = m_rim / m_tray
    if ratio <= 0: return 0.0
    x1, y1, x2, y2 = bbox
    live_area = max(1.0, float((x2 - x1) * (y2 - y1)))
    scale = ref_area / live_area
    m_adj = m_ref * scale
    cup_height = z_tray * (m_adj * ratio + c_ref)
    return cup_height if cup_height > 0 else 0.0


def calc_height_geom(z_tray: float, bbox: tuple, focal_length_px: float, K_geom: float) -> float:
    """Type 5: Pure Geometric Projection. H = Z * (bbox_h_px / focal_length) * K_geom.
    Inherently Z-invariant: when Z doubles, bbox_h_px halves, product stays constant."""
    if z_tray <= 0 or focal_length_px <= 0: return 0.0
    x1, y1, x2, y2 = bbox
    bbox_h_px = max(1.0, float(y2 - y1))
    cup_height = z_tray * (bbox_h_px / focal_length_px) * K_geom
    return cup_height if cup_height > 0 else 0.0


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  PIPELINE UTAMA                                                         ║
# ╚═════════════════════════════════════════════════════════════════════════╝

def run_pipeline(camera_idx: int, headless: bool, calib_data: dict,
                 marker_size: float, calibrate_mode: int, true_height: float, true_height_2: float,
                 n_positions: int = 3):
    print("=" * 55)
    print("  🚀  ArUco + MiDaS + YOLO  |  Cup Height Estimator")
    print("=" * 55)

    print("[INIT] Loading ArucoDetector...")
    aruco = ArucoDetector(marker_size_cm=marker_size)
    print("[INIT] Loading YoloDetector...")
    yolo  = YoloDetector()
    print("[INIT] Loading MidasDepthEstimator (this may take a while)...")
    midas = MidasDepthEstimator()
    print("[INIT] ✅ All detectors ready.\n")

    cap = cv2.VideoCapture(camera_idx)
    if not cap.isOpened():
        print(f"[ERROR] Tidak bisa membuka kamera index {camera_idx}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    time.sleep(2.0)
    for attempt in range(30):
        ret, _ = cap.read()
        if ret: break
        time.sleep(0.2)
    else:
        print("[ERROR] Kamera mati.")
        cap.release()
        return

    # ── 3a. State Mesin Sinkron (Calibration Mode) ───────────────
    if calibrate_mode in (1, 2):
        CALIB_WARMUP_SEC  = 5.0
        CALIB_SAMPLE_SEC  = 8.0
        
        if not headless:
            cv2.namedWindow("ArUco + MiDaS | Cup Height Estimator", cv2.WINDOW_NORMAL)
        
        calib_ratios_1, calib_z_trays_1 = [], []
        calib_ratios_2, calib_z_trays_2 = [], []
        
        phase = "warmup_1"
        calib_start = time.time()
        
        print(f"━" * 55)
        print(f"  ⚙  KALIBRASI BERSYARAT IN-SESSION ({calibrate_mode}-Point)")
        print(f"━" * 55)

        last_midas_calib = 0.0
        boxes = None
        
        while phase != "done":
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            elapsed = time.time() - calib_start
            h_f, w_f = frame.shape[:2]

            if last_midas_calib == 0.0 or (time.time() - last_midas_calib) > 1.0:
                # If YOLO didn't run recently, clear old boxes
                boxes = None

            aruco_results = aruco.detect(frame)
            z_calib = 0.0
            aruco_roi_c = None
            if aruco_results:
                best = aruco.get_best_distance(aruco_results)
                if best:
                    z_calib = best["distance_cm"]
                    corners = aruco_results[0].get("corners")
                    if corners is not None:
                        pts = np.array(corners, dtype=np.float32)
                        x1c, y1c = np.min(pts, axis=0).astype(int)
                        x2c, y2c = np.max(pts, axis=0).astype(int)
                        aruco_roi_c = (x1c + 2, y1c + 2, x2c - 2, y2c - 2)

            if (time.time() - last_midas_calib) > 0.2 and z_calib > 0 and aruco_roi_c:
                boxes = yolo.detect(frame)
                if boxes:
                    bbox_c = boxes[0]["bbox"]
                    dm = midas.process(frame)
                    last_midas_calib = time.time()

                    m_rim  = midas.get_rim_depth(dm, bbox_c)
                    m_tray = midas.get_tray_depth(dm, aruco_roi_c)

                    if m_rim > 0 and m_tray > 0:
                        if phase == "sampling_1":
                            calib_ratios_1.append(m_rim / m_tray)
                            calib_z_trays_1.append(z_calib)
                        elif phase == "sampling_2":
                            calib_ratios_2.append(m_rim / m_tray)
                            calib_z_trays_2.append(z_calib)
                else:
                    last_midas_calib = time.time()

            # Transisi fase otomatis per timer (dan sample count)
            if phase == "warmup_1" and elapsed >= CALIB_WARMUP_SEC:
                phase = "sampling_1"
                calib_start = time.time()  # Reset timer untuk sampling
                elapsed = 0.0
            elif phase == "sampling_1":
                if len(calib_ratios_1) >= 5:
                    if calibrate_mode == 1:
                        phase = "done"
                    else:
                        phase = "swap_wait"
                elif elapsed > 30.0:
                    print("[CALIB] Timeout: Cannot properly detect cup 1 (YOLO/ArUco failed).")
                    phase = "done"

            elif phase == "warmup_2" and elapsed >= CALIB_WARMUP_SEC:
                phase = "sampling_2"
                calib_start = time.time()
                elapsed = 0.0
            elif phase == "sampling_2":
                if len(calib_ratios_2) >= 5:
                    phase = "done"
                elif elapsed > 30.0:
                    print("[CALIB] Timeout: Cannot properly detect cup 2 (YOLO/ArUco failed).")
                    phase = "done"

            # UI Overlay Kalibrasi
            disp_c = frame.copy()
            if aruco_results:
                disp_c = aruco.annotate_frame(disp_c, aruco_results)

            # Gambar bounding box Yolo saat kalibrasi agar user tahu Yolo melihat gelasnya
            if boxes:
                for b in boxes:
                    x1c, y1c, x2c, y2c = b["bbox"]
                    cv2.rectangle(disp_c, (x1c, y1c), (x2c, y2c), (0, 255, 80), 2)

            cv2.rectangle(disp_c, (8, 8), (530, 95), (20, 20, 40), -1)
            cv2.rectangle(disp_c, (8, 8), (530, 95), (0, 200, 255), 1)

            # Indikator Hardware
            status_aruco = "OK" if z_calib > 0 else "NOT FOUND"
            status_yolo  = "OK" if boxes else "NOT FOUND"
            cv2.putText(disp_c, f"[ArUco: {status_aruco}]  [YOLO: {status_yolo}]", (18, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            if phase.startswith("warmup_"):
                idx = phase[-1]
                pct = min(100, int((elapsed / CALIB_WARMUP_SEC) * 100))
                H_t = true_height if idx == "1" else true_height_2
                cv2.putText(disp_c, f"WARMING UP CUP {idx} (H={H_t}cm)", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
                cv2.putText(disp_c, f"Keep cup still. Prog: {pct}%", (18, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 200, 255), 1)

            elif phase.startswith("sampling_"):
                idx = phase[-1]
                n = len(calib_ratios_1) if idx == "1" else len(calib_ratios_2)
                cv2.putText(disp_c, f"SAMPLING DATA CUP {idx} (Count: {n}/5)", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 180), 1)
                cv2.putText(disp_c, "Ensure camera and cup are visible...", (18, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 255, 200), 1)

            elif phase == "swap_wait":
                cv2.rectangle(disp_c, (8, 8), (530, 95), (200, 50, 50), -1)
                cv2.putText(disp_c, "SWAP THE CUP NOW", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(disp_c, f"Place a cup with height {true_height_2} cm on the tray.", (18, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 255), 1)
                cv2.putText(disp_c, "Then PRESS 'SPACE' to continue.", (18, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 255, 100), 1)

            if not headless:
                cv2.imshow("ArUco + MiDaS | Cup Height Estimator", disp_c)
                key = cv2.waitKey(1) & 0xFF
                if key == 27:
                    cap.release()
                    cv2.destroyAllWindows()
                    sys.exit(0)
                if phase == "swap_wait" and key == ord(' '):
                    calib_start = time.time()
                    phase = "warmup_2"

        # Hitung hasil kalibrasi
        if len(calib_ratios_1) < 3:
            print("[CALIB] Error: Insufficient data for cup 1.")
            return

        R1 = float(np.mean(calib_ratios_1))
        Z1 = float(np.mean(calib_z_trays_1))
        
        if calibrate_mode == 1:
            K_factor = R1 * (1.0 - true_height / Z1)
            save_calibration_1p(K_factor, Z1, R1, true_height)
            calib_data = {"type": 1, "K": K_factor}
        else:
            if len(calib_ratios_2) < 3:
                print("[CALIB] Error: Insufficient data for cup 2.")
                return
            R2 = float(np.mean(calib_ratios_2))
            Z2 = float(np.mean(calib_z_trays_2))
            
            # Linear Fit: H/Z = m * R + c
            # Titik 1: Y1 = H1/Z1, Titik 2: Y2 = H2/Z2
            Y1 = true_height / Z1
            Y2 = true_height_2 / Z2
            
            if abs(R2 - R1) < 0.05:
                print("[CALIB] Error: Both cups have nearly identical rim/tray ratio in MiDaS.")
                print("       Use cups with a wider height difference (e.g. 7.6cm and 11cm).")
                return
                
            m = (Y2 - Y1) / (R2 - R1)
            c = Y1 - m * R1
            save_calibration_2p(m, c, 
                                {"R": R1, "Z": Z1, "H": true_height}, 
                                {"R": R2, "Z": Z2, "H": true_height_2})
            calib_data = {"type": 2, "m": m, "c": c}
            
        print("[CALIB] ✅ Success. Entering LIVE mode!\n")

    # ── 3c. KALIBRASI Z-GRID (Type 3) ─────────────────────────────────────
    elif calibrate_mode == 3:
        print("━" * 55)
        print(f"  ⚙  Z-GRID CALIBRATION ({n_positions} positions)")
        print(f"     Cup reference height: {true_height} cm")
        print("━" * 55)

        CALIB_WARMUP_SEC = 4.0
        CALIB_SAMPLE_SEC = 6.0
        grid_data = []   # list of (z_avg, R_avg) per position
        pos_idx   = 0
        phase     = "warmup"
        calib_start = time.time()
        boxes = None
        last_midas_calib = 0.0
        pos_ratios, pos_z_trays = [], []

        while pos_idx < n_positions or phase not in ("done", "warmup"):
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            elapsed = time.time() - calib_start
            if last_midas_calib == 0.0 or (time.time() - last_midas_calib) > 1.0:
                boxes = None

            aruco_results = aruco.detect(frame)
            z_calib   = 0.0
            aruco_roi_c = None
            if aruco_results:
                best = aruco.get_best_distance(aruco_results)
                if best:
                    z_calib = best["distance_cm"]
                    corners = aruco_results[0].get("corners")
                    if corners is not None:
                        pts = np.array(corners, dtype=np.float32)
                        x1c, y1c = np.min(pts, axis=0).astype(int)
                        x2c, y2c = np.max(pts, axis=0).astype(int)
                        aruco_roi_c = (x1c+2, y1c+2, x2c-2, y2c-2)

            if (time.time() - last_midas_calib) > 0.2 and z_calib > 0 and aruco_roi_c and phase == "sampling":
                boxes = yolo.detect(frame)
                if boxes:
                    bbox_c = boxes[0]["bbox"]
                    dm = midas.process(frame)
                    last_midas_calib = time.time()
                    m_rim  = midas.get_rim_depth(dm, bbox_c)
                    m_tray = midas.get_tray_depth(dm, aruco_roi_c)
                    if m_rim > 0 and m_tray > 0:
                        pos_ratios.append(m_rim / m_tray)
                        pos_z_trays.append(z_calib)
                else:
                    last_midas_calib = time.time()

            if phase == "warmup" and elapsed >= CALIB_WARMUP_SEC:
                phase = "sampling"
                calib_start = time.time()
                elapsed = 0.0
            elif phase == "sampling":
                if len(pos_ratios) >= 5 or elapsed > 30.0:
                    # Commit this position
                    if len(pos_ratios) >= 3:
                        R_avg = float(np.mean(pos_ratios))
                        Z_avg = float(np.mean(pos_z_trays))
                        grid_data.append({"R": R_avg, "Z": Z_avg})
                        print(f"[CALIB] Position {pos_idx+1}/{n_positions} committed: Z={Z_avg:.2f}cm, R={R_avg:.4f}")
                    pos_ratios.clear()
                    pos_z_trays.clear()
                    pos_idx += 1
                    if pos_idx >= n_positions:
                        phase = "done"
                    else:
                        phase = "swap_wait"

            # UI
            disp_c = frame.copy()
            if aruco_results:
                disp_c = aruco.annotate_frame(disp_c, aruco_results)
            if boxes:
                for b in boxes:
                    x1b, y1b, x2b, y2b = b["bbox"]
                    cv2.rectangle(disp_c, (x1b, y1b), (x2b, y2b), (0, 255, 80), 2)
            cv2.rectangle(disp_c, (8, 8), (535, 100), (20, 20, 40), -1)
            cv2.rectangle(disp_c, (8, 8), (535, 100), (0, 200, 255), 1)
            status_a = "OK" if z_calib > 0 else "NOT FOUND"
            status_y = "OK" if boxes else "NOT FOUND"
            cv2.putText(disp_c, f"[ArUco: {status_a}]  [YOLO: {status_y}]", (18, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200,200,200), 1)

            if phase == "warmup":
                pct = min(100, int((elapsed/CALIB_WARMUP_SEC)*100))
                cv2.putText(disp_c, f"Z-GRID: Warming up position {pos_idx+1}/{n_positions}", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
                cv2.putText(disp_c, f"Keep cup + nozzle still. Prog: {pct}%", (18, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 200, 255), 1)
            elif phase == "sampling":
                cv2.putText(disp_c, f"Z-GRID: Sampling pos {pos_idx+1}/{n_positions} (Count: {len(pos_ratios)}/5)", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 180), 1)
                cv2.putText(disp_c, f"Z_tray = {z_calib:.1f} cm", (18, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 180, 60), 1)
            elif phase == "swap_wait":
                cv2.rectangle(disp_c, (8, 8), (535, 100), (160, 50, 30), -1)
                cv2.putText(disp_c, f"MOVE NOZZLE TO NEXT POSITION", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2)
                cv2.putText(disp_c, f"({pos_idx+1}/{n_positions} done)  Keep same cup visible.", (18, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 255), 1)
                cv2.putText(disp_c, "Press SPACE when ready.", (18, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 255, 100), 1)

            if not headless:
                cv2.imshow("ArUco + MiDaS | Cup Height Estimator", disp_c)
                key = cv2.waitKey(1) & 0xFF
                if key == 27:
                    cap.release(); cv2.destroyAllWindows(); sys.exit(0)
                if phase == "swap_wait" and key == ord(' '):
                    calib_start = time.time()
                    phase = "warmup"

            if phase == "done":
                break

        # Compute polynomial fit across grid points
        if len(grid_data) < 2:
            print("[CALIB] Not enough position data. Aborting.")
            return

        Z_pts  = np.array([p["Z"] for p in grid_data])
        R_pts  = np.array([p["R"] for p in grid_data])

        # K_i = R_i * (1.0 - H / Z_i)
        K_pts = R_pts * (1.0 - true_height / Z_pts)
        
        deg = min(len(grid_data) - 1, 2)
        poly_K = np.polyfit(Z_pts, K_pts, deg=deg).tolist()

        save_calibration_3p(poly_K, Z_pts.tolist(), true_height)
        calib_data = {"type": 3, "poly_K": poly_K}
        print("[CALIB] ✅ Z-Grid calibration done! Entering LIVE mode.\n")

    # ── 3d. KALIBRASI BBOX AREA (Type 4) ─────────────────────────────────
    elif calibrate_mode == 4:
        print("━" * 55)
        print("  ⚙  BBOX AREA COMPENSATION CALIBRATION (Type 4)")
        print(f"     Cup reference height: {true_height} cm")
        print("━" * 55)

        CALIB_WARMUP_SEC = 4.0
        positions_4 = []  # list of {R, Z, area}
        phase = "warmup"
        calib_start = time.time()
        boxes = None
        last_midas_calib = 0.0
        pos_ratios4, pos_z4, pos_areas4 = [], [], []
        pos_idx4 = 0
        N_POS_4  = 2  # low Z and high Z

        while pos_idx4 < N_POS_4:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05); continue

            elapsed = time.time() - calib_start
            if last_midas_calib == 0.0 or (time.time() - last_midas_calib) > 1.0:
                boxes = None

            aruco_results = aruco.detect(frame)
            z_calib = 0.0; aruco_roi_c = None
            if aruco_results:
                best = aruco.get_best_distance(aruco_results)
                if best:
                    z_calib = best["distance_cm"]
                    corners = aruco_results[0].get("corners")
                    if corners is not None:
                        pts = np.array(corners, dtype=np.float32)
                        x1c, y1c = np.min(pts, axis=0).astype(int)
                        x2c, y2c = np.max(pts, axis=0).astype(int)
                        aruco_roi_c = (x1c+2, y1c+2, x2c-2, y2c-2)

            if (time.time() - last_midas_calib) > 0.2 and z_calib > 0 and aruco_roi_c and phase == "sampling":
                boxes = yolo.detect(frame)
                if boxes:
                    bbox_c = boxes[0]["bbox"]
                    dm = midas.process(frame)
                    last_midas_calib = time.time()
                    m_rim4  = midas.get_rim_depth(dm, bbox_c)
                    m_tray4 = midas.get_tray_depth(dm, aruco_roi_c)
                    if m_rim4 > 0 and m_tray4 > 0:
                        x1b, y1b, x2b, y2b = bbox_c
                        area = float((x2b - x1b) * (y2b - y1b))
                        pos_ratios4.append(m_rim4 / m_tray4)
                        pos_z4.append(z_calib)
                        pos_areas4.append(area)
                else:
                    last_midas_calib = time.time()

            if phase == "warmup" and elapsed >= CALIB_WARMUP_SEC:
                phase = "sampling"; calib_start = time.time(); elapsed = 0.0
            elif phase == "sampling":
                if len(pos_ratios4) >= 5 or elapsed > 30.0:
                    if len(pos_ratios4) >= 3:
                        R_avg4 = float(np.mean(pos_ratios4))
                        Z_avg4 = float(np.mean(pos_z4))
                        A_avg4 = float(np.mean(pos_areas4))
                        positions_4.append({"R": R_avg4, "Z": Z_avg4, "area": A_avg4})
                        print(f"[CALIB] BBox pos {pos_idx4+1}/2 committed: Z={Z_avg4:.2f}cm, area={A_avg4:.0f}px²")
                    pos_ratios4.clear(); pos_z4.clear(); pos_areas4.clear()
                    pos_idx4 += 1
                    if pos_idx4 < N_POS_4:
                        phase = "swap_wait"

            # UI
            disp_c = frame.copy()
            if aruco_results: disp_c = aruco.annotate_frame(disp_c, aruco_results)
            if boxes:
                for b in boxes:
                    x1b,y1b,x2b,y2b = b["bbox"]
                    cv2.rectangle(disp_c,(x1b,y1b),(x2b,y2b),(0,255,80),2)
            cv2.rectangle(disp_c,(8,8),(535,100),(20,20,40),-1)
            cv2.rectangle(disp_c,(8,8),(535,100),(0,200,255),1)
            status_a = "OK" if z_calib > 0 else "NOT FOUND"
            status_y = "OK" if boxes else "NOT FOUND"
            cv2.putText(disp_c,f"[ArUco: {status_a}]  [YOLO: {status_y}]",(18,92),cv2.FONT_HERSHEY_SIMPLEX,0.4,(200,200,200),1)
            if phase == "warmup":
                pct = min(100, int((elapsed/CALIB_WARMUP_SEC)*100))
                cv2.putText(disp_c,f"BBOX-AREA: Warming up position {pos_idx4+1}/2",(18,30),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,200,255),1)
                cv2.putText(disp_c,f"Keep cup still. Prog: {pct}%",(18,58),cv2.FONT_HERSHEY_SIMPLEX,0.45,(150,200,255),1)
            elif phase == "sampling":
                n4 = len(pos_ratios4)
                cv2.putText(disp_c,f"BBOX-AREA: Sampling pos {pos_idx4+1}/2 (Count: {n4}/5)",(18,30),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,255,180),1)
                cv2.putText(disp_c,f"Z_tray = {z_calib:.1f} cm",(18,58),cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,180,60),1)
            elif phase == "swap_wait":
                cv2.rectangle(disp_c,(8,8),(535,100),(160,50,30),-1)
                cv2.putText(disp_c,"MOVE NOZZLE TO DIFFERENT HEIGHT",(18,32),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),2)
                cv2.putText(disp_c,"(1/2 done)  Keep same cup visible.",(18,58),cv2.FONT_HERSHEY_SIMPLEX,0.45,(200,220,255),1)
                cv2.putText(disp_c,"Press SPACE when ready.",(18,80),cv2.FONT_HERSHEY_SIMPLEX,0.45,(100,255,100),1)

            if not headless:
                cv2.imshow("ArUco + MiDaS | Cup Height Estimator", disp_c)
                key = cv2.waitKey(1) & 0xFF
                if key == 27: cap.release(); cv2.destroyAllWindows(); sys.exit(0)
                if phase == "swap_wait" and key == ord(' '):
                    calib_start = time.time(); phase = "warmup"

        if len(positions_4) < 2:
            print("[CALIB] Not enough BBox position data. Aborting.")
            return

        # Reference is position with largest bbox (closest camera = most detail = ref)
        ref = max(positions_4, key=lambda p: p["area"])
        # Compute m and c from reference point: H/Z = m_ref * R_ref + c_ref
        # Use 2-point linear from both measured points for a proper m_ref/c_ref
        p1, p2 = positions_4[0], positions_4[1]
        Y1_4  = true_height / p1["Z"]
        Y2_4  = true_height / p2["Z"]
        dR_4  = p2["R"] - p1["R"]
        m_ref4 = (Y2_4 - Y1_4) / dR_4 if abs(dR_4) > 0.02 else 0.15
        c_ref4 = Y1_4 - m_ref4 * p1["R"]

        save_calibration_4p(m_ref4, c_ref4, ref["area"], p1["Z"], p2["Z"], true_height)
        calib_data = {"type": 4, "m_ref": m_ref4, "c_ref": c_ref4, "ref_bbox_area_px": ref["area"]}
        print("[CALIB] ✅ BBox Area calibration done! Entering LIVE mode.\n")

    # ── 3e. KALIBRASI GEOMETRIC PROJECTION (Type 5) ──────────────────────
    elif calibrate_mode == 5:
        focal_length_px = aruco.camera_matrix[0, 0]
        print("━" * 55)
        print("  ⚙  GEOMETRIC PROJECTION CALIBRATION (Type 5)")
        print(f"     Cup reference height : {true_height} cm")
        print(f"     Camera focal length  : {focal_length_px:.1f} px")
        print("━" * 55)

        CALIB_WARMUP_SEC = 4.0
        phase = "warmup"
        calib_start = time.time()
        boxes = None
        last_det = 0.0
        g_z_samples, g_h_samples = [], []

        while phase != "done":
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05); continue

            elapsed = time.time() - calib_start
            if (time.time() - last_det) > 1.0:
                boxes = None

            aruco_results = aruco.detect(frame)
            z_calib = 0.0
            if aruco_results:
                best = aruco.get_best_distance(aruco_results)
                if best: z_calib = best["distance_cm"]

            # Sample YOLO bbox height at current Z
            if (time.time() - last_det) > 0.15 and z_calib > 0 and phase == "sampling":
                boxes = yolo.detect(frame)
                last_det = time.time()
                if boxes:
                    x1b, y1b, x2b, y2b = boxes[0]["bbox"]
                    bbox_h = float(y2b - y1b)
                    if bbox_h > 5:
                        g_z_samples.append(z_calib)
                        g_h_samples.append(bbox_h)

            if phase == "warmup" and elapsed >= CALIB_WARMUP_SEC:
                phase = "sampling"; calib_start = time.time(); elapsed = 0.0
            elif phase == "sampling":
                if len(g_z_samples) >= 20 or elapsed > 30.0:
                    phase = "done"

            # UI
            disp_c = frame.copy()
            if aruco_results: disp_c = aruco.annotate_frame(disp_c, aruco_results)
            if boxes:
                for b in boxes:
                    x1b, y1b, x2b, y2b = b["bbox"]
                    cv2.rectangle(disp_c, (x1b, y1b), (x2b, y2b), (0, 255, 80), 2)
            cv2.rectangle(disp_c, (8, 8), (535, 100), (20, 20, 40), -1)
            cv2.rectangle(disp_c, (8, 8), (535, 100), (0, 220, 120), 1)
            status_a = "OK" if z_calib > 0 else "NOT FOUND"
            status_y = "OK" if boxes else "NOT FOUND"
            cv2.putText(disp_c, f"[ArUco: {status_a}]  [YOLO: {status_y}]", (18, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            if phase == "warmup":
                pct = min(100, int((elapsed / CALIB_WARMUP_SEC) * 100))
                cv2.putText(disp_c, f"GEO-PROJ: Warming up... {pct}%", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1)
                cv2.putText(disp_c, f"Place cup H={true_height}cm in view. Keep still.", (18, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 220, 255), 1)
            elif phase == "sampling":
                n5 = len(g_z_samples)
                cv2.putText(disp_c, f"GEO-PROJ: Sampling ({n5}/20)", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 180), 1)
                cv2.putText(disp_c, f"Z_tray = {z_calib:.1f} cm  |  Keep cup visible", (18, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 255, 200), 1)

            if not headless:
                cv2.imshow("ArUco + MiDaS | Cup Height Estimator", disp_c)
                key = cv2.waitKey(1) & 0xFF
                if key == 27: cap.release(); cv2.destroyAllWindows(); sys.exit(0)

        if len(g_z_samples) < 3:
            print("[CALIB] Not enough geometric samples. Aborting.")
            return

        # K_geom = H_true / (Z * bbox_h_px / focal)
        Z_arr = np.array(g_z_samples)
        H_arr = np.array(g_h_samples)
        K_vals = true_height / (Z_arr * H_arr / focal_length_px)
        K_geom = float(np.median(K_vals))  # median is more robust than mean
        print(f"[CALIB] K_geom samples: {K_vals.round(4).tolist()}")
        print(f"[CALIB] K_geom (median) = {K_geom:.5f}")

        save_calibration_5p(K_geom, true_height)
        calib_data = {"type": 5, "K_geom": K_geom}
        print("[CALIB] ✅ Geometric Projection calibration done! Entering LIVE mode.\n")

    print(f"[CAMERA] Active (index={camera_idx}) | Headless={headless}")
    
    # ── 3b. State Asynchronous Pipeline (Live Mode) ────────────────────────
    MIDAS_FPS_LIMIT = 5.0
    midas_interval  = 1.0 / MIDAS_FPS_LIMIT
    last_midas_t    = 0.0

    z_tray_live:    float       = 0.0
    aruco_roi:      tuple | None = None
    cup_bbox:       tuple | None = None
    cup_height_ema: float | None = None
    last_depth_norm = None
    EMA_ALPHA = 0.35

    is_recording = False
    video_writer = None
    screenshot_paths = []

    stats_total_frames = 0
    stats_midas_runs = 0

    history_z_tray = []
    history_cup_h = []
    history_frames = []

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            now = time.time()
            stats_total_frames += 1
            h_frame, w_frame = frame.shape[:2]

            aruco_results = aruco.detect(frame)
            if aruco_results:
                best = aruco.get_best_distance(aruco_results)
                if best:
                    z_tray_live = best["distance_cm"]
                    corners = aruco_results[0].get("corners")
                    if corners is not None:
                        pts  = np.array(corners, dtype=np.float32)
                        x1, y1 = np.min(pts, axis=0).astype(int)
                        x2, y2 = np.max(pts, axis=0).astype(int)
                        pad_x  = max(2, (x2 - x1) // 10)
                        pad_y  = max(2, (y2 - y1) // 10)
                        aruco_roi = (x1 + pad_x, y1 + pad_y, x2 - pad_x, y2 - pad_y)

            if (now - last_midas_t) >= midas_interval and z_tray_live > 0 and aruco_roi:
                boxes = yolo.detect(frame)
                if boxes:
                    cup_bbox = boxes[0]["bbox"]
                    depth_map  = midas.process(frame)
                    stats_midas_runs += 1

                    depth_norm = cv2.normalize(depth_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    last_depth_norm = depth_norm
                    m_rim  = midas.get_rim_depth(depth_map, cup_bbox)
                    m_tray = midas.get_tray_depth(depth_map, aruco_roi)

                    if m_tray > 0 and m_rim > 0:
                        ctype = calib_data.get("type", 1)
                        if ctype == 2:
                            height_raw = calc_height_2point(m_rim, m_tray, z_tray_live,
                                                            calib_data.get("m", 0.1), calib_data.get("c", 0.0))
                        elif ctype == 3:
                            height_raw = calc_height_zgrid(m_rim, m_tray, z_tray_live,
                                                           calib_data.get("poly_K", [0.8]))
                        elif ctype == 4:
                            height_raw = calc_height_bbox(m_rim, m_tray, z_tray_live, cup_bbox,
                                                          calib_data.get("m_ref", 0.15),
                                                          calib_data.get("c_ref", 0.0),
                                                          calib_data.get("ref_bbox_area_px", 10000.0))
                        elif ctype == 5:
                            focal_px = aruco.camera_matrix[0, 0]
                            height_raw = calc_height_geom(z_tray_live, cup_bbox, focal_px,
                                                          calib_data.get("K_geom", 1.0))
                        else:
                            height_raw = calc_height_1point(m_rim, m_tray, z_tray_live, calib_data.get("K", 0.8))

                        if height_raw > 0:
                            if cup_height_ema is None:
                                cup_height_ema = height_raw
                            else:
                                cup_height_ema = (EMA_ALPHA * height_raw) + ((1.0 - EMA_ALPHA) * cup_height_ema)

                            history_z_tray.append(z_tray_live)
                            history_cup_h.append(cup_height_ema)
                            history_frames.append(stats_total_frames)

                else:
                    cup_bbox = None
                    cup_height_ema = None
                    history_z_tray.append(z_tray_live)
                    history_cup_h.append(0.0)
                    history_frames.append(stats_total_frames)

                last_midas_t = now

            disp = frame.copy()
            if aruco_results:
                disp = aruco.annotate_frame(disp, aruco_results)
            if aruco_roi:
                cv2.rectangle(disp, aruco_roi[:2], aruco_roi[2:], (255, 140, 0), 1)
            if cup_bbox:
                x1c, y1c, x2c, y2c = cup_bbox
                cv2.rectangle(disp, (x1c, y1c), (x2c, y2c), (0, 255, 80), 2)

            cv2.rectangle(disp, (8, 8), (420, 90), (25, 25, 25), -1)
            cv2.rectangle(disp, (8, 8), (420, 90), (90, 90, 90), 1)

            if last_depth_norm is not None:
                depth_color = cv2.applyColorMap(last_depth_norm, cv2.COLORMAP_JET)
                pip_h, pip_w = int(h_frame / 3.0), int(w_frame / 3.0)
                depth_resized = cv2.resize(depth_color, (pip_w, pip_h))
                pip_y1 = h_frame - pip_h - 26
                pip_y2 = h_frame - 26
                pip_x1 = w_frame - pip_w - 5
                pip_x2 = w_frame - 5
                disp[pip_y1:pip_y2, pip_x1:pip_x2] = depth_resized
                cv2.rectangle(disp, (pip_x1, pip_y1), (pip_x2, pip_y2), (200, 200, 200), 2)
                cv2.putText(disp, "MiDaS Depth", (pip_x1 + 6, pip_y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

            z_rim_val = (z_tray_live - cup_height_ema) if (z_tray_live > 0 and cup_height_ema and cup_height_ema > 0) else 0.0

            cv2.putText(disp, "CUP HEIGHT", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (170, 170, 170), 1)
            cv2.putText(disp, f"Z_tray: {z_tray_live:.1f} cm", (210, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 160, 60), 1)
            
            if z_rim_val > 0:
                cv2.putText(disp, f"Z_rim : {z_rim_val:.1f} cm", (210, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 255, 100), 1)
            else:
                cv2.putText(disp, f"Z_rim : -- cm", (210, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 100), 1)

            if cup_height_ema and cup_height_ema > 0:
                cv2.putText(disp, f"{cup_height_ema:.1f} cm", (18, 75), cv2.FONT_HERSHEY_DUPLEX, 1.4, (0, 255, 100), 2)
            else:
                hint = "Waiting for marker..." if z_tray_live == 0 else "Waiting for cup..."
                cv2.putText(disp, "-- cm", (18, 75), cv2.FONT_HERSHEY_DUPLEX, 1.4, (70, 70, 70), 2)
                cv2.putText(disp, hint, (220, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 130, 255), 1)

            if is_recording:
                if int(time.time() * 2) % 2 == 0:
                    cv2.circle(disp, (w_frame - 65, 25), 6, (0, 0, 255), -1)
                    cv2.putText(disp, "REC", (w_frame - 50, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                if video_writer is not None:
                    video_writer.write(disp)

            cv2.rectangle(disp, (0, h_frame - 26), (w_frame, h_frame), (15, 15, 15), -1)
            bar_txt = f"ArUco: {'OK' if z_tray_live else 'X'} | YOLO: {'OK' if cup_bbox else 'X'} | [R] Record  [S] Screen  [Q] Quit"
            cv2.putText(disp, bar_txt, (10, h_frame - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (130, 200, 130), 1)

            if not headless:
                cv2.imshow("ArUco + MiDaS | Cup Height Estimator", disp)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord('q')):
                    break
                elif key == ord('s'):
                    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                    ss_path = os.path.join(SCREENSHOT_DIR, f"fusion_{ts}.jpg")
                    cv2.imwrite(ss_path, disp)
                    screenshot_paths.append(ss_path)
                    print(f"[SHOT] Screenshot tersimpan: {ss_path}")
                elif key == ord('r'):
                    if not is_recording:
                        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                        vid_path = os.path.join(VIDEO_DIR, f"fusion_{ts}.mp4")
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        fps_cap = cap.get(cv2.CAP_PROP_FPS) or 30.0
                        video_writer = cv2.VideoWriter(vid_path, fourcc, fps_cap, (w_frame, h_frame))
                        is_recording = True
                        print(f"🔴 [REC] Mulai merekam video: {vid_path}")
                    else:
                        is_recording = False
                        if video_writer: video_writer.release()
                        video_writer = None
                        print("⏹ [REC] Merekam dihentikan.")
            else:
                if (now - last_midas_t) < 0.05:
                    status = "DETECTED" if cup_height_ema and cup_height_ema > 0 else "NO_CUP"
                    h_str  = f"{cup_height_ema:.2f}" if cup_height_ema else "0.00"
                    print(f"[DATA] z_tray={z_tray_live:.2f}cm | status={status} | height={h_str}cm")
    
    except KeyboardInterrupt:
        print("\n[INFO] Execution stopped by user (Ctrl+C).")
        
    finally:
        if video_writer: video_writer.release()
        cap.release()
        if not headless: cv2.destroyAllWindows()

        print("\n[DONE] Pipeline closed. Generating Final Report...")
        _generate_session_report(
            calib_data=calib_data,
            marker_size_cm=marker_size,
            focal_len=aruco.camera_matrix[0,0],
            total_frames=stats_total_frames,
            midas_runs=stats_midas_runs,
            history_z_tray=history_z_tray,
            history_cup_h=history_cup_h,
            history_frames=history_frames,
            screenshots=screenshot_paths
        )

# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  REPORT GENERATOR                                                       ║
# ╚═════════════════════════════════════════════════════════════════════════╝

def _generate_session_report(calib_data, marker_size_cm, focal_len, total_frames, midas_runs,
                             history_z_tray, history_cup_h, history_frames, screenshots):
    
    valid_cups = [h for h in history_cup_h if h > 0]
    valid_trays = [z for z in history_z_tray if z > 0]
    
    avg_h = float(np.mean(valid_cups)) if valid_cups else 0.0
    avg_z = float(np.mean(valid_trays)) if valid_trays else 0.0
    std_h = float(np.std(valid_cups)) if valid_cups else 0.0
    max_h = float(np.max(valid_cups)) if valid_cups else 0.0
    min_h = float(np.min(valid_cups)) if valid_cups else 0.0

    print("="*50)
    print("📊 ARUCO+MIDAS FUSION SESSION REPORT")
    print("="*50)
    print(f"Total Camera Frames : {total_frames}")
    print(f"Total MiDaS Inferences: {midas_runs}")
    print(f"Average Tray Z-dist : {avg_z:.2f} cm")
    print(f"Average Cup Height  : {avg_h:.2f} cm")
    print(f"Cup Height Variance : ± {std_h:.2f} cm")
    print("="*50 + "\n")
    
    if not history_frames:
        return

    ts_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_folder = os.path.join(REPORT_DIR, ts_folder)
    os.makedirs(report_folder, exist_ok=True)
    
    plt.figure(figsize=(10, 6))
    plt.plot(history_frames, history_z_tray, label='Z_tray (ArUco)', color='blue', alpha=0.6)
    plt.plot(history_frames, history_cup_h, label='Cup Height (Fusion)', color='green', linewidth=2)
    if avg_h > 0:
        plt.axhline(y=avg_h, color='red', linestyle='--', label=f'Avg Cup Height: {avg_h:.2f}cm')
    plt.title("ArUco + MiDaS Fusion Pipeline Tracker")
    plt.xlabel("Frame Number (MiDaS executions)")
    plt.ylabel("Centimeters (cm)")
    plt.grid(True, linestyle=':', alpha=0.7)
    plt.legend()
    chart_path = os.path.join(report_folder, "session_chart.png")
    plt.savefig(chart_path)
    plt.close()
    
    ss_target = []
    if screenshots:
        ss_sub = os.path.join(report_folder, "screenshots")
        os.makedirs(ss_sub, exist_ok=True)
        for s in screenshots:
            basename = os.path.basename(s)
            dst = os.path.join(ss_sub, basename)
            shutil.copy2(s, dst)
            ss_target.append(f"screenshots/{basename}")
            
    md_path = os.path.join(report_folder, "report.md")
    with open(md_path, "w") as f:
        f.write("# ArUco + MiDaS Fusion Session Report\n\n")
        f.write(f"**Date/Time:** {ts_folder.replace('_', ' ')}\n\n")

        f.write("## 1. Parameters\n")
        f.write("Parameters used during this AI depth fusion session:\n\n")
        f.write("| Parameter | Value |\n")
        f.write("| :--- | :--- |\n")
        f.write(f"| **Physical Marker Size** | {marker_size_cm} cm |\n")
        
        calib_str = "1-Point K-Factor"
        if calib_data.get("type") == 2:
            calib_str = f"2-Point Linear (m={calib_data.get('m',0):.5f}, c={calib_data.get('c',0):.5f})"
        elif calib_data.get("type") == 1:
            calib_str = f"1-Point K-Factor (K={calib_data.get('K',0):.5f})"
            
        f.write(f"| **Calibration Model** | {calib_str} |\n")
        f.write(f"| **Camera Focal Length** | {focal_len:.1f} px |\n\n")

        f.write("## 2. Global Stability Summary\n")
        f.write("Statistical summary of cup height predictions gathered over the running frames:\n\n")
        
        f.write("| Metric | Value | Description |\n")
        f.write("| :--- | :--- | :--- |\n")
        f.write(f"| **Average Cup Height** | **{avg_h:.2f} cm** | Mean of all valid predictions. |\n")
        if valid_cups:
            p50 = float(np.median(valid_cups))
            p95 = float(np.percentile(valid_cups, 95))
            p05 = float(np.percentile(valid_cups, 5))
            f.write(f"| **Median Height (P50)** | **{p50:.2f} cm** | Most representative single value. |\n")
            f.write(f"| **Precision Error (P95−P5)** | **{p95 - p05:.2f} cm** | 90% of readings fall within this range. |\n")
        f.write(f"| **Standard Deviation ($\sigma$)** | {std_h:.2f} cm | Consistency / jitter of the AI model. |\n")
        f.write(f"| **Tray Anchor Depth (Z)** | {avg_z:.2f} cm | Average physical depth of the tray. |\n")
        f.write(f"| **Minimum / Maximum Height** | {min_h:.2f} / {max_h:.2f} cm | Extremes recorded. |\n")
        f.write(f"| **Total Frames / Inferences** | {total_frames} / {midas_runs} | Pipeline tracking efficiency. |\n\n")

        f.write("## 3. Visual Evidence\n")
        f.write("### Depth Tracking Chart\n")
        f.write("![Session Chart](session_chart.png)\n\n")
        
        if ss_target:
            f.write("## 4. Screenshots\n")
            for ss in ss_target:
                f.write(f"- ![{ss}]({ss})\n")

    json_path = os.path.join(report_folder, "session_data.json")
    json_data = {
        "session_timestamp": ts_folder,
        "parameters": {
            "marker_size_cm": marker_size_cm,
            "calibration_model": calib_data,
            "focal_length_px": float(focal_len)
        },
        "summary": {
            "total_frames": total_frames,
            "midas_inferences": midas_runs,
            "avg_cup_height_cm": avg_h,
            "min_cup_height_cm": min_h,
            "max_cup_height_cm": max_h,
            "std_dev_cup_height_cm": std_h,
            "avg_z_tray_cm": avg_z
        },
        "frame_metrics_history": {
            "frame_indices": history_frames,
            "z_tray_history": history_z_tray,
            "cup_height_history": history_cup_h
        },
        "screenshots": ss_target
    }
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    size_kb = os.path.getsize(json_path) / 1024
    print(f"Report saved to: {report_folder} (Including session_data.json {size_kb:.1f} KB)")

# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  ENTRY POINT                                                            ║
# ╚═════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ArUco + MiDaS Cup Height Estimator")
    ap.add_argument("--camera",       type=int,   default=0,     help="Index kamera (default: 0)")
    ap.add_argument("--headless",     action="store_true",        help="Tanpa UI — mode terminal")
    ap.add_argument("--marker-size",  type=float, default=5.0,   help="Ukuran Fisik ArUco di meja (cm)")
    ap.add_argument("--calibrate",    type=int,   default=0, choices=[0,1,2,3,4,5],
                    help="0: Live  1: 1-Point  2: 2-Point  3: Z-Grid  4: BBox Area  5: Geometric (recommended)")
    ap.add_argument("--true-height",  type=float, default=None,  help="Reference cup height in cm.")
    ap.add_argument("--true-height-2",type=float, default=None,  help="Second cup height for 2-point calibration.")
    ap.add_argument("--n-positions",  type=int,   default=3,     help="Number of Z positions for Z-Grid calibration (type 3). Default: 3")

    args = ap.parse_args()

    calib_data = {}
    if args.calibrate > 0:
        if args.calibrate in (1, 3, 4, 5) and args.true_height is None:
            print(f"[ERROR] Calibration mode {args.calibrate} requires --true-height")
            sys.exit(1)
        if args.calibrate == 2 and (args.true_height is None or args.true_height_2 is None):
            print("[ERROR] 2-Point calibration requires --true-height AND --true-height-2")
            print("Example: --calibrate 2 --true-height 7.6 --true-height-2 10.2")
            sys.exit(1)
    else:
        calib_data = load_calibration()
        if not calib_data:
            print("[ERROR] calibration.json not found! Calibrate first, e.g.:")
            print("  python run_fusion.py --calibrate 5 --true-height 7.6")
            sys.exit(1)

    run_pipeline(
        camera_idx=args.camera,
        headless=args.headless,
        calib_data=calib_data,
        marker_size=args.marker_size,
        calibrate_mode=args.calibrate,
        true_height=args.true_height or 0.0,
        true_height_2=args.true_height_2 or 0.0,
        n_positions=args.n_positions
    )
