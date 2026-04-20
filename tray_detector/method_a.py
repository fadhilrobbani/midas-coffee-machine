"""
method_a.py — Metode A: Apparent Width Tray (Fallback / Last Resort)

Estimasi D_tray berdasarkan rasio lebar fisik tray vs lebar piksel
dari bounding box YOLO.

Formula:
    D_raw  = (f_pixel × W_real_cm) / W_pixel
    D_tray = D_raw × cos(theta_tilt)
"""

import math


def estimate_D_tray_method_A(bbox, f_pixel, W_real_cm, theta_tilt_rad,
                              frame_width, D_min=5.0, D_max=40.0):
    """
    Estimasi jarak kamera ke tray menggunakan apparent width bounding box.

    Args:
        bbox: tuple (x1, y1, x2, y2) bounding box tray dari YOLO
        f_pixel: focal length kamera dalam piksel
        W_real_cm: lebar fisik tray dalam cm
        theta_tilt_rad: sudut condong kamera dari vertikal (radian)
        frame_width: lebar frame dalam piksel
        D_min: batas minimum D_tray (cm)
        D_max: batas maksimum D_tray (cm)

    Returns:
        dict dengan keys: D_tray_cm, confidence, status, notes
        atau None jika data tidak cukup
    """
    x1, y1, x2, y2 = bbox
    W_pixel = x2 - x1

    # Bounding box terlalu kecil — data tidak valid
    if W_pixel < 20:
        return None

    # ── Kalkulasi D_tray ─────────────────────────────────────────────────
    D_raw = (f_pixel * W_real_cm) / W_pixel
    D_tray = D_raw * math.cos(theta_tilt_rad)

    # ── Validasi range ───────────────────────────────────────────────────
    if not (D_min <= D_tray <= D_max):
        return {
            "D_tray_cm": round(D_tray, 2),
            "confidence": 0.0,
            "status": "OUT_OF_RANGE",
            "notes": f"D_tray={D_tray:.2f} cm di luar range [{D_min}, {D_max}]",
        }

    # ── Confidence scoring ───────────────────────────────────────────────
    edge_margin = 10  # piksel
    near_left = x1 < edge_margin
    near_right = x2 > (frame_width - edge_margin)
    fill_ratio = W_pixel / frame_width

    if fill_ratio > 0.6:
        # Bbox mencakup sebagian besar frame — kemungkinan no-yolo mode
        # atau tray sangat dekat. Confidence moderat.
        confidence = 0.50 + 0.15 * min(fill_ratio, 1.0)
        confidence = max(0.50, min(0.65, confidence))
        notes = "Bbox lebar (mungkin mode no-yolo)"
    elif near_left or near_right:
        # Bbox terpotong di tepi tapi tidak full-frame
        confidence = 0.30 + 0.10 * (min(x1, frame_width - x2) / edge_margin)
        confidence = max(0.30, min(0.45, confidence))
        notes = "Bbox mepet tepi frame, akurasi terbatas"
    else:
        # Bbox normal dari YOLO detection
        confidence = 0.55 + 0.10 * min(fill_ratio / 0.4, 1.0)
        confidence = max(0.55, min(0.65, confidence))
        notes = None

    return {
        "D_tray_cm": round(D_tray, 2),
        "confidence": round(confidence, 3),
        "status": "OK",
        "notes": notes,
    }
