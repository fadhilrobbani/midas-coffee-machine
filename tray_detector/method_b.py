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
        # Bandingkan dengan titik referensi cluster (garis pertama di current) agar cluster tidak memanjang tanpa batas "chain merging"
        if sorted_lines[i]["y_mid"] - current[0]["y_mid"] <= cluster_gap:
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
        longest_line = max(cluster, key=lambda l: l["length"])
        x1_min = longest_line["x1"]
        x2_max = longest_line["x2"]
        merged.append({
            "y_mid": y_avg, "x_mid": x_avg,
            "x1": x1_min, "x2": x2_max,
            "y1": round(y_avg), "y2": round(y_avg),
            "count": len(cluster),
            "length": total_w,  # simpan length untuk NMS
        })
        
    # ── Non-Maximum Suppression (NMS) Spasial ────────────────────────────
    # Buang garis yang terlalu berdekatan (membatasi 1 garis per sekat fisik).
    # Bertujuan menghapus deteksi ganda di sisi atas & bawah sekat yang tebal.
    if not merged:
        return []
    
    # Urutkan berdasarkan bobot panjang garis (prioritas garis paling solid)
    merged.sort(key=lambda x: x["length"], reverse=True)
    nms_merged = []
    nms_thresh = 10.0  # Toleransi 10 pixel vertikal sebagai ketebalan 1 sekat
    
    for line in merged:
        keep = True
        for kept_line in nms_merged:
            if abs(line["y_mid"] - kept_line["y_mid"]) <= nms_thresh:
                keep = False
                break
        if keep:
            nms_merged.append(line)
            
    # Kembalikan agar terurut dari atas ke bawah secara vertikal
    nms_merged.sort(key=lambda x: x["y_mid"])
    return nms_merged


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


def _split_raw_lines_by_zone(h_lines, glass_bbox, frame_width):
    """Pisahkan raw garis ke zona kiri/kanan berdasarkan glass_bbox."""
    left_lines, right_lines = [], []

    if glass_bbox is not None:
        left_boundary = glass_bbox[0] - 10
        right_boundary = glass_bbox[2] + 10
    else:
        mid_x = frame_width // 2
        left_boundary = mid_x
        right_boundary = mid_x

    for line in h_lines:
        cx = line["x_mid"]
        if glass_bbox is not None:
            if cx < left_boundary:
                left_lines.append(line)
            elif cx > right_boundary:
                right_lines.append(line)
        else:
            if cx < left_boundary:
                left_lines.append(line)
            else:
                right_lines.append(line)

    return left_lines, right_lines


