"""
run_aruco.py — CLI Entry Point untuk ArUco Marker Detection Experiment

3 mode operasi:
  --image PATH          → proses satu gambar
  --camera [INDEX]      → live webcam dengan overlay real-time
  --generate-marker     → generate gambar marker untuk di-print

Contoh:
  python run_aruco.py --generate-marker
  python run_aruco.py --image foto_marker.jpg --marker-size 5.0
  python run_aruco.py --camera 0 --marker-size 5.0 --lock-focus
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import cv2

# Pastikan path bisa import lokal
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from aruco_detector import ArucoDetector


def _print_result(results, source=""):
    """Print hasil deteksi dalam format JSON."""
    prefix = f"[{source}] " if source else ""
    print(f"\n{prefix}{'='*50}")
    for r in results:
        output = {
            "id": r["id"],
            "distance_cm": r["distance_cm"],
            "center": [round(r["center"][0], 1), round(r["center"][1], 1)],
            "euler_deg": r["euler_deg"],
            "reprojection_error": r["reprojection_error"],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    if not results:
        print("  No ArUco marker detected")
    print(f"{'='*50}\n")


# ── Mode: Single Image ─────────────────────────────────────────────────
def process_single_image(detector, image_path, output_dir):
    """Proses satu gambar dan simpan hasil."""
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Tidak bisa membaca gambar: {image_path}")
        return

    print(f"Memproses: {image_path}")
    results = detector.detect(img)
    _print_result(results, source=os.path.basename(image_path))

    annotated = detector.annotate_frame(img, results)
    basename = os.path.splitext(os.path.basename(image_path))[0]
    out_path = os.path.join(output_dir, f"aruco_{basename}.jpg")
    cv2.imwrite(out_path, annotated)
    print(f"Visualisasi disimpan: {out_path}")


# ── Mode: Live Camera ───────────────────────────────────────────────────
def run_live_camera(detector, camera_index=0, lock_focus=False, focus_value=0):
    """Live camera mode dengan overlay real-time."""

    SCREENSHOT_DIR = os.path.join(_SCRIPT_DIR, "results", "live_cam")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # Import camera_utils dari tray_detector jika ada, fallback ke dasar
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"Error: Tidak bisa membuka kamera index {camera_index}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAMERA] Resolusi: {actual_w}x{actual_h}")

    if lock_focus:
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        cap.set(cv2.CAP_PROP_FOCUS, focus_value)
        actual_focus = cap.get(cv2.CAP_PROP_FOCUS)
        print(f"[CAMERA] ✅ Focus LOCKED: auto-focus OFF, focus={actual_focus}")

    print(f"\nLive camera started (index={camera_index})")
    print("Press 'q' to exit | 's' screenshot")
    if lock_focus:
        print(f"🔒 Focus locked at value={focus_value}")

    fps_counter = 0
    fps_time = time.time()
    fps_display = 0.0

    # Statistics
    stats_total = 0
    stats_detected = 0
    stats_d_sum = 0.0
    stats_d_min = float('inf')
    stats_d_max = float('-inf')

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to read frame from camera")
            break

        if frame.shape[1] > 640:
            frame = cv2.resize(frame, (640, 480))

        t_start = time.time()
        results = detector.detect(frame)
        t_process = time.time() - t_start

        # Update statistics
        stats_total += 1
        if results:
            stats_detected += 1
            # Gunakan marker pertama yang terdeteksi
            d_val = results[0]["distance_cm"]
            stats_d_sum += d_val
            stats_d_min = min(stats_d_min, d_val)
            stats_d_max = max(stats_d_max, d_val)

        # Annotate
        annotated = detector.annotate_frame(frame, results)

        # FPS counter
        fps_counter += 1
        elapsed = time.time() - fps_time
        if elapsed >= 1.0:
            fps_display = fps_counter / elapsed
            fps_counter = 0
            fps_time = time.time()

        h, w = annotated.shape[:2]
        fps_txt = f"FPS: {fps_display:.1f} | Process: {t_process*1000:.0f}ms"
        cv2.putText(annotated, fps_txt, (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 150), 1)

        # Jumlah marker terdeteksi
        n_markers = len(results)
        marker_txt = f"Markers: {n_markers}"
        color = (0, 255, 0) if n_markers > 0 else (0, 0, 255)
        cv2.putText(annotated, marker_txt, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.imshow("ArUco Marker Detector - Live", annotated)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("Live camera dihentikan.")
            break
        elif key == ord('s'):
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            ss_path = os.path.join(SCREENSHOT_DIR,
                                   f"aruco_capture_{timestamp}.jpg")
            cv2.imwrite(ss_path, annotated)
            _print_result(results, source="screenshot")
            print(f"Screenshot saved: {ss_path}")

    cap.release()
    cv2.destroyAllWindows()

    # Session report
    print(f"\n{'='*50}")
    print("📐 ARUCO MARKER SESSION REPORT 📐")
    print(f"{'='*50}")
    print(f"Total frames processed  : {stats_total}")
    if stats_detected > 0:
        avg_d = stats_d_sum / stats_detected
        pct = stats_detected / max(1, stats_total) * 100
        print(f"Frames with marker      : {stats_detected} ({pct:.1f}%)")
        print(f"Average Distance        : {avg_d:.2f} cm")
        print(f"Minimum Distance        : {stats_d_min:.2f} cm")
        print(f"Maximum Distance        : {stats_d_max:.2f} cm")
        print(f"Distance Range (spread) : {stats_d_max - stats_d_min:.2f} cm")
        print("-" * 50)
        print(f"🎯 FINAL ESTIMATED DISTANCE: {avg_d:.2f} cm 🎯")
    else:
        print("Frames with marker      : 0 (No marker detected)")
    print(f"{'='*50}\n")


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="ArUco Marker Detection Experiment — Distance Estimation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  # 1. Generate marker (print ini di kertas)
  python run_aruco.py --generate-marker
  python run_aruco.py --generate-marker --marker-id 5 --dictionary DICT_5X5_50

  # 2. Test pada gambar
  python run_aruco.py --image foto_marker.jpg --marker-size 5.0

  # 3. Live camera
  python run_aruco.py --camera 0 --marker-size 5.0 --lock-focus
        """,
    )

    # Mode operasi
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--image", type=str,
                      help="Path ke satu file gambar")
    mode.add_argument("--camera", nargs="?", const=0, type=int,
                      help="Index kamera untuk live mode (default: 0)")
    mode.add_argument("--generate-marker", action="store_true",
                      help="Generate gambar ArUco marker untuk di-print")

    # ArUco options
    parser.add_argument("--marker-size", type=float, default=5.0,
                        help="Ukuran fisik sisi marker dalam cm (default: 5.0)")
    parser.add_argument("--dictionary", type=str, default="DICT_4X4_50",
                        help="ArUco dictionary (default: DICT_4X4_50)")
    parser.add_argument("--marker-id", type=int, default=0,
                        help="Marker ID untuk generate (default: 0)")
    parser.add_argument("--marker-px", type=int, default=400,
                        help="Ukuran marker dalam piksel untuk generate (default: 400)")

    # Camera options
    parser.add_argument("--lock-focus", action="store_true",
                        help="Lock camera focus (matikan auto-focus)")
    parser.add_argument("--focus-value", type=int, default=0,
                        help="Nilai fokus tetap saat --lock-focus aktif (default: 0)")

    # Calibration
    parser.add_argument("--params", type=str, default=None,
                        help="Path ke calibration_params.yml")

    # Output
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Direktori output untuk visualisasi")

    args = parser.parse_args()

    # ── Generate Marker Mode ─────────────────────────────────────────────
    if args.generate_marker:
        from generate_marker import generate_marker
        generate_marker(
            marker_id=args.marker_id,
            size_px=args.marker_px,
            dictionary_name=args.dictionary,
        )
        return

    # ── Detection Modes ──────────────────────────────────────────────────
    output_dir = args.output_dir or os.path.join(_SCRIPT_DIR, "results")
    os.makedirs(output_dir, exist_ok=True)

    print("Initializing ArUco detector...")
    detector = ArucoDetector(
        marker_size_cm=args.marker_size,
        dictionary_name=args.dictionary,
        params_path=args.params,
    )
    print("Detector siap.\n")

    if args.image:
        process_single_image(detector, args.image, output_dir)
    elif args.camera is not None:
        run_live_camera(detector, camera_index=args.camera,
                        lock_focus=args.lock_focus,
                        focus_value=args.focus_value)


if __name__ == "__main__":
    main()
