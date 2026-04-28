"""
core/image_preprocess.py — Preprocessing pipeline untuk meningkatkan kualitas
gambar fisheye sebelum deteksi ArUco dan rim gelas.

Modul ini menyediakan:
  - apply_clahe()           : CLAHE untuk kontrast lokal
  - apply_unsharp_mask()    : Sharpening dengan unsharp masking
  - detect_fisheye_circle() : Deteksi lingkaran fisheye dengan HoughCircles
  - crop_fisheye_to_rect()  : Crop area fisheye ke persegi panjang
  - enhance_for_detection() : Pipeline lengkap (CLAHE + unsharp + normalisasi)
"""

import cv2
import numpy as np


def apply_clahe(
    frame: np.ndarray,
    clip_limit: float = 3.0,
    tile_grid_size: tuple = (8, 8),
) -> np.ndarray:
    """
    Terapkan CLAHE (Contrast Limited Adaptive Histogram Equalization) pada
    channel L dari LAB colorspace untuk meningkatkan kontrast lokal tanpa
    mengubah saturasi warna.

    Args:
        frame      : BGR image
        clip_limit : Batas amplifikasi kontras (default 3.0; semakin tinggi
                     semakin kontras tapi semakin noisy)
        tile_grid_size : Ukuran tile untuk histogram lokal

    Returns:
        BGR image yang sudah di-enhance
    """
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def apply_unsharp_mask(
    frame: np.ndarray,
    sigma: float = 1.0,
    strength: float = 1.5,
) -> np.ndarray:
    """
    Terapkan unsharp masking untuk mempertajam gambar.

    Formula: output = frame * (1 + strength) - blurred * strength

    Args:
        frame    : BGR image
        sigma    : Standar deviasi Gaussian blur kernel
        strength : Kekuatan sharpening (default 1.5; lebih tinggi = lebih tajam)

    Returns:
        BGR image yang sudah di-sharpen
    """
    blurred = cv2.GaussianBlur(frame, (0, 0), sigma)
    sharpened = cv2.addWeighted(frame, 1.0 + strength, blurred, -strength, 0)
    return sharpened


def detect_fisheye_circle(
    frame: np.ndarray,
    dp: float = 1.2,
    min_dist_ratio: float = 0.5,
    param1: float = 100,
    param2: float = 30,
) -> tuple:
    """
    Deteksi lingkaran fisheye menggunakan HoughCircles.

    Untuk kamera fisheye yang dipasang pointing-down, gambar akan memiliki
    lingkaran besar di tengah dengan area hitam di sekeliling (vignetting).

    Returns:
        (cx, cy, radius) dalam pixel.
        Fallback ke pusat + min(H,W)/2 jika tidak ada lingkaran terdeteksi.
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (11, 11), 2)

    min_r = int(min(h, w) * 0.25)
    max_r = int(min(h, w) * 0.55)

    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=dp,
        minDist=int(min(h, w) * min_dist_ratio),
        param1=param1,
        param2=param2,
        minRadius=min_r,
        maxRadius=max_r,
    )

    if circles is not None:
        # Ambil lingkaran dengan radius terbesar (= fisheye circle utama)
        circles = np.round(circles[0, :]).astype(int)
        best = max(circles, key=lambda c: c[2])
        cx, cy, r = int(best[0]), int(best[1]), int(best[2])
    else:
        # Fallback: estimasi dari vignetting (area tengah lebih terang)
        cx, cy = w // 2, h // 2
        # Radius dari threshold otomatis
        _, thresh = cv2.threshold(blurred, 15, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            (cx, cy), r = cv2.minEnclosingCircle(largest)
            cx, cy, r = int(cx), int(cy), int(r)
        else:
            r = int(min(h, w) * 0.4)

    return cx, cy, r


def crop_fisheye_to_rect(
    frame: np.ndarray,
    margin: float = 0.05,
    output_size: tuple = None,
) -> np.ndarray:
    """
    Crop frame fisheye ke kotak persegi panjang yang mencakup area valid
    (dalam lingkaran fisheye), lalu resize ke output_size.

    Area crop adalah bounding box dari lingkaran fisheye dikurangi margin.

    Args:
        frame       : BGR fisheye image
        margin      : Margin tambahan (0.05 = 5% dari radius) untuk menghindari
                      tepi lingkaran yang blur
        output_size : (width, height) output. None = gunakan ukuran crop asli.

    Returns:
        BGR image hasil crop
    """
    cx, cy, r = detect_fisheye_circle(frame)
    h, w = frame.shape[:2]

    # Inscribed square dalam lingkaran (diagonal = 2r → sisi = r*sqrt(2))
    half_side = int(r * (1.0 - margin) / np.sqrt(2))

    x1 = max(0, cx - half_side)
    y1 = max(0, cy - half_side)
    x2 = min(w, cx + half_side)
    y2 = min(h, cy + half_side)

    cropped = frame[y1:y2, x1:x2]

    if output_size is not None:
        cropped = cv2.resize(cropped, output_size, interpolation=cv2.INTER_LINEAR)

    return cropped


def enhance_for_detection(
    frame: np.ndarray,
    clahe_clip: float = 3.0,
    unsharp_sigma: float = 1.0,
    unsharp_strength: float = 1.5,
) -> np.ndarray:
    """
    Pipeline lengkap preprocessing untuk meningkatkan deteksi ArUco dan rim gelas.

    Urutan:
      1. CLAHE  — perbaiki kontrast lokal (terutama marker yang terlalu gelap/terang)
      2. Unsharp masking — pertajam tepi untuk deteksi ArUco yang lebih akurat

    Args:
        frame            : BGR image (fisheye yang sudah di-undistort)
        clahe_clip       : CLAHE clip limit
        unsharp_sigma    : Sigma Gaussian untuk unsharp mask
        unsharp_strength : Kekuatan sharpening

    Returns:
        BGR image yang sudah di-enhance, shape sama dengan input.
    """
    enhanced = apply_clahe(frame, clip_limit=clahe_clip)
    enhanced = apply_unsharp_mask(enhanced, sigma=unsharp_sigma,
                                  strength=unsharp_strength)
    return enhanced
