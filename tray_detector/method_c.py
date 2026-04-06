"""
method_c.py — Metode C: Homografi 4 Corner + PnP (Backup Presisi)

Estimasi D_tray menggunakan 4 titik sudut tray sebagai correspondences
2D ↔ 3D, lalu cv2.solvePnP untuk mendapatkan translation vector.

Formula:
    D_tray = |T[2]| × cos(theta_tilt)
"""

import math
import cv2
import numpy as np


def _sort_corners_clockwise(pts):
    """
    Urutkan 4 titik menjadi: kiri-atas, kanan-atas, kanan-bawah, kiri-bawah.
    """
    pts = pts.reshape(4, 2).astype(np.float32)

    # Sort berdasarkan x
    x_sorted = pts[np.argsort(pts[:, 0])]
    left_pair = x_sorted[:2]
    right_pair = x_sorted[2:]

    # Sort left pair by y (atas dulu)
    left_pair = left_pair[np.argsort(left_pair[:, 1])]
    # Sort right pair by y (atas dulu)
    right_pair = right_pair[np.argsort(right_pair[:, 1])]

    # TL, TR, BR, BL
    return np.array([left_pair[0], right_pair[0],
                     right_pair[1], left_pair[1]], dtype=np.float32)


def _compute_reprojection_error(obj_pts, img_pts, rvec, tvec, K, dist_coeffs):
    """Hitung rata-rata reprojection error (pixel)."""
    projected, _ = cv2.projectPoints(obj_pts, rvec, tvec, K, dist_coeffs)
    projected = projected.reshape(-1, 2)
    errors = np.linalg.norm(img_pts - projected, axis=1)
    return float(np.mean(errors))


def estimate_D_tray_method_C(tray_mask, K, dist_coeffs,
                              W_tray_cm, L_tray_cm, theta_tilt_rad,
                              D_min=5.0, D_max=40.0):
    """
    Estimasi D_tray menggunakan solvePnP dari 4 corner tray.

    Args:
        tray_mask: mask binary tray (H×W) dari YOLO segmentation
        K: camera matrix (3×3) — np.ndarray
        dist_coeffs: distortion coefficients — np.ndarray
        W_tray_cm: lebar fisik tray (cm)
        L_tray_cm: panjang fisik tray (cm)
        theta_tilt_rad: sudut condong kamera (radian)
        D_min, D_max: range validasi (cm)

    Returns:
        dict: D_tray_cm, confidence, status, reprojection_error, corners, notes
        atau None jika 4 corner tidak terdeteksi
    """
    if tray_mask is None or np.count_nonzero(tray_mask) < 500:
        return None

    # ── Step 3: Ekstrak contour ──────────────────────────────────────────
    mask_u8 = (tray_mask > 0.5).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Ambil contour terbesar
    cnt = max(contours, key=cv2.contourArea)
    peri = cv2.arcLength(cnt, True)

    # ── Step 3–4: approxPolyDP → validasi 4 titik ───────────────────────
    # Coba beberapa epsilon untuk mendapat tepat 4 titik
    approx = None
    for eps_factor in [0.02, 0.03, 0.04, 0.05, 0.015]:
        candidate = cv2.approxPolyDP(cnt, eps_factor * peri, True)
        if len(candidate) == 4:
            approx = candidate
            break

    if approx is None or len(approx) != 4:
        return None

    # ── Step 5: Urutkan corner clockwise ─────────────────────────────────
    img_pts = _sort_corners_clockwise(approx)

    # ── Step 6: Object points 3D ─────────────────────────────────────────
    W, L = W_tray_cm, L_tray_cm
    obj_pts = np.array([
        [0, 0, 0],      # TL
        [W, 0, 0],      # TR
        [W, L, 0],      # BR
        [0, L, 0],      # BL
    ], dtype=np.float32)

    # ── Step 7: solvePnP ─────────────────────────────────────────────────
    ok, rvec, tvec = cv2.solvePnP(
        obj_pts, img_pts, K.astype(np.float64),
        dist_coeffs.astype(np.float64)
    )
    if not ok:
        return None

    # ── Step 8: Ekstrak D_tray ───────────────────────────────────────────
    D_raw = abs(float(tvec[2]))
    D_tray = D_raw * math.cos(theta_tilt_rad)

    # Reproj error untuk confidence
    reproj_err = _compute_reprojection_error(
        obj_pts, img_pts, rvec, tvec,
        K.astype(np.float64), dist_coeffs.astype(np.float64)
    )

    # ── Step 9: Validasi range ───────────────────────────────────────────
    if not (D_min <= D_tray <= D_max):
        return {
            "D_tray_cm": round(D_tray, 2),
            "confidence": 0.0,
            "status": "OUT_OF_RANGE",
            "reprojection_error": round(reproj_err, 2),
            "corners": img_pts.tolist(),
            "notes": f"D_tray={D_tray:.2f} cm di luar range [{D_min}, {D_max}]",
        }

    # ── Confidence scoring ───────────────────────────────────────────────
    if reproj_err < 2.0:
        confidence = 0.92 + 0.08 * max(0, 1.0 - reproj_err / 2.0)
    elif reproj_err < 5.0:
        confidence = 0.75 + 0.16 * max(0, 1.0 - (reproj_err - 2.0) / 3.0)
    else:
        confidence = 0.50 + 0.24 * max(0, 1.0 - (reproj_err - 5.0) / 10.0)
        confidence = max(0.50, confidence)

    return {
        "D_tray_cm": round(D_tray, 2),
        "confidence": round(min(confidence, 1.0), 3),
        "status": "OK",
        "reprojection_error": round(reproj_err, 2),
        "corners": img_pts.tolist(),
        "notes": None,
    }
