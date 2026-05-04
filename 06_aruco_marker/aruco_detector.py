"""
aruco_detector.py — ArUco Marker Detector with Pose Estimation

Mendeteksi marker ArUco pada frame kamera dan menghitung:
  - Jarak (depth) dalam cm menggunakan solvePnP
  - Rotasi (euler angles) marker relatif terhadap kamera
  - 4 titik sudut marker (corners)

Menggunakan calibration_params.yml yang sudah ada di project root.
"""

import math
import os
import sys

import cv2
import numpy as np
import yaml

# Tambah core/ ke path untuk import image_preprocess
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FUSION_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..', '07_midas_aruco_fusion'))
if _FUSION_DIR not in sys.path:
    sys.path.insert(0, _FUSION_DIR)

try:
    from core.image_preprocess import enhance_for_detection as _enhance
    _HAS_PREPROCESS = True
except ImportError:
    _HAS_PREPROCESS = False

# ── Dictionary mapping ──────────────────────────────────────────────────
DICT_MAP = {
    "DICT_4X4_50":   cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100":  cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250":  cv2.aruco.DICT_4X4_250,
    "DICT_5X5_50":   cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100":  cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250":  cv2.aruco.DICT_5X5_250,
    "DICT_6X6_50":   cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100":  cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250":  cv2.aruco.DICT_6X6_250,
    "DICT_7X7_50":   cv2.aruco.DICT_7X7_50,
    "DICT_7X7_100":  cv2.aruco.DICT_7X7_100,
    "DICT_7X7_250":  cv2.aruco.DICT_7X7_250,
}


def load_camera_calibration(params_path=None):
    """
    Memuat parameter kalibrasi kamera dari calibration_params.yml.

    Returns:
        dict: camera_matrix (3x3), dist_coeffs (1x5), f_pixel (float)
    """
    if params_path is None:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        params_path = os.path.join(root_dir, "calibration_params.yml")

    if not os.path.isfile(params_path):
        raise FileNotFoundError(f"Calibration file not found: {params_path}")

    with open(params_path, "r") as f:
        data = yaml.safe_load(f)

    K = np.array(data["camera_matrix_left"], dtype=np.float64)
    D = np.array(data["dist_coeff_left"], dtype=np.float64).flatten()
    f_pixel = (K[0, 0] + K[1, 1]) / 2.0

    return {
        "camera_matrix": K,
        "dist_coeffs": D,
        "f_pixel": f_pixel,
    }


