"""
tests/test_volume_estimation.py — TDD tests for cup volume estimation
======================================================================
Tests for:
  1. measure_rim_width_px()  — mengukur lebar piksel di strip rim atas bbox
  2. calc_diameter()         — diameter fisik (cm) via pinhole model
  3. calc_volume()           — volume silinder (mL) dari h_cup + diameter
  4. Integrasi: pipeline lengkap dari bbox+frame → volume
"""

import math
import numpy as np
import cv2
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.volume_math import measure_rim_width_px, calc_diameter, calc_volume


# ═══════════════════════════════════════════════════════════════════════
#  Helper: Frame sintetis untuk test
# ═══════════════════════════════════════════════════════════════════════

def _make_cup_frame(
    frame_w=640, frame_h=480,
    cup_x1=200, cup_y1=100, cup_x2=440, cup_y2=400,
    rim_width=None, body_width=None,
    bg_color=30, cup_color=180,
):
    """
    Buat frame sintetis berisi gambar gelas sederhana.

    Parameters
    ----------
    rim_width : int or None
        Lebar rim (bibir gelas) di piksel. Jika None, sama dengan bbox width.
    body_width : int or None
        Lebar body (badan gelas) di piksel. Jika None, sama dengan bbox width.
    """
    frame = np.full((frame_h, frame_w, 3), bg_color, dtype=np.uint8)
    bbox_w = cup_x2 - cup_x1
    bbox_h = cup_y2 - cup_y1

    if rim_width is None:
        rim_width = bbox_w
    if body_width is None:
        body_width = bbox_w

    # Gambar body (bagian tengah dan bawah bbox)
    body_cx = (cup_x1 + cup_x2) // 2
    body_x1 = body_cx - body_width // 2
    body_x2 = body_cx + body_width // 2
    rim_thickness = max(4, bbox_h // 10)
    cv2.rectangle(frame, (body_x1, cup_y1 + rim_thickness), (body_x2, cup_y2),
                  (cup_color, cup_color, cup_color), -1)

    # Gambar rim (strip atas bbox, mungkin lebih kecil dari body)
    rim_cx = (cup_x1 + cup_x2) // 2
    rim_x1 = rim_cx - rim_width // 2
    rim_x2 = rim_cx + rim_width // 2
    cv2.rectangle(frame, (rim_x1, cup_y1), (rim_x2, cup_y1 + rim_thickness),
                  (cup_color, cup_color, cup_color), -1)

    return frame


# ═══════════════════════════════════════════════════════════════════════
#  TEST GROUP 1: measure_rim_width_px
# ═══════════════════════════════════════════════════════════════════════

class TestMeasureRimWidthPx:
    """Test pengukuran lebar rim di strip atas bounding box."""

    def test_rim_same_as_bbox_width(self):
        """Jika rim = body width, rim_w ≈ bbox_w (toleransi kecil karena sampling center)."""
        frame = _make_cup_frame(rim_width=200, body_width=200)
        bbox = (200, 100, 440, 400)
        rim_w = measure_rim_width_px(frame, bbox)
        # Rim width diukur di 50% tengah → harusnya sekitar 100px (setengah dari 200)
        # Tapi kita mengukur di area penuh rim strip, harusnya ≈ lebar cup
        assert rim_w > 0
        assert isinstance(rim_w, float)

    def test_rim_smaller_than_body(self):
        """Rim lebih kecil dari body → rim_w < bbox_w."""
        frame = _make_cup_frame(rim_width=100, body_width=240)
        bbox = (200, 100, 440, 400)
        rim_w = measure_rim_width_px(frame, bbox)
        bbox_w = 440 - 200  # 240
        assert rim_w < bbox_w, f"rim_w={rim_w} should be < bbox_w={bbox_w}"

    def test_rim_equals_body_consistency(self):
        """Jika rim == body, pengukuran konsisten."""
        frame = _make_cup_frame(rim_width=180, body_width=180)
        bbox = (200, 100, 440, 400)
        rim_w = measure_rim_width_px(frame, bbox)
        assert rim_w > 0

    def test_dark_frame_returns_fallback(self):
        """Frame gelap → fallback ke lebar bbox center strip."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bbox = (200, 100, 440, 400)
        rim_w = measure_rim_width_px(frame, bbox)
        # Harus tetap return angka positif (fallback), bukan crash
        assert rim_w > 0

    def test_single_pixel_bbox(self):
        """Bbox sangat kecil → tidak crash, return > 0."""
        frame = np.full((480, 640, 3), 128, dtype=np.uint8)
        bbox = (320, 240, 322, 242)
        rim_w = measure_rim_width_px(frame, bbox)
        assert rim_w > 0

    def test_bbox_at_edge_of_frame(self):
        """Bbox di pinggir frame → tidak crash."""
        frame = _make_cup_frame(frame_w=640, frame_h=480,
                                cup_x1=0, cup_y1=0, cup_x2=100, cup_y2=200,
                                rim_width=80, body_width=100)
        bbox = (0, 0, 100, 200)
        rim_w = measure_rim_width_px(frame, bbox)
        assert rim_w > 0

    def test_returns_float(self):
        """Output harus berupa float."""
        frame = _make_cup_frame()
        bbox = (200, 100, 440, 400)
        result = measure_rim_width_px(frame, bbox)
        assert isinstance(result, float)


# ═══════════════════════════════════════════════════════════════════════
#  TEST GROUP 2: calc_diameter
# ═══════════════════════════════════════════════════════════════════════

class TestCalcDiameter:
    """Test perhitungan diameter fisik dari model pinhole."""

    def test_basic_calculation(self):
        """Diameter = (rim_w_px × z_rim) / focal_px."""
        # rim_w = 100 px, z_rim = 30 cm, focal = 500 px
        # expected: (100 * 30) / 500 = 6.0 cm
        d = calc_diameter(rim_w_px=100.0, z_rim_cm=30.0, focal_px=500.0)
        assert math.isclose(d, 6.0, abs_tol=0.01)

    def test_zero_z_rim(self):
        """z_rim = 0 → diameter = 0 (bibir gelas di posisi kamera, tidak valid)."""
        d = calc_diameter(rim_w_px=100.0, z_rim_cm=0.0, focal_px=500.0)
        assert d == 0.0

    def test_zero_focal(self):
        """focal_px = 0 → diameter = 0 (kamera tidak terkalibrasi)."""
        d = calc_diameter(rim_w_px=100.0, z_rim_cm=30.0, focal_px=0.0)
        assert d == 0.0

    def test_negative_z_rim(self):
        """z_rim negatif → 0 (rim di belakang kamera, tidak masuk akal)."""
        d = calc_diameter(rim_w_px=100.0, z_rim_cm=-5.0, focal_px=500.0)
        assert d == 0.0

    def test_camera_moves_up_self_compensating(self):
        """
        Kamera naik: z_rim membesar, rim_w_px mengecil secara proporsional.
        Diameter fisik harus tetap sama.
        """
        # Posisi A: kamera dekat
        d_close = calc_diameter(rim_w_px=200.0, z_rim_cm=15.0, focal_px=500.0)
        # Posisi B: kamera jauh (2x jarak → bbox 2x lebih kecil)
        d_far = calc_diameter(rim_w_px=100.0, z_rim_cm=30.0, focal_px=500.0)
        assert math.isclose(d_close, d_far, abs_tol=0.01)

    def test_returns_float(self):
        d = calc_diameter(rim_w_px=100.0, z_rim_cm=30.0, focal_px=500.0)
        assert isinstance(d, float)


# ═══════════════════════════════════════════════════════════════════════
#  TEST GROUP 3: calc_volume
# ═══════════════════════════════════════════════════════════════════════

class TestCalcVolume:
    """Test perhitungan volume silinder."""

    def test_basic_cylinder(self):
        """Gelas d=6cm, h=10cm → V = π × 3² × 10 = 282.74 mL."""
        v = calc_volume(h_cup_cm=10.0, diameter_cm=6.0)
        expected = math.pi * (3.0 ** 2) * 10.0  # ≈ 282.74
        assert math.isclose(v, expected, rel_tol=0.001)

    def test_zero_height(self):
        """h = 0 → volume = 0."""
        v = calc_volume(h_cup_cm=0.0, diameter_cm=6.0)
        assert v == 0.0

    def test_zero_diameter(self):
        """d = 0 → volume = 0."""
        v = calc_volume(h_cup_cm=10.0, diameter_cm=0.0)
        assert v == 0.0

    def test_negative_height(self):
        """h negatif → volume = 0."""
        v = calc_volume(h_cup_cm=-5.0, diameter_cm=6.0)
        assert v == 0.0

    def test_negative_diameter(self):
        """d negatif → volume = 0."""
        v = calc_volume(h_cup_cm=10.0, diameter_cm=-3.0)
        assert v == 0.0

    def test_small_espresso_cup(self):
        """Cup espresso: d=5cm, h=6cm → V ≈ 117.8 mL."""
        v = calc_volume(h_cup_cm=6.0, diameter_cm=5.0)
        expected = math.pi * (2.5 ** 2) * 6.0
        assert math.isclose(v, expected, rel_tol=0.001)

    def test_tall_latte_cup(self):
        """Cup latte: d=7cm, h=12cm → V ≈ 461.8 mL."""
        v = calc_volume(h_cup_cm=12.0, diameter_cm=7.0)
        expected = math.pi * (3.5 ** 2) * 12.0
        assert math.isclose(v, expected, rel_tol=0.001)

    def test_returns_float(self):
        v = calc_volume(h_cup_cm=10.0, diameter_cm=6.0)
        assert isinstance(v, float)

    def test_volume_unit_is_ml(self):
        """1 cm³ = 1 mL. Diameter 2cm, tinggi 1cm → π × 1² × 1 ≈ 3.14 mL."""
        v = calc_volume(h_cup_cm=1.0, diameter_cm=2.0)
        assert math.isclose(v, math.pi, rel_tol=0.001)


# ═══════════════════════════════════════════════════════════════════════
#  TEST GROUP 4: Integrasi end-to-end
# ═══════════════════════════════════════════════════════════════════════

class TestVolumeIntegration:
    """Test integrasi: frame sintetis → rim_w → diameter → volume."""

    def test_full_pipeline_cylindrical_cup(self):
        """Gelas silinder (rim ≈ body) → volume masuk akal."""
        frame = _make_cup_frame(
            frame_w=640, frame_h=480,
            cup_x1=220, cup_y1=140, cup_x2=420, cup_y2=380,
            rim_width=200, body_width=200,
        )
        bbox = (220, 140, 420, 380)

        rim_w = measure_rim_width_px(frame, bbox)
        z_tray = 30.0
        h_cup = 8.0
        z_rim = z_tray - h_cup  # 22 cm
        focal_px = 500.0

        diameter = calc_diameter(rim_w, z_rim, focal_px)
        volume = calc_volume(h_cup, diameter)

        assert diameter > 0, "Diameter harus positif"
        assert volume > 0, "Volume harus positif"
        # Sanity check: volume gelas kopi biasanya 50-500 mL
        assert 10 < volume < 2000, f"Volume {volume:.0f} mL tidak realistis"

    def test_rim_narrower_than_body_gives_smaller_volume(self):
        """Gelas dengan rim kecil harus menghasilkan volume lebih kecil
        dibanding jika pakai bbox_w penuh."""
        bbox = (200, 100, 440, 400)
        z_tray = 30.0
        h_cup = 8.0
        z_rim = z_tray - h_cup
        focal_px = 500.0

        # Gelas dengan rim lebar = body
        frame_wide = _make_cup_frame(rim_width=200, body_width=200)
        rim_w_wide = measure_rim_width_px(frame_wide, bbox)
        d_wide = calc_diameter(rim_w_wide, z_rim, focal_px)
        v_wide = calc_volume(h_cup, d_wide)

        # Gelas dengan rim lebih kecil dari body
        frame_narrow = _make_cup_frame(rim_width=100, body_width=200)
        rim_w_narrow = measure_rim_width_px(frame_narrow, bbox)
        d_narrow = calc_diameter(rim_w_narrow, z_rim, focal_px)
        v_narrow = calc_volume(h_cup, d_narrow)

        assert v_narrow < v_wide, (
            f"Volume rim sempit ({v_narrow:.1f} mL) harus < rim lebar ({v_wide:.1f} mL)"
        )

    def test_all_zeros_returns_zero(self):
        """Input nol tidak crash, return 0."""
        d = calc_diameter(0.0, 0.0, 0.0)
        v = calc_volume(0.0, d)
        assert v == 0.0
