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
        if ctype == 1:
            print(f"[CALIB] ✅ Ditemukan model 1-Point. K={data.get('K',0):.5f}")
        else:
            print(f"[CALIB] ✅ Ditemukan model 2-Point. m={data.get('m',0):.5f}, c={data.get('c',0):.5f}")
        return data
    except Exception as e:
        print(f"[CALIB] ⚠ Gagal baca calibration.json: {e}")
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
    print(f"[CALIB] 💾 Tersimpan 2-Point → {CALIB_PATH}")


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


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  PIPELINE UTAMA                                                         ║
# ╚═════════════════════════════════════════════════════════════════════════╝

def run_pipeline(camera_idx: int, headless: bool, calib_data: dict,
                 marker_size: float, calibrate_mode: int, true_height: float, true_height_2: float):
    print("=" * 55)
    print("  🚀  ArUco + MiDaS + YOLO  |  Cup Height Estimator")
    print("=" * 55)

    print("[INIT] Memuat ArucoDetector...")
    aruco = ArucoDetector(marker_size_cm=marker_size)
    print("[INIT] Memuat YoloDetector...")
    yolo  = YoloDetector()
    print("[INIT] Memuat MidasDepthEstimator (butuh waktu)...")
    midas = MidasDepthEstimator()
    print("[INIT] ✅ Semua detektor siap.\n")

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

    # ── 3a. KALIBRASI IN-SESSION ──────────────────────────────────────────
    if calibrate_mode > 0:
        CALIB_WARMUP_SEC  = 5.0
        CALIB_SAMPLE_SEC  = 8.0
        
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
                    print("[CALIB] Timeout: Tidak bisa mendeteksi gelas 1 dengan benar (YOLO/ArUco gagal).")
                    phase = "done"

            elif phase == "warmup_2" and elapsed >= CALIB_WARMUP_SEC:
                phase = "sampling_2"
                calib_start = time.time()
                elapsed = 0.0
            elif phase == "sampling_2":
                if len(calib_ratios_2) >= 5:
                    phase = "done"
                elif elapsed > 30.0:
                    print("[CALIB] Timeout: Tidak bisa mendeteksi gelas 2 dengan benar (YOLO/ArUco gagal).")
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
            status_aruco = "OK" if z_calib > 0 else "TIDAK DITEMUKAN"
            status_yolo  = "OK" if boxes else "TIDAK DITEMUKAN"
            cv2.putText(disp_c, f"[ArUco: {status_aruco}]  [YOLO: {status_yolo}]", (18, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            if phase.startswith("warmup_"):
                idx = phase[-1]
                pct = min(100, int((elapsed / CALIB_WARMUP_SEC) * 100))
                H_t = true_height if idx == "1" else true_height_2
                cv2.putText(disp_c, f"PEMANASAN GELAS {idx} (H={H_t}cm)", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
                cv2.putText(disp_c, f"Jangan sentuh/pindah gelas. Prog: {pct}%", (18, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 200, 255), 1)

            elif phase.startswith("sampling_"):
                idx = phase[-1]
                n = len(calib_ratios_1) if idx == "1" else len(calib_ratios_2)
                cv2.putText(disp_c, f"MENGAMBIL DATA GELAS {idx} (Terkumpul: {n}/5)", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 180), 1)
                cv2.putText(disp_c, "Pastikan kamera diam & melihat gelas utuh...", (18, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 255, 200), 1)

            elif phase == "swap_wait":
                cv2.rectangle(disp_c, (8, 8), (530, 95), (200, 50, 50), -1)
                cv2.putText(disp_c, "GANTI GELAS SEKARANG", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(disp_c, f"Letakkan gelas setinggi {true_height_2} cm di nampan.", (18, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 220, 255), 1)
                cv2.putText(disp_c, "Lalu TEKAN 'SPC' (SPASI) untuk lanjut.", (18, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 255, 100), 1)

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
            print("[CALIB] Error: Data gelas 1 tidak cukup.")
            return

        R1 = float(np.mean(calib_ratios_1))
        Z1 = float(np.mean(calib_z_trays_1))
        
        if calibrate_mode == 1:
            K_factor = R1 * (1.0 - true_height / Z1)
            save_calibration_1p(K_factor, Z1, R1, true_height)
            calib_data = {"type": 1, "K": K_factor}
        else:
            if len(calib_ratios_2) < 3:
                print("[CALIB] Error: Data gelas 2 tidak cukup.")
                return
            R2 = float(np.mean(calib_ratios_2))
            Z2 = float(np.mean(calib_z_trays_2))
            
            # Linear Fit: H/Z = m * R + c
            # Titik 1: Y1 = H1/Z1, Titik 2: Y2 = H2/Z2
            Y1 = true_height / Z1
            Y2 = true_height_2 / Z2
            
            if abs(R2 - R1) < 0.05:
                print("[CALIB] Error: Kedua gelas memiliki ukuran bibir/jarak yang terlalu identik di mata MiDaS.")
                print("       Gunakan gelas yang tingginya terpaut agak jauh (misal 7.6cm dan 11cm).")
                return
                
            m = (Y2 - Y1) / (R2 - R1)
            c = Y1 - m * R1
            save_calibration_2p(m, c, 
                                {"R": R1, "Z": Z1, "H": true_height}, 
                                {"R": R2, "Z": Z2, "H": true_height_2})
            calib_data = {"type": 2, "m": m, "c": c}
            
        print("[CALIB] ✅ Berhasil. Masuk LIVE mode!\n")

    print(f"[CAMERA] Aktif (index={camera_idx}) | Headless={headless}")
    
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
                        if calib_data.get("type") == 2:
                            m_val = calib_data.get("m", 0.1)
                            c_val = calib_data.get("c", 0.0)
                            height_raw = calc_height_2point(m_rim, m_tray, z_tray_live, m_val, c_val)
                        else:
                            K_val = calib_data.get("K", 0.8)
                            height_raw = calc_height_1point(m_rim, m_tray, z_tray_live, K_val)

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

            cv2.putText(disp, "CUP HEIGHT", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (170, 170, 170), 1)
            cv2.putText(disp, f"Z_tray: {z_tray_live:.1f} cm", (210, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 160, 60), 1)

            if cup_height_ema and cup_height_ema > 0:
                cv2.putText(disp, f"{cup_height_ema:.1f} cm", (18, 75), cv2.FONT_HERSHEY_DUPLEX, 1.4, (0, 255, 100), 2)
            else:
                hint = "Tunggu marker..." if z_tray_live == 0 else "Belum Mendeteksi Gelas..."
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
        print("\n[INFO] Eksekusi dihentikan oleh user (Ctrl+C).")
        
    finally:
        if video_writer: video_writer.release()
        cap.release()
        if not headless: cv2.destroyAllWindows()

        print("\n[DONE] Pipeline ditutup. Mempersiapkan Laporan Akhir...")
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
    print(f"Laporan tercetak di: {report_folder} (Termasuk session_data.json {size_kb:.1f} KB)")

# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  ENTRY POINT                                                            ║
# ╚═════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ArUco + MiDaS Cup Height Estimator")
    ap.add_argument("--camera",       type=int,   default=0,     help="Index kamera (default: 0)")
    ap.add_argument("--headless",     action="store_true",        help="Tanpa UI — mode terminal")
    ap.add_argument("--marker-size",  type=float, default=5.0,   help="Ukuran Fisik ArUco di meja (cm)")
    ap.add_argument("--calibrate",    type=int,   default=0, choices=[0,1,2], help="0: Live, 1: Kalibrasi 1-Point, 2: Kalibrasi 2-Point")
    ap.add_argument("--true-height",  type=float, default=None,  help="Tinggi gelas (cm) untuk 1-Point atau Gelas ke-1 di 2-Point.")
    ap.add_argument("--true-height-2",type=float, default=None,  help="Tinggi gelas ke-2 (cm) khusus untuk 2-Point kalibrasi.")

    args = ap.parse_args()

    calib_data = {}
    if args.calibrate > 0:
        if args.calibrate == 1 and args.true_height is None:
            print("[ERROR] 1-Point kalibrasi butuh --true-height")
            sys.exit(1)
        if args.calibrate == 2 and (args.true_height is None or args.true_height_2 is None):
            print("[ERROR] 2-Point kalibrasi butuh --true-height DAN --true-height-2")
            print("Contoh: --calibrate 2 --true-height 7.6 --true-height-2 10.2")
            sys.exit(1)
    else:
        calib_data = load_calibration()
        if not calib_data:
            print("[ERROR] calibration.json tidak ada! Harap kalibrasi dulu:")
            print("  python run_fusion.py --calibrate 2 --true-height 7.6 --true-height-2 10.2")
            sys.exit(1)

    run_pipeline(
        camera_idx=args.camera,
        headless=args.headless,
        calib_data=calib_data,
        marker_size=args.marker_size,
        calibrate_mode=args.calibrate,
        true_height=args.true_height or 0.0,
        true_height_2=args.true_height_2 or 0.0
    )