def _compute_zone_D(y_mids, f_pixel, P_real_cm, theta_tilt_rad, D_min, D_max):
    """
    Hitung D_tray untuk satu zona menggunakan dua metode:
    1. Pitch-based: D = (f * P * cos(theta)) / median_pitch
    2. Span-based:  D = (f * N_gaps * P * cos(theta)) / span_px
    
    Metode span-based kebal terhadap auto-focus karena menggunakan
    total rentang vertikal dari semua sekat yang terdeteksi.
    """
    if len(y_mids) < 3:
        return None, 0, None
    
    y_sorted = sorted(y_mids)
    gaps = np.diff(y_sorted)
    
    if len(gaps) == 0:
        return None, 0, None
    
    # IQR filtering pada gaps
    q1, q3 = np.percentile(gaps, [25, 75])
    iqr = q3 - q1
    if iqr < 1e-6:
        valid_gaps = gaps
    else:
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        valid_gaps = gaps[(gaps >= lower) & (gaps <= upper)]
    
    if len(valid_gaps) == 0:
        valid_gaps = gaps
    
    p_avg = float(np.median(valid_gaps))
    
    if p_avg < 1.0:
        return None, len(valid_gaps), p_avg
    
    # ── Metode 1: Pitch-based (klasik) ───────────────────────────────────
    D_pitch = (f_pixel * P_real_cm * math.cos(theta_tilt_rad)) / p_avg
    
    # ── Metode 2: Span-based (anti auto-focus) ──────────────────────────
    # Gunakan rentang vertikal penuh dari sekat pertama sampai terakhir
    span_px = y_sorted[-1] - y_sorted[0]
    n_gaps = len(y_sorted) - 1  # jumlah celah = jumlah sekat - 1
    
    D_span = None
    if span_px > 10 and n_gaps >= 2:
        # Total jarak fisik dari sekat pertama ke terakhir = n_gaps * P_real_cm
        total_physical_cm = n_gaps * P_real_cm
        D_span = (f_pixel * total_physical_cm * math.cos(theta_tilt_rad)) / span_px
    
    # ── Pilih metode terbaik ─────────────────────────────────────────────
    # Span-based lebih stabil terhadap auto-focus, jadi gunakan sebagai primary
    if D_span is not None and D_min <= D_span <= D_max:
        D_tray = D_span
    elif D_min <= D_pitch <= D_max:
        D_tray = D_pitch
    else:
        return None, len(valid_gaps), p_avg
    
    return round(D_tray, 2), len(valid_gaps), p_avg


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

    # ── Apply base mask → enhance → detect edges ────────────────────────
    mask_u8 = (tray_mask > 0).astype(np.uint8) * 255
    roi = cv2.bitwise_and(frame, frame, mask=mask_u8)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)
    
    # Adaptive Canny: Hitung median piksel agar gambar gelap tetap terdeteksi sekatnya
    med = np.median(blurred)
    c_low = max(5, int(0.66 * med))
    c_high = min(255, int(1.33 * med))
    # Batasi agar Canny tidak telalu tinggi saat gambar tidak rata (dark)
    c_low = min(canny_low, c_low)
    c_high = min(canny_high, c_high)
    
    edges = cv2.Canny(blurred, c_low, c_high)

    # ── Terapkan Strict ROI Mask pada edges ──────────────────────────────
    # Membuat dua kotak "sempit" tepat di kiri dan kanan gelas.
    # Memotong margin atas/bawah 15% agar ujung rim solid tray diabaikan.
    if glass_bbox is not None:
        gx1, gy1, gx2, gy2 = glass_bbox
        g_h = gy2 - gy1
        
        margin_y = int(g_h * 0.15)
        box_y1 = max(0, int(gy1 + margin_y))
        box_y2 = min(h, int(gy2 - margin_y))
        
        search_w = 250
        lx1, lx2 = max(0, int(gx1 - search_w)), int(gx1 - 5)
        rx1, rx2 = int(gx2 + 5), min(w, int(gx2 + search_w))
        
        strict_mask = np.zeros_like(edges)
        if lx2 > lx1:
            strict_mask[box_y1:box_y2, lx1:lx2] = 255
        if rx2 > rx1:
            strict_mask[box_y1:box_y2, rx1:rx2] = 255
            
        edges = cv2.bitwise_and(edges, strict_mask)
    else:
        # Fallback jika tidak ada gelas:
        # 1. Buang secara paksa noise statis dari dinding atas & rim plastik bawah
        # 2. Pura-pura ada gelas di tengah tray untuk memotong pola bundar drain hole!
        # Ini akan memaksa algoritma hanya mengecek sisi paling kiri dan paling kanan.
        box_y1 = int(h * 0.33)
        box_y2 = int(h * 0.79)
        
        mid_x = w // 2
        # Asumsikan diameter drain hole ~ 160 px, kita lewati 80 px ke kiri & kanan
        skip_radius = 80
        lx2 = max(0, mid_x - skip_radius)
        lx1 = max(0, lx2 - 200)  # Box kiri selebar 200px
        
        rx1 = min(w, mid_x + skip_radius)
        rx2 = min(w, rx1 + 200)
        
        strict_mask = np.zeros_like(edges)
        if lx2 > lx1:
            strict_mask[box_y1:box_y2, lx1:lx2] = 255
        if rx2 > rx1:
            strict_mask[box_y1:box_y2, rx1:rx2] = 255
            
        edges = cv2.bitwise_and(edges, strict_mask)

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

    # ── Split zona LALU Cluster ──────────────────────────────────────────
    # Ini sangat penting untuk frame bergambar gelas: jika kita cluster
    # seluruh frame dulu, xy_mid dari sekat akan berada tepat di tengah frame
    # (di balik gelas) yang menyebabkannya difilter habis.
    left_raw, right_raw = _split_raw_lines_by_zone(h_lines, glass_bbox, w)

    left_merged = _cluster_lines(left_raw, cluster_gap=6.0)
    right_merged = _cluster_lines(right_raw, cluster_gap=6.0)

    debug_clustered = [(l["x1"], l["y1"], l["x2"], l["y2"]) for l in left_merged + right_merged]

    total_merged = len(left_merged) + len(right_merged)
    if total_merged == 0:
        return _empty_result(
            "Tidak ada sekat valid setelah split zona dan clustering",
            debug_raw=debug_raw, debug_clustered=debug_clustered,
        )

    left_y = [l["y_mid"] for l in left_merged]
    right_y = [l["y_mid"] for l in right_merged]

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
        # Fallback: coba semua garis digabung jadi satu
        all_merged = _cluster_lines(h_lines, cluster_gap=6.0)
        all_y = [l["y_mid"] for l in all_merged]
        p_avg, n_all = _compute_pitch_iqr(all_y)
        if p_avg and p_avg > 1.0:
            D_all = (f_pixel * P_real_cm * math.cos(theta_tilt_rad)) / p_avg
            if D_min <= D_all <= D_max:
                D_tray = round(D_all, 2)
                status = "FULL_FRAME"
                notes = f"{len(all_merged)} sekat full-frame, pitch={p_avg:.1f}px"
            else:
                return _empty_result(
                    f"D={D_all:.1f}cm di luar [{D_min},{D_max}]. "
                    f"pitch={p_avg:.1f}px, {len(all_merged)} sekat",
                    debug_raw=debug_raw, debug_clustered=debug_clustered,
                )
        else:
            return _empty_result(
                "Pitch tidak valid",
                debug_raw=debug_raw, debug_clustered=debug_clustered,
            )

    if D_tray is None:
        return _empty_result(
            "Tidak ada zona yang valid",
            debug_raw=debug_raw, debug_clustered=debug_clustered,
        )

    # ── Slat-Count Correction (anti auto-focus stagnation) ────────────────
    # Auto-focus mengubah f_eff ∝ D, sehingga pitch tetap konstan.
    # Namun JUMLAH sekat yang terlihat berkurang saat tray menjauh
    # (karena FOV tidak sempurna linear). Kita gunakan rasio jumlah sekat
    # sebagai proxy untuk koreksi.
    # Kalibrasi: pada D=25cm dengan YOLO aktif, terdeteksi ~27 sekat total.
    total_slats = len(left_merged) + len(right_merged)
    REF_SLATS = 27  # jumlah sekat pada jarak kalibrasi (25cm, YOLO ON)
    
    if total_slats > 0 and total_slats != REF_SLATS:
        raw_ratio = REF_SLATS / total_slats
        # Gunakan sqrt(ratio) sebagai koreksi:
        #   - 27/15 = 1.8 → sqrt → 1.342 → 25cm * 1.342 = 33.6cm ✓
        #   - 27/27 = 1.0 → sqrt → 1.0   → 25cm * 1.0   = 25.0cm ✓
        #   - 27/30 = 0.9 → sqrt → 0.949 → 25cm * 0.949 = 23.7cm ✓
        correction = math.sqrt(raw_ratio) if raw_ratio > 0 else 1.0
        # Batasi koreksi: max ±50% untuk keamanan
        correction = max(0.7, min(1.5, correction))
        D_tray = round(D_tray * correction, 2)
        if D_left is not None:
            D_left = round(D_left * correction, 2)
        if D_right is not None:
            D_right = round(D_right * correction, 2)

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
    total_slats = len(left_merged) + len(right_merged)
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
