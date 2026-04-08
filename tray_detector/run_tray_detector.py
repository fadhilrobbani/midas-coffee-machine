"""
run_tray_detector.py — CLI Entry Point

3 mode operasi:
  --image PATH       → proses satu gambar, simpan visualisasi + print JSON
  --input_dir PATH   → batch seluruh folder gambar
  --camera [INDEX]   → live webcam dengan overlay real-time (tekan 'q' keluar)

Contoh:
  python -m tray_detector.run_tray_detector --image test.jpg
  python -m tray_detector.run_tray_detector --camera 0
  python -m tray_detector.run_tray_detector --image test.jpg --no-yolo
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import cv2

# Pastikan root project di sys.path
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from tray_detector.pipeline import TrayDistancePipeline


def _print_result(result, source=""):
    """Print hasil deteksi dalam format JSON yang rapi."""
    # Buat copy tanpa _detail (terlalu verbose)
    output = {k: v for k, v in result.items() if k != "_detail"}
    prefix = f"[{source}] " if source else ""
    print(f"\n{prefix}{'='*50}")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"{'='*50}\n")


def process_single_image(pipeline, image_path, output_dir):
    """Proses satu gambar dan simpan hasil."""
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Tidak bisa membaca gambar: {image_path}")
        return

    print(f"Memproses: {image_path}")
    result = pipeline.process_frame(img)
    _print_result(result, source=os.path.basename(image_path))

    # Simpan visualisasi
    annotated = pipeline.annotate_frame(img, result)
    basename = os.path.splitext(os.path.basename(image_path))[0]
    out_path = os.path.join(output_dir, f"dtray_{basename}.jpg")
    cv2.imwrite(out_path, annotated)
    print(f"Visualisasi disimpan: {out_path}")


def process_directory(pipeline, input_dir, output_dir):
    """Batch proses semua gambar dalam folder."""
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
    images = sorted([
        f for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in exts
    ])

    if not images:
        print(f"Tidak ada gambar ditemukan di: {input_dir}")
        return

    print(f"Memproses {len(images)} gambar dari: {input_dir}")
    for img_name in images:
        img_path = os.path.join(input_dir, img_name)
        process_single_image(pipeline, img_path, output_dir)


def run_live_camera(pipeline, camera_index=0, lock_focus=False, focus_value=0):
    """Live camera mode dengan overlay real-time."""

    SCREENSHOT_DIR= "tray_detector/results/live_cam"
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    from tray_detector.camera_utils import init_camera
    
    cap = init_camera(
        camera_index=camera_index,
        lock_focus=lock_focus,
        focus_value=focus_value,
        width=640, height=480,
    )
    if cap is None:
        return

    print(f"Live camera dimulai (index={camera_index})")
    print("Tekan 'q' untuk keluar | 's' untuk screenshot")
    if lock_focus:
        print(f"🔒 Focus locked at value={focus_value}")

    fps_counter = 0
    fps_time = time.time()
    fps_display = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Gagal membaca frame dari kamera")
            break

        # Pastikan frame adalah 640x480 (jika driver kamera mengabaikan cap.set)
        if frame.shape[1] > 640:
            frame = cv2.resize(frame, (640, 480))

        # Proses frame
        t_start = time.time()
        result = pipeline.process_frame(frame)
        t_process = time.time() - t_start

        # Annotasi
        annotated = pipeline.annotate_frame(frame, result)

        # FPS counter
        fps_counter += 1
        elapsed = time.time() - fps_time
        if elapsed >= 1.0:
            fps_display = fps_counter / elapsed
            fps_counter = 0
            fps_time = time.time()

        # Overlay FPS + processing time
        h, w = annotated.shape[:2]
        fps_txt = f"FPS: {fps_display:.1f} | Process: {t_process*1000:.0f}ms"
        cv2.putText(annotated, fps_txt, (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 150), 1)

        # Display
        cv2.imshow("Tray Detector - Live", annotated)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("Live camera dihentikan.")
            break
        elif key == ord('s'):
            # Screenshot
            timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
            ss_path = f"{SCREENSHOT_DIR}/tray_detector_{timestamp}.jpg"
            cv2.imwrite(ss_path, annotated)
            _print_result(result, source="screenshot")
            print(f"Screenshot disimpan: {ss_path}")

    cap.release()
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline Deteksi Jarak Kamera ke Tray (D_tray_cm)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  # Proses satu gambar
  python -m tray_detector.run_tray_detector --image foto_tray.jpg

  # Live camera (default index 0)
  python -m tray_detector.run_tray_detector --camera

  # Live camera dengan lock focus (untuk tray tanpa gelas)
  python -m tray_detector.run_tray_detector --camera 0 --lock-focus
  python -m tray_detector.run_tray_detector --camera 0 --lock-focus --focus-value 30

  # Tanpa YOLO + lock focus (best for tray-only)
  python -m tray_detector.run_tray_detector --camera 0 --no-yolo --lock-focus
        """,
    )

    # Mode operasi (mutually exclusive)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--image", type=str,
                      help="Path ke satu file gambar")
    mode.add_argument("--input_dir", type=str,
                      help="Direktori berisi gambar untuk batch processing")
    mode.add_argument("--camera", nargs="?", const=0, type=int,
                      help="Index kamera untuk live mode (default: 0)")

    # Opsi umum
    parser.add_argument("--output_dir", type=str, default=None,
                        help="Direktori output untuk visualisasi (default: tray_detector/results)")
    parser.add_argument("--weights", type=str, default=None,
                        help="Path ke YOLO weights (.pt)")
    parser.add_argument("--params", type=str, default=None,
                        help="Path ke calibration parameters YAML")
    parser.add_argument("--no-yolo", action="store_true",
                        help="Nonaktifkan YOLO — gunakan Hough Lines langsung di seluruh frame")
    parser.add_argument("--method", type=str, default="auto",
                        choices=["auto", "A", "B", "C"],
                        help="Pilih metode deteksi: auto (hierarki), A (apparent width), "
                             "B (horizontal slat pitch), C (homografi PnP). Default: auto")
    parser.add_argument("--lock-focus", action="store_true",
                        help="Lock camera focus (matikan auto-focus). "
                             "Wajib untuk akurasi jarak jauh tanpa YOLO.")
    parser.add_argument("--focus-value", type=int, default=0,
                        help="Nilai fokus tetap saat --lock-focus aktif. "
                             "0=infinity (default, terbaik untuk overhead tray)")

    args = parser.parse_args()

    # Default output dir
    output_dir = args.output_dir or os.path.join(_ROOT_DIR, "tray_detector", "results")
    os.makedirs(output_dir, exist_ok=True)

    # Inisialisasi pipeline
    print("Menginisialisasi pipeline...")
    pipeline = TrayDistancePipeline(
        weights_path=args.weights,
        params_path=args.params,
        no_yolo=args.no_yolo,
        method=args.method,
    )
    print("Pipeline siap.\n")

    # Jalankan sesuai mode
    if args.image:
        process_single_image(pipeline, args.image, output_dir)
    elif args.input_dir:
        process_directory(pipeline, args.input_dir, output_dir)
    elif args.camera is not None:
        run_live_camera(pipeline, camera_index=args.camera,
                        lock_focus=args.lock_focus,
                        focus_value=args.focus_value)


if __name__ == "__main__":
    main()
