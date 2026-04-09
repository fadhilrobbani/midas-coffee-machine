"""
config.py — Konstanta kalibrasi kamera dan dimensi fisik tray.

Nilai default diambil dari calibration_params.yml (kamera kiri).
Dapat di-override melalui YAML file atau argumen langsung.
"""

import os
import math
import numpy as np
import yaml


# ── Paths ────────────────────────────────────────────────────────────────
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CALIB_PATH = os.path.join(ROOT_DIR, "calibration_params.yml")
DEFAULT_WEIGHTS_PATH = os.path.join(ROOT_DIR, "weights", "cup_detection_v3_12_s_best.pt")
DEFAULT_TRAY_CALIB_PATH = os.path.join(os.path.dirname(__file__), "tray_calibration.yaml")

# ── Dimensi fisik tray Jura (cm) — diukur dari unit fisik ────────────────
P_REAL_CM = 0.69         # jarak aktual kalibrasi (agar test_tray terbaca 25.0cm)
W_TRAY_CM = 12.5         # lebar tray (cm) — arah pendek
L_TRAY_CM = 22.0         # panjang tray (cm) — arah panjang
THETA_TILT_DEG = 20.0    # sudut condong kamera dari vertikal (derajat)

# ── Validasi range D_tray ────────────────────────────────────────────────
D_MIN_CM = 2.0
D_MAX_CM = 100.0

# ── Hough Lines tuning ──────────────────────────────────────────────────
CANNY_LOW = 20
CANNY_HIGH = 80
HOUGH_THRESHOLD = 25
HOUGH_MIN_LINE_LENGTH = 25
HOUGH_MAX_LINE_GAP = 15
HORIZONTAL_ANGLE_TOLERANCE_DEG = 10.0   # ±10° dari horizontal
MIN_LINES_PER_ZONE = 3


def load_calibration(params_path=None):
    """
    Memuat parameter kalibrasi kamera dari YAML file.

    Returns:
        dict dengan keys:
            'camera_matrix' (np.ndarray 3x3),
            'dist_coeffs' (np.ndarray 1x5),
            'f_pixel' (float — focal length rata-rata fx, fy)
    """
    path = params_path or DEFAULT_CALIB_PATH
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Calibration file not found: {path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    # Gunakan kamera kiri sebagai default (lebih stabil)
    K = np.array(data["camera_matrix_left"], dtype=np.float64)
    D = np.array(data["dist_coeff_left"], dtype=np.float64).flatten()
    f_pixel = (K[0, 0] + K[1, 1]) / 2.0  # rata-rata fx dan fy

    return {
        "camera_matrix": K,
        "dist_coeffs": D,
        "f_pixel": f_pixel,
    }


def load_tray_calibration(tray_calib_path=None):
    """
    Memuat kalibrasi tray dari YAML jika file ada.

    Returns:
        dict atau None jika file tidak ditemukan.
    """
    path = tray_calib_path or DEFAULT_TRAY_CALIB_PATH
    if not os.path.isfile(path):
        return None

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    return data


def get_default_config(params_path=None, tray_calib_path=None):
    """
    Mengembalikan dict konfigurasi lengkap yang dibutuhkan oleh pipeline.
    Jika tray_calibration.yaml ada, nilai-nilainya akan di-override.
    """
    calib = load_calibration(params_path)

    # ── Load kalibrasi tray (override jika ada) ──────────────────────────
    tray_calib = load_tray_calibration(tray_calib_path)

    p_real = P_REAL_CM
    theta_deg = THETA_TILT_DEG
    ref_slats = 27  # default fallback
    d_known = None

    if tray_calib:
        p_real = tray_calib.get("P_real_cm", P_REAL_CM)
        theta_deg = tray_calib.get("theta_tilt_deg", THETA_TILT_DEG)
        ref_slats = tray_calib.get("ref_slats", 27)
        d_known = tray_calib.get("D_known_cm", None)
        print(f"[CONFIG] ✅ Kalibrasi tray dimuat: P_real={p_real:.4f}, "
              f"ref_slats={ref_slats}, θ={theta_deg}°, D_known={d_known}cm")
    else:
        print(f"[CONFIG] ⚠️  File kalibrasi tray tidak ditemukan.")
        print(f"[CONFIG]    Menggunakan default: P_real={p_real}, ref_slats={ref_slats}")
        print(f"[CONFIG]    Jalankan: python -m tray_detector.calibrate_tray --help")

    theta_rad = math.radians(theta_deg)

    return {
        # Kalibrasi kamera
        "camera_matrix": calib["camera_matrix"],
        "dist_coeffs": calib["dist_coeffs"],
        "f_pixel": calib["f_pixel"],

        # Dimensi fisik (dari kalibrasi tray atau default)
        "P_real_cm": p_real,
        "W_tray_cm": W_TRAY_CM,
        "L_tray_cm": L_TRAY_CM,
        "theta_tilt_deg": theta_deg,
        "theta_tilt_rad": theta_rad,
        "ref_slats": ref_slats,
        "D_known_cm": d_known,

        # Validasi
        "D_min_cm": D_MIN_CM,
        "D_max_cm": D_MAX_CM,

        # Hough Lines
        "canny_low": CANNY_LOW,
        "canny_high": CANNY_HIGH,
        "hough_threshold": HOUGH_THRESHOLD,
        "hough_min_line_length": HOUGH_MIN_LINE_LENGTH,
        "hough_max_line_gap": HOUGH_MAX_LINE_GAP,
        "horizontal_angle_tol_deg": HORIZONTAL_ANGLE_TOLERANCE_DEG,
        "min_lines_per_zone": MIN_LINES_PER_ZONE,

        # Paths
        "weights_path": DEFAULT_WEIGHTS_PATH,
    }
