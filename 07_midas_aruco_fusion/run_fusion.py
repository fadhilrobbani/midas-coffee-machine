"""
run_fusion.py — ArUco + MiDaS + YOLO Cup Height Estimator
=============================================================
Eksperimen penggabungan 3 sistem tanpa kalibrasi kurva (polynomial).
ArUco Marker memberikan Z_tray absolut sebagai jangkar _real-time_,
lalu MiDaS + YOLO mengukur posisi bibir gelas secara geometri.

Fitur:
  - Estimasi Asynchronous (ArUco 30 FPS, MiDaS 5 FPS)
  - Video Recording (Tekan 'R')
  - Screenshot (Tekan 'S')
  - Session Report lengkap .MD/.JSON di folder `results/` saat keluar

Cara Pengunaan:
  python run_fusion.py                      → kamera default (index 0)
  python run_fusion.py --camera 2           → kamera index 2
  python run_fusion.py --headless           → tanpa UI (mode Kakip)
  python run_fusion.py --marker-size 1.5    → ukuran sisi ArUco fisik (cm)
  python run_fusion.py --alpha 1.0          → fine-tuning skala geometri
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
RESULT_DIR = os.path.join(_THIS_DIR, "results")
REPORT_DIR = os.path.join(RESULT_DIR, "report")
VIDEO_DIR  = os.path.join(RESULT_DIR, "video")
SCREENSHOT_DIR = os.path.join(RESULT_DIR, "live_cam")

for d in [REPORT_DIR, VIDEO_DIR, SCREENSHOT_DIR]:
    os.makedirs(d, exist_ok=True)


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  PIPELINE UTAMA                                                         ║
# ╚═════════════════════════════════════════════════════════════════════════╝

def run_pipeline(camera_idx: int, headless: bool, alpha: float, marker_size: float):
    print("=" * 55)
    print("  🚀  ArUco + MiDaS + YOLO  |  Cup Height Estimator")
    print("=" * 55)

    # ── 1. Inisialisasi Detektor ─────────────────────────────────────
    print("[INIT] Memuat ArucoDetector...")
    aruco = ArucoDetector(marker_size_cm=marker_size)
    print("[INIT] Memuat YoloDetector...")
    yolo  = YoloDetector()
    print("[INIT] Memuat MidasDepthEstimator (butuh waktu)...")
    midas = MidasDepthEstimator()
    print("[INIT] ✅ Semua detektor siap.\n")

    # ── 2. Setup Kamera ────────────────────────────────────────────────────
    cap = cv2.VideoCapture(camera_idx)
    if not cap.isOpened():
        print(f"[ERROR] Tidak bisa membuka kamera index {camera_idx}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    for _ in range(20):
        ret, _ = cap.read()
        if ret: break
        time.sleep(0.05)

    print(f"[CAMERA] Aktif (index={camera_idx}) | Headless={headless}")
    if not headless:
        print("         Tekan 'S' untuk Screenshot.")
        print("         Tekan 'R' untuk Record Video.")
        print("         Tekan 'Q' / ESC untuk Keluar & Buat Report.\n")

    # ── 3. State Asynchronous Pipeline ────────────────────────────────────
    MIDAS_FPS_LIMIT = 5.0
    midas_interval  = 1.0 / MIDAS_FPS_LIMIT
    last_midas_t    = 0.0

    z_tray_live:    float       = 0.0
    aruco_roi:      tuple | None = None
    cup_bbox:       tuple | None = None
    cup_height_ema: float | None = None
    last_depth_norm = None
    EMA_ALPHA = 0.3

    # ── 4. State Reporting & Recording ────────────────────────────────────
    is_recording = False
    video_writer = None
    screenshot_paths = []
    
    stats_total_frames = 0
    stats_midas_runs = 0
    
    history_z_tray = []
    history_cup_h = []
    history_frames = []

    # ── 5. Loop Utama ─────────────────────────────────────────────────────
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[WARN] Gagal membaca frame. Mencoba ulang...")
                time.sleep(0.1)
                continue

            now = time.time()
            stats_total_frames += 1
            h_frame, w_frame = frame.shape[:2]

            # ──────────────────────────────────────────────────────────────────
            # TREK CEPAT (ArUco)  — berjalan setiap frame (≈30 FPS)
            # ──────────────────────────────────────────────────────────────────
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

            # ──────────────────────────────────────────────────────────────────
            # TREK BERAT (YOLO + MiDaS) — terbatas <= 5 FPS
            # ──────────────────────────────────────────────────────────────────
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
                        z_rim = calculate_z_rim_alpha(m_rim, m_tray, z_tray_live, alpha)
                        height_raw = z_tray_live - z_rim

                        if height_raw > 0:
                            if cup_height_ema is None:
                                cup_height_ema = height_raw
                            else:
                                cup_height_ema = (EMA_ALPHA * height_raw) + ((1.0 - EMA_ALPHA) * cup_height_ema)
                            
                            # Record to history array
                            history_z_tray.append(z_tray_live)
                            history_cup_h.append(cup_height_ema)
                            history_frames.append(stats_total_frames)

                else:
                    cup_bbox = None
                    cup_height_ema = None
                    # Jika tidak ada gelas, nilai z_tray tetap dicatat untuk referensi stability tray
                    history_z_tray.append(z_tray_live)
                    history_cup_h.append(0.0)
                    history_frames.append(stats_total_frames)

                last_midas_t = now

            # ──────────────────────────────────────────────────────────────────
            # OUTPUT & RECORDING
            # ──────────────────────────────────────────────────────────────────
            disp = frame.copy()
            
            # Update Disp layer
            if aruco_results:
                disp = aruco.annotate_frame(disp, aruco_results)
            if aruco_roi:
                cv2.rectangle(disp, aruco_roi[:2], aruco_roi[2:], (255, 140, 0), 1)
            if cup_bbox:
                x1c, y1c, x2c, y2c = cup_bbox
                cv2.rectangle(disp, (x1c, y1c), (x2c, y2c), (0, 255, 80), 2)

            # Panel UI
            cv2.rectangle(disp, (8, 8), (420, 90), (25, 25, 25), -1)
            cv2.rectangle(disp, (8, 8), (420, 90), (90, 90, 90), 1)

            # ── Picture-in-Picture: MiDaS Depth Map ───────────────────────────
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

            # REC Indicator
            if is_recording:
                if int(time.time() * 2) % 2 == 0:
                    cv2.circle(disp, (w_frame - 65, 25), 6, (0, 0, 255), -1)
                    cv2.putText(disp, "REC", (w_frame - 50, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                if video_writer is not None:
                    video_writer.write(disp)

            # Status bar bawah
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
        print("\n[DONE] Pipeline ditutup. Mempersiapkan Laporan Akhir (Report)...")
        
        _generate_session_report(
            alpha=alpha,
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

def _generate_session_report(alpha, marker_size_cm, focal_len, total_frames, midas_runs, 
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
    
    # Bikin Chart
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
    
    # Kopi Screenshots
    ss_target = []
    if screenshots:
        ss_sub = os.path.join(report_folder, "screenshots")
        os.makedirs(ss_sub, exist_ok=True)
        for s in screenshots:
            basename = os.path.basename(s)
            dst = os.path.join(ss_sub, basename)
            shutil.copy2(s, dst)
            ss_target.append(f"screenshots/{basename}")
            
    # Tulis MD
    md_path = os.path.join(report_folder, "report.md")
    with open(md_path, "w") as f:
        f.write("# ArUco + MiDaS Fusion Session Report\n\n")
        f.write(f"**Date/Time:** {ts_folder.replace('_', ' ')}\n\n")
        
        f.write("## 1. Parameters\n")
        f.write(f"- Marker Size: {marker_size_cm} cm\n")
        f.write(f"- Formula Alpha: {alpha}\n")
        f.write(f"- Camera Focal Length: {focal_len:.1f} px\n\n")
        
        f.write("## 2. Global Results\n")
        f.write(f"- **Avg Cup Height**: {avg_h:.2f} cm\n")
        f.write(f"- **Min / Max Cup Height**: {min_h:.2f} cm / {max_h:.2f} cm\n")
        f.write(f"- **Standard Deviation (Precision jitter)**: ± {std_h:.2f} cm\n")
        f.write(f"- **Avg Z_tray Anchor**: {avg_z:.2f} cm\n")
        f.write(f"- Total Frames Streamed: {total_frames}\n")
        f.write(f"- Total MiDaS Inferences: {midas_runs}\n\n")
        
        f.write("## 3. Session Chart\n")
        f.write("![Session Chart](session_chart.png)\n\n")
        
        if ss_target:
            f.write("## 4. Screenshots\n")
            for ss in ss_target:
                f.write(f"- ![{ss}]({ss})\n")

    # Generate JSON
    json_path = os.path.join(report_folder, "session_data.json")
    json_data = {
        "session_timestamp": ts_folder,
        "parameters": {
            "marker_size_cm": marker_size_cm,
            "alpha": alpha,
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
    ap.add_argument("--camera",      type=int,   default=0,   help="Index kamera (default: 0)")
    ap.add_argument("--headless",    action="store_true",      help="Tanpa UI — mode terminal")
    ap.add_argument("--alpha",       type=float, default=1.0,  help="Skala geometri z_rim (default: 1.0)")
    ap.add_argument("--marker-size", type=float, default=5.0,  help="Ukuran Fisik ArUco di meja (cm)")

    args = ap.parse_args()
    run_pipeline(args.camera, args.headless, args.alpha, args.marker_size)
