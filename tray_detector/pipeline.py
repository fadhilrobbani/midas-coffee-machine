"""
pipeline.py — Main Pipeline Orchestrator

Menjalankan urutan lengkap:
  1. Undistort frame
  2. YOLO inference → tray bbox/mask + glass bbox
  3. Jalankan Metode B (primary), C (backup), A (fallback)
  4. Fusi hasil → output schema final
  5. Annotasi frame untuk visualisasi
"""

import cv2
import numpy as np
import os
import sys
import math

# Pastikan root project ada di sys.path untuk import midas_volumecup
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from .config import get_default_config
from .method_a import estimate_D_tray_method_A
from .method_b import estimate_D_tray_method_B
from .method_c import estimate_D_tray_method_C
from .fusion import fuse_results


class TrayDistancePipeline:
    """
    Pipeline utama untuk estimasi D_tray_cm.

    Usage:
        pipeline = TrayDistancePipeline()
        result = pipeline.process_frame(frame)
        annotated = pipeline.annotate_frame(frame, result)
    """

    def __init__(self, weights_path=None, params_path=None, config=None,
                 no_yolo=False, method="auto"):
        """
        Args:
            weights_path: path ke YOLO weights (.pt)
            params_path: path ke calibration YAML
            config: dict konfigurasi (override default)
            no_yolo: jika True, skip YOLO dan gunakan full frame sebagai ROI
            method: metode deteksi — 'auto', 'A', 'B', 'C' (case-insensitive)
        """
        self.cfg = config or get_default_config(params_path)
        self.no_yolo = no_yolo
        self.method = method.upper() if method else "AUTO"

        if self.method not in ("AUTO", "A", "B", "C"):
            raise ValueError(f"Method harus 'auto', 'A', 'B', atau 'C', bukan '{method}'")

        if weights_path:
            self.cfg["weights_path"] = weights_path

        # Load YOLO detector (skip jika no_yolo)
        self.detector = None
        if not no_yolo:
            from midas_volumecup.detector import YoloDetector
            self.detector = YoloDetector(weights_path=self.cfg["weights_path"])
        else:
            print("[INFO] Mode --no-yolo: YOLO dinonaktifkan, menggunakan full frame.")

        print(f"[INFO] Metode aktif: {self.method}")

        # ── YOLO caching untuk live cam (hemat CPU) ──────────────────────
        self._frame_count = 0
        self._cached_yolo = (None, None, None)  # (tray_bbox, tray_mask, glass_bbox)
        self.yolo_interval = 5  # Jalankan YOLO setiap N frame saja

        # ── Temporal smoothing buffer (anti jitter) ──────────────────────
        from collections import deque
        self._d_tray_history = deque(maxlen=7)  # Rolling window 7 frame

        # Pre-compute undistort maps for speed
        self._K = self.cfg["camera_matrix"]
        self._D = self.cfg["dist_coeffs"]
        self._map1 = None
        self._map2 = None

    def _init_undistort_maps(self, h, w):
        """Lazy-init undistort remap tables (sekali saja per resolusi)."""
        if self._map1 is None:
            new_K, _ = cv2.getOptimalNewCameraMatrix(
                self._K, self._D, (w, h), 1, (w, h)
            )
            self._map1, self._map2 = cv2.initUndistortRectifyMap(
                self._K, self._D, None, new_K, (w, h), cv2.CV_16SC2
            )

    def _undistort(self, frame):
        """Undistort frame menggunakan remap (lebih cepat dari cv2.undistort)."""
        h, w = frame.shape[:2]
        self._init_undistort_maps(h, w)
        return cv2.remap(frame, self._map1, self._map2,
                         cv2.INTER_LINEAR)

    def _create_tray_mask_from_bbox(self, bbox, frame_shape):
        """
        Buat mask binary dari bounding box tray.
        Digunakan jika YOLO tidak menyediakan segmentasi mask.
        """
        h, w = frame_shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        x1, y1, x2, y2 = bbox
        mask[y1:y2, x1:x2] = 255
        return mask

    def _run_yolo(self, frame):
        """
        Jalankan YOLO dan kategorikan deteksi menjadi tray dan glass.

        Returns:
            (tray_bbox, tray_mask, glass_bbox)
        """
        boxes = self.detector.detect(frame)
        h, w = frame.shape[:2]

        tray_bbox = None
        glass_bbox = None
        tray_mask = None

        if not boxes:
            return None, None, None

        # Heuristik: 
        # Jika ada > 1 deteksi: terbesar = tray, kedua = glass
        # Jika hanya ada 1 deteksi (karena modelnya adalah cup_detector): deteksi = glass, tray = full frame
        sorted_boxes = sorted(boxes,
                              key=lambda b: (b["bbox"][2] - b["bbox"][0]) *
                                            (b["bbox"][3] - b["bbox"][1]),
                              reverse=True)

        if len(sorted_boxes) == 1:
            # Hanya deteksi cup
            glass_bbox = sorted_boxes[0]["bbox"]
            tray_bbox = (0, 0, w, h)
        elif len(sorted_boxes) > 1:
            tray_bbox = sorted_boxes[0]["bbox"]
            glass_bbox = sorted_boxes[1]["bbox"]

        if tray_bbox is not None:
            tray_mask = self._create_tray_mask_from_bbox(tray_bbox,
                                                          frame.shape)

        return tray_bbox, tray_mask, glass_bbox

    def process_frame(self, frame):
        """
        Proses satu frame dan hasilkan estimasi D_tray_cm.

        Args:
            frame: image BGR (np.ndarray)

        Returns:
            dict sesuai output schema:
                D_tray_cm, method_used, confidence, status,
                D_left_cm, D_right_cm, lines_left, lines_right, notes
        """
        cfg = self.cfg
        h, w = frame.shape[:2]

        # ── 1. Undistort ─────────────────────────────────────────────────
        frame_u = self._undistort(frame)

        # ── 2. Deteksi ROI ───────────────────────────────────────────────
        if self.no_yolo:
            # No-YOLO mode: gunakan seluruh frame sebagai tray
            tray_bbox = (0, 0, w, h)
            tray_mask = np.ones((h, w), dtype=np.uint8) * 255
            glass_bbox = None
        else:
            # YOLO caching: hanya jalankan YOLO setiap N frame
            self._frame_count += 1
            if self._frame_count % self.yolo_interval == 1 or self._cached_yolo[0] is None:
                tray_bbox, tray_mask, glass_bbox = self._run_yolo(frame_u)
                self._cached_yolo = (tray_bbox, tray_mask, glass_bbox)
            else:
                tray_bbox, tray_mask, glass_bbox = self._cached_yolo
                # Regenerasi tray_mask jika ukuran frame berubah
                if tray_mask is not None and tray_mask.shape[:2] != (h, w):
                    tray_mask = np.ones((h, w), dtype=np.uint8) * 255

            if tray_bbox is None:
                return {
                    "D_tray_cm": None,
                    "method_used": "NONE",
                    "confidence": 0.0,
                    "status": "INSUFFICIENT_DATA",
                    "D_left_cm": None, "D_right_cm": None,
                    "lines_left": 0, "lines_right": 0,
                    "notes": "YOLO tidak mendeteksi tray",
                }

        # ── 3. Jalankan metode sesuai pilihan ────────────────────────────
        m = self.method
        result_a, result_b, result_c = None, None, None

        if m in ("AUTO", "B"):
            result_b = estimate_D_tray_method_B(
                frame=frame_u,
                tray_mask=tray_mask,
                glass_bbox=glass_bbox,
                f_pixel=cfg["f_pixel"],
                P_real_cm=cfg["P_real_cm"],
                theta_tilt_rad=cfg["theta_tilt_rad"],
                canny_low=cfg["canny_low"],
                canny_high=cfg["canny_high"],
                hough_threshold=cfg["hough_threshold"],
                hough_min_line_length=cfg["hough_min_line_length"],
                hough_max_line_gap=cfg["hough_max_line_gap"],
                angle_tol_deg=cfg["horizontal_angle_tol_deg"],
                min_lines=cfg["min_lines_per_zone"],
                D_min=cfg["D_min_cm"],
                D_max=cfg["D_max_cm"],
            )

        if m in ("AUTO", "C"):
            result_c = estimate_D_tray_method_C(
                tray_mask=tray_mask,
                K=cfg["camera_matrix"],
                dist_coeffs=cfg["dist_coeffs"],
                W_tray_cm=cfg["W_tray_cm"],
                L_tray_cm=cfg["L_tray_cm"],
                theta_tilt_rad=cfg["theta_tilt_rad"],
                D_min=cfg["D_min_cm"],
                D_max=cfg["D_max_cm"],
            )

        if m in ("AUTO", "A"):
            result_a = estimate_D_tray_method_A(
                bbox=tray_bbox,
                f_pixel=cfg["f_pixel"],
                W_real_cm=cfg["W_tray_cm"],
                theta_tilt_rad=cfg["theta_tilt_rad"],
                frame_width=w,
                D_min=cfg["D_min_cm"],
                D_max=cfg["D_max_cm"],
            )

        # ── 4. Fusi atau single-method output ────────────────────────────
        if m == "AUTO":
            fused = fuse_results(result_a, result_b, result_c)
        else:
            # Single method — langsung pakai hasilnya
            single = {"A": result_a, "B": result_b, "C": result_c}[m]
            if single and single.get("D_tray_cm") is not None:
                fused = {
                    "D_tray_cm": single["D_tray_cm"],
                    "method_used": m,
                    "confidence": single.get("confidence", 0),
                    "status": single.get("status", "OK"),
                    "D_left_cm": single.get("D_left_cm"),
                    "D_right_cm": single.get("D_right_cm"),
                    "lines_left": single.get("lines_left", 0),
                    "lines_right": single.get("lines_right", 0),
                    "notes": single.get("notes"),
                }
            else:
                fused = {
                    "D_tray_cm": None,
                    "method_used": m,
                    "confidence": 0.0,
                    "status": single.get("status", "INSUFFICIENT_DATA") if single else "INSUFFICIENT_DATA",
                    "D_left_cm": None, "D_right_cm": None,
                    "lines_left": single.get("lines_left", 0) if single else 0,
                    "lines_right": single.get("lines_right", 0) if single else 0,
                    "notes": single.get("notes") if single else f"Metode {m} gagal",
                }

        # Simpan detail per metode untuk debugging
        fused["_detail"] = {
            "method_a": result_a,
            "method_b": result_b,
            "method_c": result_c,
            "tray_bbox": tray_bbox,
            "glass_bbox": glass_bbox,
        }
        # ── Temporal Smoothing (anti jitter untuk live cam) ────────────────
        raw_d = fused.get("D_tray_cm")
        if raw_d is not None:
            self._d_tray_history.append(raw_d)
            if len(self._d_tray_history) >= 3:
                import numpy as _np
                smoothed = float(_np.median(list(self._d_tray_history)))
                fused["D_tray_cm"] = round(smoothed, 1)

        return fused

    def annotate_frame(self, frame, result):
        """
        Buat annotated copy dari frame dengan overlay visualisasi.

        Args:
            frame: frame BGR original
            result: dict output dari process_frame()

        Returns:
            frame BGR dengan annotasi
        """
        vis = frame.copy()
        h, w = vis.shape[:2]
        detail = result.get("_detail", {})

        # ── Tray bounding box ────────────────────────────────────────────
        tray_bbox = detail.get("tray_bbox")
        if tray_bbox:
            x1, y1, x2, y2 = tray_bbox
            cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 200, 0), 2)
            cv2.putText(vis, "TRAY", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)

        # ── Glass bounding box ───────────────────────────────────────────
        glass_bbox = detail.get("glass_bbox")
        if glass_bbox:
            gx1, gy1, gx2, gy2 = glass_bbox
            cv2.rectangle(vis, (gx1, gy1), (gx2, gy2), (0, 255, 255), 2)
            cv2.putText(vis, "GLASS", (gx1, gy1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # ── Hough Lines dari Metode B ────────────────────────────────────
        result_b = detail.get("method_b", {})
        if result_b and isinstance(result_b, dict):
            # Raw lines (abu-abu) dihilangkan agar tampilan lebih bersih
            # Data tetap tersimpan di result["_detail"] untuk analisis offline

            # Gambar clustered lines (hijau tebal) — satu per sekat
            clustered = result_b.get("debug_clustered", [])
            for i, line in enumerate(clustered):
                lx1, ly1, lx2, ly2 = line
                cv2.line(vis, (int(lx1), int(ly1)), (int(lx2), int(ly2)),
                         (0, 255, 0), 2)
                # Label nomor sekat
                cv2.putText(vis, f"#{i+1}", (int(lx1) - 25, int(ly1) + 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1)

            # Tampilkan jarak antar sekat (clustered gaps) di sisi kanan
            if len(clustered) > 1:
                y_mids = sorted([(l[1] + l[3]) / 2.0 for l in clustered])
                for i in range(len(y_mids) - 1):
                    gap = y_mids[i + 1] - y_mids[i]
                    mid_y = int((y_mids[i] + y_mids[i + 1]) / 2)
                    # Garis penghubung vertikal
                    cv2.line(vis, (w - 50, int(y_mids[i])),
                             (w - 50, int(y_mids[i + 1])), (0, 200, 255), 1)
                    # Titik ujung
                    cv2.circle(vis, (w - 50, int(y_mids[i])), 3, (0, 200, 255), -1)
                    cv2.circle(vis, (w - 50, int(y_mids[i + 1])), 3, (0, 200, 255), -1)
                    # Label gap
                    cv2.putText(vis, f"{gap:.1f}px", (w - 48, mid_y + 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                                (0, 200, 255), 1)

        # ── Corners dari Metode C ────────────────────────────────────────
        result_c = detail.get("method_c", {})
        if result_c and isinstance(result_c, dict):
            corners = result_c.get("corners", [])
            for pt in corners:
                cx, cy = int(pt[0]), int(pt[1])
                cv2.circle(vis, (cx, cy), 6, (255, 0, 255), -1)

        # ── Overlay text: D_tray, method, confidence, status ─────────────
        y_offset = 30
        D = result.get("D_tray_cm")
        method = result.get("method_used", "?")
        conf = result.get("confidence", 0)
        status = result.get("status", "?")

        if D is not None:
            txt = f"D_tray: {D:.1f} cm"
            cv2.putText(vis, txt, (10, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        else:
            cv2.putText(vis, "D_tray: N/A", (10, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        y_offset += 30
        cv2.putText(vis, f"Method: {method} | Conf: {conf:.2f}",
                    (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (200, 200, 200), 1)
        
        y_offset += 25
        color = (0, 255, 0) if status == "OK" else (0, 165, 255)
        cv2.putText(vis, f"Status: {status}", (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)

        # ── Tambah info Left/Right D_tray & Slat Count ───────────────────
        dl = result.get("D_left_cm")
        dr = result.get("D_right_cm")
        ll = result.get("lines_left", 0)
        lr = result.get("lines_right", 0)
        
        y_offset += 25
        dl_str = f"{dl:.1f}" if dl else "N/A"
        dr_str = f"{dr:.1f}" if dr else "N/A"
        cv2.putText(vis, f"L: {dl_str}cm ({ll}s) | R: {dr_str}cm ({lr}s)", 
                    (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.55, 
                    (255, 255, 0), 1)

        # ── Notes ────────────────────────────────────────────────────────
        notes = result.get("notes")
        if notes:
            y_offset += 25
            cv2.putText(vis, notes[:80], (10, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 100, 255), 1)

        return vis