class ArucoDetector:
    """
    Detektor ArUco marker dengan pose estimation (jarak + orientasi).

    Alur kerja:
      1. detectMarkers() → cari semua marker di frame
      2. estimatePoseSingleMarkers() → hitung pose 3D tiap marker
      3. Ekstrak jarak (tvec[2]) dan rotasi (Rodrigues → Euler)

    Args:
        marker_size_cm: Ukuran fisik sisi marker (cm)
        dictionary_name: Nama dictionary ArUco (default: DICT_4X4_50)
        params_path: Path ke calibration_params.yml
    """

    def __init__(self, marker_size_cm=5.0, dictionary_name="DICT_4X4_50",
                 params_path=None):
        self.marker_size_cm = marker_size_cm

        # Load dictionary
        if dictionary_name not in DICT_MAP:
            raise ValueError(f"Dictionary tidak dikenal: {dictionary_name}")
        # Mendukung OpenCV 4.7+ (API baru) dan fallback ke API lama (< 4.7)
        if hasattr(cv2.aruco, 'getPredefinedDictionary'):
            self.aruco_dict = cv2.aruco.getPredefinedDictionary(DICT_MAP[dictionary_name])
        else:
            self.aruco_dict = cv2.aruco.Dictionary_get(DICT_MAP[dictionary_name])
        if hasattr(cv2.aruco, 'DetectorParameters') and callable(cv2.aruco.DetectorParameters):
            self.aruco_params = cv2.aruco.DetectorParameters()
        else:
            self.aruco_params = cv2.aruco.DetectorParameters_create()

        # Parameter max-tolerant untuk kondisi fisheye blur (sharpness ~88)
        # Terbukti mendeteksi marker pada brightness=45, sharpness=88 (kondisi live)
        # Parameter dioptimalkan untuk kecepatan (balanced)
        # Parameter sensitivitas tinggi untuk kondisi fisheye (kecil/blur)
        # Dioptimalkan agar tetap stabil pada resolusi 5MP (2592x1944)
        self.aruco_params.adaptiveThreshConstant        = 7      # Kembali ke 7 untuk mencegah false positive pada keyboard
        self.aruco_params.adaptiveThreshWinSizeMin      = 3
        self.aruco_params.adaptiveThreshWinSizeMax      = 53     
        self.aruco_params.adaptiveThreshWinSizeStep     = 10     
        self.aruco_params.minMarkerPerimeterRate        = 0.01   # Cegah deteksi noise berukuran mikroskopis
        self.aruco_params.maxMarkerPerimeterRate        = 4.0
        self.aruco_params.polygonalApproxAccuracyRate   = 0.15   # SANGAT PENTING: Toleransi tinggi untuk garis melengkung akibat distorsi fisheye di pinggir frame!
        self.aruco_params.errorCorrectionRate           = 0.8    # Lebih toleran terhadap noise/blur pada bit-pattern
        self.aruco_params.cornerRefinementMethod        = cv2.aruco.CORNER_REFINE_SUBPIX # Penting untuk akurasi jarak


        # Load kalibrasi kamera
        calib = load_camera_calibration(params_path)
        self.camera_matrix = calib["camera_matrix"]
        self.dist_coeffs = calib["dist_coeffs"]

        self.dictionary_name = dictionary_name
        print(f"[ARUCO] ✅ Detector initialized:")
        print(f"   Dictionary  : {dictionary_name}")
        print(f"   Marker size : {marker_size_cm} cm")
        print(f"   Focal length: {calib['f_pixel']:.1f} px")

    def detect(self, frame, use_enhancement: bool = True, roi_ratio: float = 1.0):
        """
        Deteksi semua ArUco marker pada frame dan hitung pose 3D-nya.

        Args:
            frame           : BGR image (numpy array)
            use_enhancement : Terapkan CLAHE + unsharp sebelum deteksi
                              (default True; matikan di headless/benchmark)
            roi_ratio       : Rasio ROI tengah (0.0 - 1.0). 
                              1.0 = full frame, 0.65 = ambil 65% area tengah.

        Returns:
            list of dict, masing-masing berisi:
                - id, corners, distance_cm, rvec, tvec, euler_deg, center,
                  reprojection_error
        """
        # ── ROI Strategy (The "Tunnel" Fix) ─────────────────────────────────
        h, w = frame.shape[:2]
        if roi_ratio < 1.0:
            roi_w = int(w * roi_ratio)
            roi_h = int(h * roi_ratio)
            dw = (w - roi_w) // 2
            dh = (h - roi_h) // 2
            detect_frame = frame[dh:dh+roi_h, dw:dw+roi_w]
        else:
            dw, dh = 0, 0
            detect_frame = frame

        # ── Strategi deteksi: Cepat & Sensitif ──────────────────────────────────
        # Konversi ke Grayscale
        gray = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2GRAY)

        # Gunakan UMat jika OpenCV mendukung OpenCL untuk deteksi yang lebih cepat
        try:
            u_gray = cv2.UMat(gray)
        except:
            u_gray = gray

        if hasattr(cv2.aruco, 'ArucoDetector'):
            detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
            corners, ids, rejected = detector.detectMarkers(u_gray)
        else:
            detector = None
            corners, ids, rejected = cv2.aruco.detectMarkers(
                u_gray, self.aruco_dict, parameters=self.aruco_params
            )

        # ── Cek apakah sudah ada hasil ────────────────────────────────────────
        def _is_empty(ids):
            if ids is None: return True
            ids_np = ids.get() if hasattr(ids, 'get') else ids
            return ids_np is None or len(ids_np) == 0

        # ── Fallback 1: CLAHE ringan (jika frame gelap/kurang kontras) ────────
        if _is_empty(ids) and _HAS_PREPROCESS:
            # Gunakan CLAHE via UMat agar cepat
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            u_gray_enh = clahe.apply(u_gray)
            
            if hasattr(cv2.aruco, 'ArucoDetector'):
                corners, ids, rejected = detector.detectMarkers(u_gray_enh)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(
                    u_gray_enh, self.aruco_dict, parameters=self.aruco_params
                )

        # ── Fallback 2: Histogram Equalization (jika terlalu pudar) ───────────
        if _is_empty(ids):
            u_gray_eq = cv2.equalizeHist(u_gray)
            if hasattr(cv2.aruco, 'ArucoDetector'):
                corners, ids, rejected = detector.detectMarkers(u_gray_eq)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(
                    u_gray_eq, self.aruco_dict, parameters=self.aruco_params
                )

        # Jika masih UMat, konversi balik ke numpy untuk pemrosesan koordinat
        if corners is not None and len(corners) > 0:
            if hasattr(corners[0], 'get'):
                corners = [c.get() for c in corners]
        if ids is not None:
            if hasattr(ids, 'get'):
                ids = ids.get()

        results = []

        if ids is None or len(ids) == 0:
            return results

        # ── Kembalikan koordinat ke ruang frame asli ──────────────────────────
        if dw > 0 or dh > 0:
            for i in range(len(corners)):
                corners[i][0][:, 0] += dw
                corners[i][0][:, 1] += dh


        # Estimate pose untuk setiap marker
        rvecs = []
        tvecs = []
        half = self.marker_size_cm / 2.0
        obj_pts = np.array([
            [-half,  half, 0],
            [ half,  half, 0],
            [ half, -half, 0],
            [-half, -half, 0]
        ], dtype=np.float32)
        
        for i in range(len(ids)):
            success, rv, tv = cv2.solvePnP(
                obj_pts, corners[i][0].astype(np.float32), 
                self.camera_matrix, self.dist_coeffs,
                flags=cv2.SOLVEPNP_IPPE_SQUARE
            )
            rvecs.append([rv.flatten() if rv is not None else np.zeros(3)])
            tvecs.append([tv.flatten() if tv is not None else np.zeros(3)])

        for i in range(len(ids)):
            marker_id = int(ids[i][0])
            corner_pts = corners[i][0]  # shape (4, 2)
            rvec = rvecs[i][0]          # shape (3,)
            tvec = tvecs[i][0]          # shape (3,)

            # ── Estimasi jarak ──────────────────────────────────────────────
            # Gunakan perimeter marker dalam piksel sebagai estimasi jarak.
            # Formula: Z = (marker_size_cm * fx) / side_length_px
            # Lebih robust dari tvec[2] karena tidak menganggap gambar pinhole.
            side_px = np.mean([
                np.linalg.norm(corner_pts[1] - corner_pts[0]),
                np.linalg.norm(corner_pts[2] - corner_pts[1]),
                np.linalg.norm(corner_pts[3] - corner_pts[2]),
                np.linalg.norm(corner_pts[0] - corner_pts[3]),
            ])
            fx = float(self.camera_matrix[0, 0])
            if side_px > 0:
                distance_cm = (self.marker_size_cm * fx) / side_px
            else:
                distance_cm = float(tvec[2])  # fallback


            # Titik tengah marker
            center_x = float(np.mean(corner_pts[:, 0]))
            center_y = float(np.mean(corner_pts[:, 1]))

            # Euler angles
            euler = self._rvec_to_euler(rvec)

            # Reprojection error
            reproj_err = self._compute_reprojection_error(corner_pts, rvec, tvec)

            results.append({
                "id": marker_id,
                "corners": corner_pts,
                "distance_cm": round(distance_cm, 2),
                "rvec": rvec,
                "tvec": tvec,
                "euler_deg": euler,
                "center": (center_x, center_y),
                "reprojection_error": round(reproj_err, 3),
            })

        return results

    def detect_with_fallback(
        self,
        frame: np.ndarray,
        max_scale: int = 4,
        use_enhancement: bool = True,
        roi_ratio: float = 1.0,
    ) -> list:
        """
        Deteksi ArUco dengan fallback multi-skala.

        Jika deteksi pada resolusi asli gagal (0 marker), coba upscale frame
        secara progressif (2x, 3x, ... max_scale) hingga marker terdeteksi.
        Koordinat corner dikembalikan ke ruang koordinat frame asli.

        Metode ini mengatasi keterbatasan ArUco detector pada marker kecil
        atau sedikit blur akibat fisheye undistortion.

        Args:
            frame          : BGR image (undistorted)
            max_scale      : Maksimum faktor upscale (default 4)
            use_enhancement: Terapkan CLAHE+unsharp sebelum deteksi
            roi_ratio      : Rasio ROI tengah (0.0 - 1.0).

        Returns:
            list of dict (sama seperti detect()), koordinat dalam frame asli.
        """
        # Coba deteksi pada resolusi asli terlebih dahulu
        results = self.detect(frame, use_enhancement=use_enhancement,
                              roi_ratio=roi_ratio)
        if results:
            return results

        # Fallback: upscale progressif
        h, w = frame.shape[:2]
        orig_k = self.camera_matrix.copy()

        for scale in range(2, max_scale + 1):
            upscaled = cv2.resize(frame, (w * scale, h * scale),
                                  interpolation=cv2.INTER_CUBIC)
            
            # PENTING: Skala Camera Matrix agar solvePnP akurat pada frame upscaled
            scaled_k = orig_k.copy()
            scaled_k[0, 0] *= scale  # fx
            scaled_k[1, 1] *= scale  # fy
            scaled_k[0, 2] *= scale  # cx
            scaled_k[1, 2] *= scale  # cy
            self.camera_matrix = scaled_k

            try:
                results_up = self.detect(upscaled, use_enhancement=use_enhancement,
                                         roi_ratio=roi_ratio)
            finally:
                # Selalu kembalikan camera matrix ke original
                self.camera_matrix = orig_k

            if results_up:
                # Konversi koordinat kembali ke ruang frame asli
                inv_scale = 1.0 / scale
                for r in results_up:
                    r['corners'] = r['corners'] * inv_scale
                    r['center'] = (r['center'][0] * inv_scale,
                                   r['center'][1] * inv_scale)
                    # tvec x,y tidak perlu di-scale manual karena solvePnP sudah pakai scaled_k
                    # Jarak (z) akan tetap konsisten karena perbandingan marker_size / side_px tetap.
                return results_up

        return []  # Tidak ditemukan di semua skala

    def annotate_frame(self, frame, results):
        """
        Menggambar overlay visualisasi pada frame.

        Args:
            frame: BGR image
            results: output dari detect()

        Returns:
            Annotated BGR image
        """
        annotated = frame.copy()

        if not results:
            cv2.putText(annotated, "No ArUco marker detected",
                        (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                        (0, 0, 255), 3)
            return annotated

        for r in results:
            corners = r["corners"].astype(int)

            # Gambar kotak cyan di sekeliling marker agar beda dengan YOLO (yang warna hijau)
            for j in range(4):
                pt1 = tuple(corners[j])
                pt2 = tuple(corners[(j + 1) % 4])
                cv2.line(annotated, pt1, pt2, (255, 255, 0), 4)

            # Gambar axis 3D
            cv2.drawFrameAxes(annotated, self.camera_matrix, self.dist_coeffs,
                               r["rvec"], r["tvec"], self.marker_size_cm * 0.5, 3)

            # Label: ID + Distance
            cx, cy = int(r["center"][0]), int(r["center"][1])
            label_id = f"ID:{r['id']}"
            label_dist = f"D:{r['distance_cm']:.1f}cm"
            label_err = f"err:{r['reprojection_error']:.2f}px"

            # Perbesar font dan offset
            cv2.putText(annotated, label_id,
                        (cx - 80, cy - 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 0), 3)
            cv2.putText(annotated, label_dist,
                        (cx - 80, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
            cv2.putText(annotated, label_err,
                        (cx - 80, cy + 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 200, 200), 2)

            # Euler angles di pojok
            euler = r["euler_deg"]
            euler_txt = (f"R:{euler['roll']:.0f} "
                         f"P:{euler['pitch']:.0f} "
                         f"Y:{euler['yaw']:.0f}")
            cv2.putText(annotated, euler_txt,
                        (cx - 120, cy + 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 255), 2)

        return annotated

    def _rvec_to_euler(self, rvec):
        """Konversi rotation vector ke euler angles (derajat)."""
        R, _ = cv2.Rodrigues(rvec)

        # Euler angles dari rotation matrix (ZYX convention)
        sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
        singular = sy < 1e-6

        if not singular:
            roll = math.atan2(R[2, 1], R[2, 2])
            pitch = math.atan2(-R[2, 0], sy)
            yaw = math.atan2(R[1, 0], R[0, 0])
        else:
            roll = math.atan2(-R[1, 2], R[1, 1])
            pitch = math.atan2(-R[2, 0], sy)
            yaw = 0

        return {
            "roll": round(math.degrees(roll), 1),
            "pitch": round(math.degrees(pitch), 1),
            "yaw": round(math.degrees(yaw), 1),
        }

    def _compute_reprojection_error(self, corners_2d, rvec, tvec):
        """Hitung reprojection error rata-rata."""
        half = self.marker_size_cm / 2.0
        obj_pts = np.array([
            [-half,  half, 0],
            [ half,  half, 0],
            [ half, -half, 0],
            [-half, -half, 0],
        ], dtype=np.float64)

        projected, _ = cv2.projectPoints(
            obj_pts, rvec, tvec,
            self.camera_matrix, self.dist_coeffs
        )
        projected = projected.reshape(-1, 2)

        errors = np.sqrt(np.sum((corners_2d - projected) ** 2, axis=1))
        return float(np.mean(errors))

    def get_best_distance(self, results, max_reproj_error=0.5):
        """
        Hitung jarak terbaik dari semua marker terdeteksi menggunakan MEDIAN
        setelah memfilter marker dengan reprojection error tinggi.

        Args:
            results: output dari detect()
            max_reproj_error: threshold reprojection error (piksel).
                              Marker dengan error > threshold akan ditolak.

        Returns:
            dict: {
                'distance_cm': float (median distance),
                'used_count': int (jumlah marker dipakai),
                'rejected_count': int (jumlah marker ditolak),
                'all_distances': list (semua jarak yang dipakai),
            }
            atau None jika tidak ada marker valid.
        """
        if not results:
            return None

        # Filter by reprojection error
        valid = [r for r in results if r["reprojection_error"] <= max_reproj_error]
        rejected_count = len(results) - len(valid)

        # Fallback: jika semua ditolak, pakai yang error-nya paling kecil
        if not valid:
            best = min(results, key=lambda r: r["reprojection_error"])
            return {
                "distance_cm": best["distance_cm"],
                "used_count": 1,
                "rejected_count": len(results) - 1,
                "all_distances": [best["distance_cm"]],
            }

        distances = [r["distance_cm"] for r in valid]
        median_dist = round(float(np.median(distances)), 2)

        return {
            "distance_cm": median_dist,
            "used_count": len(valid),
            "rejected_count": rejected_count,
            "all_distances": distances,
        }
