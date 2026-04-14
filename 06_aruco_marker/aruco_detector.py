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

import cv2
import numpy as np
import yaml

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
        self.aruco_dict = cv2.aruco.Dictionary_get(DICT_MAP[dictionary_name])
        self.aruco_params = cv2.aruco.DetectorParameters_create()

        # Optimasi parameter deteksi untuk kondisi mesin kopi
        self.aruco_params.adaptiveThreshConstant = 7
        self.aruco_params.adaptiveThreshWinSizeMin = 3
        self.aruco_params.adaptiveThreshWinSizeMax = 23
        self.aruco_params.adaptiveThreshWinSizeStep = 10
        self.aruco_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.aruco_params.cornerRefinementWinSize = 5
        self.aruco_params.cornerRefinementMaxIterations = 30
        self.aruco_params.cornerRefinementMinAccuracy = 0.1

        # Load kalibrasi kamera
        calib = load_camera_calibration(params_path)
        self.camera_matrix = calib["camera_matrix"]
        self.dist_coeffs = calib["dist_coeffs"]

        self.dictionary_name = dictionary_name
        print(f"[ARUCO] ✅ Detector initialized:")
        print(f"   Dictionary  : {dictionary_name}")
        print(f"   Marker size : {marker_size_cm} cm")
        print(f"   Focal length: {calib['f_pixel']:.1f} px")

    def detect(self, frame):
        """
        Deteksi semua ArUco marker pada frame dan hitung pose 3D-nya.

        Args:
            frame: BGR image (numpy array)

        Returns:
            list of dict, masing-masing berisi:
                - id: int (marker ID)
                - corners: ndarray (4, 2) — 4 sudut marker dalam piksel
                - distance_cm: float — jarak kamera ke marker
                - rvec: ndarray (3,) — rotation vector
                - tvec: ndarray (3,) — translation vector (x, y, z cm)
                - euler_deg: dict — {'roll', 'pitch', 'yaw'} dalam derajat
                - center: tuple (x, y) — titik tengah marker
                - reprojection_error: float — error reprojeksi (piksel)
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        corners, ids, rejected = cv2.aruco.detectMarkers(
            gray, self.aruco_dict, parameters=self.aruco_params
        )

        results = []

        if ids is None or len(ids) == 0:
            return results

        # Estimate pose untuk setiap marker
        rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
            corners, self.marker_size_cm,
            self.camera_matrix, self.dist_coeffs
        )

        for i in range(len(ids)):
            marker_id = int(ids[i][0])
            corner_pts = corners[i][0]  # shape (4, 2)
            rvec = rvecs[i][0]          # shape (3,)
            tvec = tvecs[i][0]          # shape (3,)

            # Jarak = |tvec| (euclidean) atau tvec[2] (depth Z)
            distance_cm = float(tvec[2])

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
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 0, 255), 2)
            return annotated

        for r in results:
            corners = r["corners"].astype(int)

            # Gambar kotak hijau di sekeliling marker
            for j in range(4):
                pt1 = tuple(corners[j])
                pt2 = tuple(corners[(j + 1) % 4])
                cv2.line(annotated, pt1, pt2, (0, 255, 0), 2)

            # Gambar axis 3D
            cv2.drawFrameAxes(annotated, self.camera_matrix, self.dist_coeffs,
                               r["rvec"], r["tvec"], self.marker_size_cm * 0.5)

            # Label: ID + Distance
            cx, cy = int(r["center"][0]), int(r["center"][1])
            label_id = f"ID:{r['id']}"
            label_dist = f"D:{r['distance_cm']:.1f}cm"
            label_err = f"err:{r['reprojection_error']:.2f}px"

            cv2.putText(annotated, label_id,
                        (cx - 40, cy - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            cv2.putText(annotated, label_dist,
                        (cx - 40, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(annotated, label_err,
                        (cx - 40, cy + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            # Euler angles di pojok
            euler = r["euler_deg"]
            euler_txt = (f"R:{euler['roll']:.0f} "
                         f"P:{euler['pitch']:.0f} "
                         f"Y:{euler['yaw']:.0f}")
            cv2.putText(annotated, euler_txt,
                        (cx - 60, cy + 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 255), 1)

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
