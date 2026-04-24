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

import core.calibration_storage as cs
import core.height_math as hm
import core.session_reporter as sr

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
# For module
sr.REPORT_DIR = REPORT_DIR
VIDEO_DIR      = os.path.join(RESULT_DIR, "video")
SCREENSHOT_DIR = os.path.join(RESULT_DIR, "live_cam")
CALIB_PATH     = os.path.join(_THIS_DIR, "calibration.json")

for d in [REPORT_DIR, VIDEO_DIR, SCREENSHOT_DIR]:
    os.makedirs(d, exist_ok=True)


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
        ret, tmp_frame = cap.read()
        if ret: break
        time.sleep(0.2)
    else:
        print("[ERROR] Kamera mati.")
        cap.release()
        return

    fisheye_map1 = None
    fisheye_map2 = None
    if getattr(args, "fisheye", False):
        try:
            import yaml
            params_path = os.path.join(os.path.dirname(__file__), "focal_length_calibration.yaml")
            with open(params_path, "r") as f:
                f_cal = yaml.safe_load(f)
            K = np.array(f_cal["camera_matrix"])
            D = np.array(f_cal["dist_coeffs"])
            
            h, w = tmp_frame.shape[:2]
            if f_cal.get("is_fisheye_model"):
                new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(K, D, (w,h), np.eye(3), balance=1.0)
                fisheye_map1, fisheye_map2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), new_K, (w,h), cv2.CV_16SC2)
            else:
                new_K, roi = cv2.getOptimalNewCameraMatrix(K, D, (w,h), 1, (w,h))
                fisheye_map1, fisheye_map2 = cv2.initUndistortRectifyMap(K, D, None, new_K, (w,h), cv2.CV_16SC2)
            
            aruco.camera_matrix = new_K
            print(f"[FISHEYE] Loaded camera params: fx={new_K[0,0]:.1f}, fy={new_K[1,1]:.1f}")
        except Exception as e:
            print(f"[FISHEYE ERROR] {e}. Did you run calibrate_fisheye.py first?")

    def get_frame():
        r, f = cap.read()
        if r and fisheye_map1 is not None and fisheye_map2 is not None:
            f = cv2.remap(f, fisheye_map1, fisheye_map2, interpolation=cv2.INTER_LINEAR)
        return r, f


    # Delegate to calibration routines
    import core.calibration_routines as calib_rt
    
    if calibrate_mode in (1, 2):
        calib_data = calib_rt.run_calib_1p_2p(get_frame, cap, aruco, yolo, midas, headless, true_height, true_height_2, calibrate_mode)
    elif calibrate_mode == 3:
        calib_data = calib_rt.run_calib_zgrid(get_frame, cap, aruco, yolo, midas, headless, true_height, n_positions)
    elif calibrate_mode == 4:
        calib_data = calib_rt.run_calib_bbox(get_frame, cap, aruco, yolo, midas, headless, true_height)
    elif calibrate_mode == 5:
        calib_data = calib_rt.run_calib_geom(get_frame, cap, aruco, yolo, midas, headless, true_height, n_positions)
    elif calibrate_mode == 6:
        calib_data = calib_rt.run_calib_bilateral(get_frame, cap, aruco, yolo, midas, headless, true_height, true_height_2, n_positions)
    elif calibrate_mode == 7:
        calib_data = calib_rt.run_calib_analytic(get_frame, cap, aruco, yolo, midas, headless, true_height, true_height_2)
    elif calibrate_mode != 0:
        print("[ERROR] Unknown calibration mode")
        return

    if calib_data is None:
        print("[CALIB] Error or Aborted. Exiting.")
        return

    active_poly_Kgeom = [1.0]
    active_cup_str = "LEGACY (1 Profile)"
    if calib_data.get("type") == 5:
        if "profiles" in calib_data:
            if getattr(args, "target_cup", None):
                target_str = str(args.target_cup)
                if target_str in calib_data["profiles"]:
                    active_poly_Kgeom = calib_data["profiles"][target_str]["poly_Kgeom"]
                    active_cup_str = target_str
                else:
                    keys = list(calib_data["profiles"].keys())
                    active_cup_str = keys[0] if keys else "Unknown"
                    active_poly_Kgeom = calib_data["profiles"][active_cup_str].get("poly_Kgeom", [1.0]) if keys else [1.0]
            else:
                keys = list(calib_data["profiles"].keys())
                active_cup_str = keys[0] if keys else "Unknown"
                active_poly_Kgeom = calib_data["profiles"][active_cup_str].get("poly_Kgeom", [1.0]) if keys else [1.0]
        else:
            active_poly_Kgeom = calib_data.get("poly_Kgeom", [1.0])
            
    # Delegate to live pipeline
    import core.live_pipeline as live_pipe
    live_pipe.run_live_pipeline(get_frame, cap, aruco, yolo, midas, headless, calib_data, marker_size, active_poly_Kgeom, active_cup_str, args, SCREENSHOT_DIR, VIDEO_DIR)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ArUco + MiDaS Cup Height Estimator")
    ap.add_argument("--camera",       type=int,   default=0,     help="Index kamera (default: 0)")
    ap.add_argument("--headless",     action="store_true",        help="Tanpa UI — mode terminal")
    ap.add_argument("--marker-size",  type=float, default=5.0,   help="Ukuran Fisik ArUco di meja (cm)")
    ap.add_argument("--calibrate",    type=int,   default=0, choices=[0,1,2,3,4,5,6,7],
                    help="0:Live 1:1Pt 2:2Pt 3:ZGrid 4:BBox 5:Geom 6:Bilateral 7:Analytic")
    ap.add_argument("--true-height",  type=float, default=None,  help="Reference cup height in cm.")
    ap.add_argument("--true-height-2",type=float, default=None,  help="Second cup height for 2-point calibration.")
    ap.add_argument("--target-cup",   type=float, default=None,  help="LIVE MODE: specify the target menu cup height to monitor (e.g. 7.6 or 11.4)")
    ap.add_argument("--n-positions",  type=int,   default=3,     help="Number of Z positions for Z-Grid calibration. Default: 3")
    ap.add_argument("--cup-profile",  type=str,   default="default", help="Nama profil gelas (misal: short, tall) untuk membedakan file kalibrasi.")
    ap.add_argument("--fisheye",      action="store_true", help="Enable fisheye undistortion menggunakan focal_length_calibration.yaml")

    args = ap.parse_args()

    if args.fisheye:
        CALIB_PATH = os.path.join(_THIS_DIR, f"calibration_fisheye_{args.cup_profile}.json")
    elif args.cup_profile != "default":
        CALIB_PATH = os.path.join(_THIS_DIR, f"calibration_{args.cup_profile}.json")

    # Sync CALIB_PATH to storage module
    cs.CALIB_PATH = CALIB_PATH

    calib_data = {}
    if args.calibrate > 0:
        if args.calibrate in (1, 3, 4, 5) and args.true_height is None:
            print(f"[ERROR] Calibration mode {args.calibrate} requires --true-height")
            sys.exit(1)
        if args.calibrate in (2, 6, 7) and (args.true_height is None or args.true_height_2 is None):
            print(f"[ERROR] Calibration mode {args.calibrate} requires --true-height AND --true-height-2")
            print("Example: --calibrate 7 --true-height 7.6 --true-height-2 11.4")
            sys.exit(1)
    else:
        cs.CALIB_PATH = CALIB_PATH
        calib_data = cs.load_calibration()
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
