"""
method_b.py — Metode B: Horizontal Slat Pitch (PRIMARY / Utama)

Estimasi D_tray dari jarak antar sekat horizontal tray di frame.
Pipeline: mask → CLAHE → Canny → HoughLinesP → filter horizontal →
cluster nearby lines → split zona → IQR pitch → kalkulasi D.

Formula:
    D_tray = (f_pixel × P_real_cm × cos(theta_tilt)) / p_avg_pixel
"""

import math
import cv2
import numpy as np


def _filter_horizontal_lines(lines, angle_tol_deg=10.0):
    """Pertahankan hanya garis horizontal."""
    horizontal = []
    if lines is None:
        return horizontal
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))
        if angle < angle_tol_deg or angle > (180 - angle_tol_deg):
            y_mid = (y1 + y2) / 2.0
            x_mid = (x1 + x2) / 2.0
            length = math.hypot(x2 - x1, y2 - y1)
            horizontal.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "y_mid": y_mid, "x_mid": x_mid, "length": length,
            })
    return horizontal


def _cluster_lines(h_lines, cluster_gap=8.0):
    """
    Merge garis horizontal berdekatan (dalam cluster_gap piksel)
    menjadi satu garis per sekat. Weighted average berdasarkan panjang.
    """
    if not h_lines:
        return []

    sorted_lines = sorted(h_lines, key=lambda l: l["y_mid"])
    clusters = []
    current = [sorted_lines[0]]

    for i in range(1, len(sorted_lines)):
        if sorted_lines[i]["y_mid"] - current[-1]["y_mid"] <= cluster_gap:
            current.append(sorted_lines[i])
        else:
            clusters.append(current)
            current = [sorted_lines[i]]
    clusters.append(current)

    merged = []
    for cluster in clusters:
        total_w = sum(l["length"] for l in cluster)
        if total_w < 1e-6:
            continue
        y_avg = sum(l["y_mid"] * l["length"] for l in cluster) / total_w
        x_avg = sum(l["x_mid"] * l["length"] for l in cluster) / total_w
        x1_min = min(l["x1"] for l in cluster)
        x2_max = max(l["x2"] for l in cluster)
        merged.append({
            "y_mid": y_avg, "x_mid": x_avg,
            "x1": x1_min, "x2": x2_max,
            "y1": round(y_avg), "y2": round(y_avg),
            "count": len(cluster),
        })
    return merged


def _compute_pitch_iqr(y_mids):
    """Hitung median pitch antar garis setelah IQR filtering."""
    if len(y_mids) < 3:
        return None, len(y_mids)

    y_sorted = sorted(y_mids)
    gaps = np.diff(y_sorted)

    if len(gaps) == 0:
        return None, 0

    q1, q3 = np.percentile(gaps, [25, 75])
    iqr = q3 - q1
    if iqr < 1e-6:
        valid = gaps
    else:
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        valid = gaps[(gaps >= lower) & (gaps <= upper)]

    if len(valid) == 0:
        valid = gaps

    return float(np.median(valid)), len(valid)


def _split_lines_by_zone(merged_lines, glass_bbox, frame_width):
    """Pisahkan garis ke zona kiri/kanan berdasarkan glass_bbox."""
    left_y, right_y = [], []

    if glass_bbox is not None:
        left_boundary = glass_bbox[0] - 10
        right_boundary = glass_bbox[2] + 10
    else:
        mid_x = frame_width // 2
        left_boundary = mid_x
        right_boundary = mid_x

    for line in merged_lines:
        cx = line["x_mid"]
        if glass_bbox is not None:
            if cx < left_boundary:
                left_y.append(line["y_mid"])
            elif cx > right_boundary:
                right_y.append(line["y_mid"])
        else:
            if cx < left_boundary:
                left_y.append(line["y_mid"])
            else:
                right_y.append(line["y_mid"])

    return left_y, right_y


