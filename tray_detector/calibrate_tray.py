"""
calibrate_tray.py — Script Kalibrasi Tray Detector

Menghitung P_real_cm dengan memanggil pipeline deteksi yang SAMA PERSIS
dengan runtime (estimate_D_tray_method_B), sehingga hasil kalibrasi
100% konsisten dengan pipeline.

Penggunaan:
  # Kalibrasi via live camera
  python -m tray_detector.calibrate_tray --camera 0 --distance 18.3

  # Kalibrasi via gambar
  python -m tray_detector.calibrate_tray --image foto_tray.jpg --distance 18.3
"""

import argparse
import math
import os
import sys
import time
from datetime import datetime

import cv2
import numpy as np
import yaml

# Pastikan root project di sys.path
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from tray_detector.config import (
    load_calibration,
    THETA_TILT_DEG,
    CANNY_LOW, CANNY_HIGH,
    HOUGH_THRESHOLD, HOUGH_MIN_LINE_LENGTH, HOUGH_MAX_LINE_GAP,
    HORIZONTAL_ANGLE_TOLERANCE_DEG, MIN_LINES_PER_ZONE,
    D_MIN_CM, D_MAX_CM,
)
from tray_detector.method_b import estimate_D_tray_method_B

# Default output path
DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "tray_calibration.yaml")

# P_real_cm referensi untuk kalibrasi (nilainya tidak masalah,
# akan di-scale berdasarkan rasio D_known / D_trial)
_P_TRIAL = 1.0


def _run_method_b_trial(frame, f_pixel, theta_tilt_rad):
    """
    Jalankan method_b dengan P_real_cm=1.0 (trial) pada frame tanpa gelas.
    Menghasilkan D_trial yang kemudian digunakan untuk menghitung P_real_cm.
    """
    h, w = frame.shape[:2]
    tray_mask = np.ones((h, w), dtype=np.uint8) * 255

    result = estimate_D_tray_method_B(
        frame=frame,
        tray_mask=tray_mask,
        glass_bbox=None,
        f_pixel=f_pixel,
        P_real_cm=_P_TRIAL,
        theta_tilt_rad=theta_tilt_rad,
        canny_low=CANNY_LOW,
        canny_high=CANNY_HIGH,
        hough_threshold=HOUGH_THRESHOLD,
        hough_min_line_length=HOUGH_MIN_LINE_LENGTH,
        hough_max_line_gap=HOUGH_MAX_LINE_GAP,
        angle_tol_deg=HORIZONTAL_ANGLE_TOLERANCE_DEG,
        min_lines=MIN_LINES_PER_ZONE,
        D_min=0.1,
        D_max=10000.0
    )

    return result


def save_calibration(output_path, D_known_cm, P_real_cm, ref_slats,
                     median_pitch_px, theta_tilt_deg, camera_index=None):
    """Simpan hasil kalibrasi ke YAML (semua nilai native Python)."""
    data = {
        "calibrated_at": datetime.now().astimezone().isoformat(),
        "D_known_cm": float(round(D_known_cm, 2)),
        "P_real_cm": float(round(float(P_real_cm), 6)),
        "ref_slats": int(ref_slats),
        "median_pitch_px": float(round(float(median_pitch_px), 2)),
        "theta_tilt_deg": float(round(theta_tilt_deg, 2)),
        "camera_index": int(camera_index) if camera_index is not None else None,
        "notes": "Auto-generated oleh calibrate_tray.py",
    }

    with open(output_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False)

    return data


def calibrate_from_frame(frame, D_known_cm, f_pixel, theta_tilt_deg):
    """
    Kalibrasi dari satu frame.

    Returns:
        (P_real_cm, ref_slats, pitch_px) atau (None, None, None) jika gagal
    """
    theta_rad = math.radians(theta_tilt_deg)

    result = _run_method_b_trial(frame, f_pixel, theta_rad)

    D_trial = result.get("D_tray_cm")
    if D_trial is None or D_trial <= 0:
        return None, None, None

    # P_real_cm = D_known / D_trial * P_trial
    P_real_cm = (D_known_cm / D_trial) * _P_TRIAL

    total_slats = result.get("num_slats", 0)
    pitch_px = result.get("pitch_px")

    return P_real_cm, total_slats, pitch_px