def _compute_zone_D(y_mids, f_pixel, P_real_cm, theta_tilt_rad, D_min, D_max):
    """Hitung D_tray untuk satu zona."""
    p_avg, num_valid = _compute_pitch_iqr(y_mids)
    if p_avg is None or p_avg < 1.0:
        return None, 0, p_avg
    D_tray = (f_pixel * P_real_cm * math.cos(theta_tilt_rad)) / p_avg
    if not (D_min <= D_tray <= D_max):
        return None, num_valid, p_avg
    return round(D_tray, 2), num_valid, p_avg


def estimate_D_tray_method_B(frame, tray_mask, glass_bbox,
                              f_pixel, P_real_cm, theta_tilt_rad,
                              canny_low=20, canny_high=80,
                              hough_threshold=25, hough_min_line_length=25,
                              hough_max_line_gap=15,
                              angle_tol_deg=10.0, min_lines=3,
                              D_min=5.0, D_max=100.0):
    """
    Estimasi D_tray menggunakan pitch sekat horizontal tray.

    Pipeline:
      mask → CLAHE → GaussianBlur → Canny → HoughLinesP →
      filter horizontal → cluster → split zona → IQR pitch → D_tray

    Returns:
        dict: D_tray_cm, confidence, status, D_left_cm, D_right_cm,
              lines_left, lines_right, notes, debug_lines, debug_clustered,
              pitch_px, num_slats
    """
    h, w = frame.shape[:2]

    # ── Validasi mask ────────────────────────────────────────────────────
    if tray_mask is None or np.count_nonzero(tray_mask) < 500:
        return _empty_result("Tray mask terlalu kecil atau tidak ada")

    # ── Apply mask → enhance → edge detect → Hough ──────────────────────
    mask_u8 = (tray_mask > 0).astype(np.uint8) * 255
    roi = cv2.bitwise_and(frame, frame, mask=mask_u8)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
    edges = cv2.Canny(blurred, canny_low, canny_high)

    lines = cv2.HoughLinesP(edges, rho=1, theta=np.pi / 180,
                            threshold=hough_threshold,
                            minLineLength=hough_min_line_length,
                            maxLineGap=hough_max_line_gap)

    # ── Filter horizontal ────────────────────────────────────────────────
    h_lines = _filter_horizontal_lines(lines, angle_tol_deg)
    debug_raw = [(l["x1"], l["y1"], l["x2"], l["y2"]) for l in h_lines]

    if len(h_lines) < min_lines:
        return _empty_result(
            f"Hanya {len(h_lines)} garis horizontal (min={min_lines})",
            debug_raw=debug_raw,
        )

    # ── Cluster nearby lines ─────────────────────────────────────────────
    merged = _cluster_lines(h_lines, cluster_gap=8.0)
    debug_clustered = [(l["x1"], l["y1"], l["x2"], l["y2"]) for l in merged]

    if len(merged) < min_lines:
        return _empty_result(
            f"Hanya {len(merged)} sekat setelah clustering (min={min_lines})",
            debug_raw=debug_raw, debug_clustered=debug_clustered,
        )

    # ── Split zona ───────────────────────────────────────────────────────
    left_y, right_y = _split_lines_by_zone(merged, glass_bbox, w)

    D_left, n_left, p_left = _compute_zone_D(
        left_y, f_pixel, P_real_cm, theta_tilt_rad, D_min, D_max)
    D_right, n_right, p_right = _compute_zone_D(
        right_y, f_pixel, P_real_cm, theta_tilt_rad, D_min, D_max)

    left_valid = D_left is not None and len(left_y) >= min_lines
    right_valid = D_right is not None and len(right_y) >= min_lines

    # ── Tentukan D_tray ──────────────────────────────────────────────────
    if left_valid and right_valid:
        D_tray = round((D_left + D_right) / 2.0, 2)
        status = "OK"
        notes = None
    elif left_valid:
        D_tray = D_left
        status = "SINGLE_ZONE"
        notes = "Hanya zona kiri valid"
    elif right_valid:
        D_tray = D_right
        status = "SINGLE_ZONE"
        notes = "Hanya zona kanan valid"
    else:
        # Fallback: coba semua clustered lines tanpa split
        all_y = [l["y_mid"] for l in merged]
        p_avg, n_all = _compute_pitch_iqr(all_y)
        if p_avg and p_avg > 1.0:
            D_all = (f_pixel * P_real_cm * math.cos(theta_tilt_rad)) / p_avg
            if D_min <= D_all <= D_max:
                D_tray = round(D_all, 2)
                status = "FULL_FRAME"
                notes = f"{len(merged)} sekat, pitch={p_avg:.1f}px"
            else:
                return _empty_result(
                    f"D={D_all:.1f}cm di luar [{D_min},{D_max}]. "
                    f"pitch={p_avg:.1f}px, {len(merged)} sekat",
                    debug_raw=debug_raw, debug_clustered=debug_clustered,
                )
        else:
            return _empty_result(
                "Pitch tidak valid",
                debug_raw=debug_raw, debug_clustered=debug_clustered,
            )

    # ── Validasi range ───────────────────────────────────────────────────
    if not (D_min <= D_tray <= D_max):
        return {
            **_empty_result(f"D_tray={D_tray}cm di luar [{D_min},{D_max}]",
                            debug_raw, debug_clustered),
            "D_tray_cm": D_tray,
            "D_left_cm": D_left, "D_right_cm": D_right,
            "lines_left": len(left_y), "lines_right": len(right_y),
            "status": "OUT_OF_RANGE",
        }

    # ── Confidence scoring (max ~0.85, sane range) ───────────────────────
    total_slats = len(merged)
    p_avg_final = p_left or p_right or 0

    if left_valid and right_valid:
        # Kedua zona valid — terbaik
        if total_slats >= 10:
            confidence = 0.70 + 0.15 * min((total_slats - 10) / 10, 1.0)
        elif total_slats >= 6:
            confidence = 0.60 + 0.10 * ((total_slats - 6) / 4)
        else:
            confidence = 0.55
    elif status == "FULL_FRAME":
        if total_slats >= 8:
            confidence = 0.55 + 0.10 * min((total_slats - 8) / 8, 1.0)
        elif total_slats >= 5:
            confidence = 0.45 + 0.10 * ((total_slats - 5) / 3)
        else:
            confidence = 0.40
    else:
        # SINGLE_ZONE
        zone_lines = len(left_y) if left_valid else len(right_y)
        if zone_lines >= 5:
            confidence = 0.50 + 0.10 * min((zone_lines - 5) / 5, 1.0)
        else:
            confidence = 0.40 + 0.10 * ((zone_lines - min_lines) /
                                          max(5 - min_lines, 1))

    # Cap di 0.85 — metode ini tidak pernah 100% pasti
    confidence = min(confidence, 0.85)

    return {
        "D_tray_cm": D_tray,
        "confidence": round(confidence, 3),
        "status": status,
        "D_left_cm": D_left,
        "D_right_cm": D_right,
        "lines_left": len(left_y),
        "lines_right": len(right_y),
        "notes": notes,
        "debug_lines": debug_raw,
        "debug_clustered": debug_clustered,
        "pitch_px": round(p_avg_final, 1) if p_avg_final else None,
        "num_slats": total_slats,
    }


def _empty_result(notes, debug_raw=None, debug_clustered=None):
    return {
        "D_tray_cm": None, "confidence": 0.0,
        "status": "INSUFFICIENT_DATA",
        "D_left_cm": None, "D_right_cm": None,
        "lines_left": 0, "lines_right": 0,
        "notes": notes,
        "debug_lines": debug_raw or [],
        "debug_clustered": debug_clustered or [],
        "pitch_px": None, "num_slats": 0,
    }