def run_camera_calibration(camera_index, D_known_cm, output_path, f_pixel,
                           theta_tilt_deg):
    """Mode kalibrasi via kamera live."""
    from tray_detector.camera_utils import init_camera

    cap = init_camera(camera_index=camera_index, width=640, height=480)
    if cap is None:
        return False

    print(f"\n{'='*60}")
    print(f"  KALIBRASI TRAY DETECTOR")
    print(f"  Jarak diketahui: {D_known_cm} cm")
    print(f"  Tekan 'c' untuk capture & kalibrasi")
    print(f"  Tekan 'q' untuk batal")
    print(f"{'='*60}\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Gagal membaca frame")
            break

        if frame.shape[1] > 640:
            frame = cv2.resize(frame, (640, 480))

        # Preview: jalankan trial untuk tampilkan info
        theta_rad = math.radians(theta_tilt_deg)
        result = _run_method_b_trial(frame, f_pixel, theta_rad)
        D_trial = result.get("D_tray_cm")
        P_preview = None
        if D_trial and D_trial > 0:
            P_preview = (D_known_cm / D_trial) * _P_TRIAL

        # Gambar overlay preview
        vis = frame.copy()
        h, w = vis.shape[:2]

        # Gambar clustered lines
        clustered = result.get("debug_clustered", [])
        for i, line in enumerate(clustered):
            lx1, ly1, lx2, ly2 = line
            cv2.line(vis, (int(lx1), int(ly1)), (int(lx2), int(ly2)),
                     (0, 255, 0), 2)
            cv2.putText(vis, f"#{i+1}", (int(lx1) - 25, int(ly1) + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)

        num_slats = result.get("num_slats", 0)
        pitch = result.get("pitch_px")
        info = [
            f"Sekat: {num_slats}",
            f"Pitch: {pitch:.1f}px" if pitch else "Pitch: N/A",
            f"D_trial: {D_trial:.1f}" if D_trial else "D_trial: N/A",
            f"P_real: {P_preview:.4f}" if P_preview else "P_real: N/A",
        ]
        for i, txt in enumerate(info):
            cv2.putText(vis, txt, (10, 25 + i * 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        cv2.putText(vis, "Tekan 'c' KALIBRASI | 'q' BATAL",
                    (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (150, 255, 150), 1)
        cv2.imshow("Kalibrasi Tray Detector", vis)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print("Kalibrasi dibatalkan.")
            cap.release()
            cv2.destroyAllWindows()
            return False
        elif key == ord('c'):
            if P_preview is None or num_slats < 3:
                print("❌ Tidak cukup sekat terdeteksi! Pastikan tray terlihat jelas.")
                continue

            # Capture beberapa frame untuk rata-rata
            print("\n🔄 Mengambil 10 sample untuk rata-rata...")
            samples_p = []
            samples_slats = []
            samples_pitch = []
            for _ in range(10):
                ret2, frame2 = cap.read()
                if not ret2:
                    break
                if frame2.shape[1] > 640:
                    frame2 = cv2.resize(frame2, (640, 480))

                p, s, pitch = calibrate_from_frame(
                    frame2, D_known_cm, f_pixel, theta_tilt_deg)
                if p is not None:
                    samples_p.append(p)
                    samples_slats.append(s)
                    if pitch:
                        samples_pitch.append(pitch)
                time.sleep(0.1)

            cap.release()
            cv2.destroyAllWindows()

            if len(samples_p) < 3:
                print("❌ Gagal mengambil cukup sample. Coba lagi.")
                return False

            final_P = float(np.median(samples_p))
            final_slats = int(np.median(samples_slats))
            final_pitch = float(np.median(samples_pitch)) if samples_pitch else 0

            data = save_calibration(
                output_path, D_known_cm, final_P, final_slats,
                final_pitch, theta_tilt_deg, camera_index=camera_index,
            )

            print(f"\n{'='*60}")
            print(f"  ✅ KALIBRASI BERHASIL!")
            print(f"{'='*60}")
            print(f"  P_real_cm   : {data['P_real_cm']}")
            print(f"  REF_SLATS   : {data['ref_slats']}")
            print(f"  Median pitch: {data['median_pitch_px']} px")
            print(f"  Samples     : {len(samples_p)} frame")
            print(f"  Disimpan ke : {output_path}")
            print(f"{'='*60}")

            # ── Verifikasi: langsung cek dengan P_real yang baru ──────────
            print(f"\n🔍 VERIFIKASI — mengecek akurasi kalibrasi...")
            cap2 = init_camera(camera_index=camera_index, width=640, height=480)
            if cap2 is not None:
                time.sleep(0.5)
                theta_rad = math.radians(theta_tilt_deg)
                verify_results = []
                for _ in range(10):
                    ret3, frame3 = cap2.read()
                    if not ret3:
                        break
                    if frame3.shape[1] > 640:
                        frame3 = cv2.resize(frame3, (640, 480))
                    h3, w3 = frame3.shape[:2]
                    mask3 = np.ones((h3, w3), dtype=np.uint8) * 255
                    r3 = estimate_D_tray_method_B(
                        frame=frame3, tray_mask=mask3, glass_bbox=None,
                        f_pixel=f_pixel, P_real_cm=final_P,
                        theta_tilt_rad=theta_rad,
                        canny_low=CANNY_LOW, canny_high=CANNY_HIGH,
                        hough_threshold=HOUGH_THRESHOLD,
                        hough_min_line_length=HOUGH_MIN_LINE_LENGTH,
                        hough_max_line_gap=HOUGH_MAX_LINE_GAP,
                        angle_tol_deg=HORIZONTAL_ANGLE_TOLERANCE_DEG,
                        min_lines=MIN_LINES_PER_ZONE,
                        D_min=D_MIN_CM, D_max=D_MAX_CM
                    )
                    d3 = r3.get("D_tray_cm")
                    if d3:
                        verify_results.append(d3)
                    time.sleep(0.1)
                cap2.release()

                if verify_results:
                    v_mean = float(np.mean(verify_results))
                    v_std = float(np.std(verify_results))
                    v_err = abs(v_mean - D_known_cm) / D_known_cm * 100
                    print(f"  Jarak diketahui : {D_known_cm} cm")
                    print(f"  Hasil verifikasi: {v_mean:.1f} ± {v_std:.1f} cm")
                    print(f"  Error           : {v_err:.1f}%")
                    if v_err < 2.0:
                        print(f"  ✅ Kalibrasi SANGAT BAIK (error < 2%)")
                    elif v_err < 5.0:
                        print(f"  ⚠️ Kalibrasi CUKUP BAIK (error < 5%)")
                    else:
                        print(f"  ❌ Kalibrasi KURANG AKURAT — periksa jarak ukur!")
                else:
                    print("  ⚠️ Gagal memverifikasi (tidak ada hasil)")
            print(f"{'='*60}\n")
            return True

    cap.release()
    cv2.destroyAllWindows()
    return False


def run_image_calibration(image_path, D_known_cm, output_path, f_pixel,
                          theta_tilt_deg):
    """Mode kalibrasi via gambar tunggal."""
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Tidak bisa membaca gambar: {image_path}")
        return False

    P_real, slats, pitch = calibrate_from_frame(
        img, D_known_cm, f_pixel, theta_tilt_deg)

    if P_real is None or slats < 3:
        print(f"❌ Tidak cukup sekat terdeteksi.")
        return False

    data = save_calibration(
        output_path, D_known_cm, P_real, slats,
        pitch if pitch else 0, theta_tilt_deg, camera_index=None,
    )

    print(f"\n{'='*60}")
    print(f"  ✅ KALIBRASI BERHASIL!")
    print(f"{'='*60}")
    print(f"  P_real_cm   : {data['P_real_cm']}")
    print(f"  REF_SLATS   : {data['ref_slats']}")
    print(f"  Median pitch: {data['median_pitch_px']} px")
    print(f"  Disimpan ke : {output_path}")
    print(f"{'='*60}\n")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Kalibrasi Tray Detector — Hitung P_real_cm dari jarak diketahui",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh penggunaan:
  # Kalibrasi via live camera
  python -m tray_detector.calibrate_tray --camera 0 --distance 18.3

  # Kalibrasi via gambar
  python -m tray_detector.calibrate_tray --image foto_tray.jpg --distance 18.3
        """,
    )

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--camera", nargs="?", const=0, type=int,
                        help="Index kamera untuk kalibrasi live (default: 0)")
    source.add_argument("--image", type=str,
                        help="Path ke gambar tray untuk kalibrasi")

    parser.add_argument("--distance", type=float, default=None,
                        help="Jarak kamera ke tray dalam CM. Jika tidak diisi, akan ditanyakan interaktif.")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT,
                        help=f"Path output YAML (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--params", type=str, default=None,
                        help="Path ke calibration_params.yml kamera")

    args = parser.parse_args()

    # Interactively ask for distance if not provided
    if args.distance is None:
        print("\n" + "-"*60)
        print("  Masukkan jarak aktual kamera ke permukaan atas tray.")
        print("  Gunakan penggaris atau meteran (dalam cm).")
        print("-" * 60)
        while True:
            val = input("Masukkan jarak (cm) [misal: 21.3]: ").strip()
            try:
                distance = float(val)
                if distance > 0:
                    break
                print("Error: Jarak harus lebih besar dari 0.")
            except ValueError:
                print("Error: Input tidak valid. Masukkan angka.")
    else:
        distance = args.distance

    if distance <= 0:
        print("Error: --distance harus bernilai positif (cm)")
        sys.exit(1)

    # Load kalibrasi kamera untuk mendapatkan f_pixel
    print("\nMemuat kalibrasi kamera...")
    calib = load_calibration(args.params)
    f_pixel = calib["f_pixel"]
    print(f"  f_pixel = {f_pixel:.2f}")
    print(f"  theta   = {THETA_TILT_DEG}°\n")

    if args.camera is not None:
        success = run_camera_calibration(
            args.camera, distance, args.output, f_pixel, THETA_TILT_DEG)
    else:
        success = run_image_calibration(
            args.image, distance, args.output, f_pixel, THETA_TILT_DEG)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
