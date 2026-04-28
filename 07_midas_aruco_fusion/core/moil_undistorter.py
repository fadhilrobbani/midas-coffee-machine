"""
core/moil_undistorter.py — Wrapper Moildev fisheye undistortion dengan akselerasi OpenCL
==========================================================================================
Modul ini membungkus library Moildev (di ../moildev/) dan menyediakan
interface undistortion yang transparan untuk pipeline MiDaS+ArUco.

Filosofi:
  - Folder moildev/ TIDAK DISENTUH sama sekali (read-only dependency).
  - Jika OpenCL tersedia, map_x / map_y diupload ke cv2.UMat untuk
    akselerasi GPU terintegrasi (iGPU / ARM Mali / OpenCL device).
  - Jika OpenCL tidak tersedia, fallback ke CPU numpy biasa tanpa crash.
  - Matriks remap dihitung SEKALI saat inisiasi, lalu dipakai ulang
    di setiap frame → overhead per-frame minimum.

Dipanggil dari:
  run_fusion.py → hanya jika argumen --fisheye diberikan.
"""

import os
import sys
import json
import warnings

import cv2
import numpy as np

# ── Import Moildev dari folder sibling (../moildev/) ───────────────────────
_THIS_DIR    = os.path.dirname(os.path.abspath(__file__))
_MOIL_DIR    = os.path.abspath(os.path.join(_THIS_DIR, "..", "moildev"))

if _MOIL_DIR not in sys.path:
    sys.path.insert(0, _MOIL_DIR)

try:
    from Moildev import Moildev as _MoildevLib
except ImportError as _e:
    raise ImportError(
        f"[MoilUndistorter] Gagal import Moildev dari {_MOIL_DIR}.\n"
        f"Pastikan folder moildev/ sudah ada dan berisi Moildev.py.\n"
        f"Error asli: {_e}"
    )


class MoilUndistorter:
    """
    Wrapper Moildev untuk undistortion lensa fisheye secara real-time.

    Parameters
    ----------
    json_path : str
        Path absolut atau relatif ke camera_parameters.json.
    camera_name : str
        Nama profil kamera di dalam JSON (contoh: 'lrcp_imx586_240_17').
    pitch : float
        Rotasi pitch dalam derajat (default 0 = lurus ke tengah lensa).
    yaw : float
        Rotasi yaw dalam derajat (default 0).
    roll : float
        Rotasi roll dalam derajat (default 0).
    zoom : float
        Faktor zoom anypoint (default 2).
    use_opencl : bool
        Aktifkan akselerasi OpenCL jika tersedia (default True).
    frame_width : int
        Lebar resolusi stream aktual (default 640). Maps di-rescale ke ukuran ini.
    frame_height : int
        Tinggi resolusi stream aktual (default 480). Maps di-rescale ke ukuran ini.
    target_size : tuple | None
        Resize output ke (width, height) setelah remap. None = tidak diubah.

    Attributes
    ----------
    opencl_active : bool
        True jika OpenCL berhasil diaktifkan dan dipakai.
    adjusted_focal_length : float
        Perkiraan focal length baru berbasis parameter5 Moildev.
        Injeksikan ke aruco.camera_matrix setelah inisiasi.
    """

    def __init__(
        self,
        json_path: str,
        camera_name: str = "lrcp_imx586_240_17",
        pitch: float = 0.0,
        yaw: float = 0.0,
        roll: float = 0.0,
        zoom: float = 2.0,
        use_opencl: bool = True,
        frame_width: int = 640,
        frame_height: int = 480,
        target_size: tuple = None,
    ):
        self.camera_name   = camera_name
        self.pitch         = pitch
        self.yaw           = yaw
        self.roll          = roll
        self.zoom          = zoom
        self.frame_width   = frame_width
        self.frame_height  = frame_height
        self.target_size   = target_size
        self.opencl_active = False

        # ── Validasi json_path ──────────────────────────────────────────────
        if not os.path.isabs(json_path):
            json_path = os.path.join(_THIS_DIR, "..", json_path)
        json_path = os.path.abspath(json_path)

        if not os.path.exists(json_path):
            raise FileNotFoundError(
                f"[MoilUndistorter] camera_parameters.json tidak ditemukan: {json_path}"
            )

        # ── Validasi camera_name ada di JSON ───────────────────────────────
        with open(json_path, "r") as f:
            _params = json.load(f)
        if camera_name not in _params:
            available = [k for k in _params.keys()][:10]
            raise KeyError(
                f"[MoilUndistorter] camera_name '{camera_name}' tidak ditemukan di JSON.\n"
                f"Beberapa profil yang tersedia: {available} ..."
            )

        # ── Ekstraksi Parameter Kamera ──────────────────────────────────────
        cam_entry = _params[camera_name]
        
        # Simpan metadata asli sensor (untuk perhitungan focal length)
        self._parameter5   = float(cam_entry.get("parameter5", 0.0))
        self._calibRatio   = float(cam_entry.get("calibrationRatio", 1.0))
        self._image_width  = int(cam_entry.get("imageWidth", 8000))
        self._image_height = int(cam_entry.get("imageHeight", 6000))

        # Hitung skala antara sensor asli dan resolusi stream aktual
        scale_x = frame_width  / max(self._image_width,  1)
        scale_y = frame_height / max(self._image_height, 1)
        avg_scale = (scale_x + scale_y) / 2.0

        # ── Instansiasi Moildev Natively (Scaled) ───────────────────────────
        # DARIPADA: generate maps 8000x6000 lalu resize ke 640x480 (blur).
        # SEBAIKNYA: inisiasi Moildev dengan parameter yang sudah di-scale.
        # Maps akan langsung keluar di resolusi stream tanpa interpolation kedua.
        
        print(f"[MOIL] Native Init: {frame_width}x{frame_height} (scaled from {self._image_width}x{self._image_height})")
        
        self._moil = _MoildevLib(
            camera_name      = camera_name,
            camera_fov       = float(cam_entry.get("cameraFov", 220)),
            sensor_width     = float(cam_entry.get("cameraSensorWidth", 1.0)),
            sensor_height    = float(cam_entry.get("cameraSensorHeight", 1.0)),
            icx              = float(cam_entry.get("iCx", 4000)) * scale_x,
            icy              = float(cam_entry.get("iCy", 3000)) * scale_y,
            ratio            = float(cam_entry.get("ratio", 1.0)),
            image_width      = frame_width,
            image_height     = frame_height,
            calibration_ratio = float(cam_entry.get("calibrationRatio", 1.0)) * avg_scale,
            parameter_0      = float(cam_entry.get("parameter0", 0.0)),
            parameter_1      = float(cam_entry.get("parameter1", 0.0)),
            parameter_2      = float(cam_entry.get("parameter2", 0.0)),
            parameter_3      = float(cam_entry.get("parameter3", 0.0)),
            parameter_4      = float(cam_entry.get("parameter4", 0.0)),
            parameter_5      = float(cam_entry.get("parameter5", 0.0)),
        )

        # Generate maps langsung di resolusi stream
        map_x_np, map_y_np = self._moil.maps_anypoint_mode2(pitch, yaw, roll, zoom)
        self._map_x_cpu = map_x_np.astype(np.float32)
        self._map_y_cpu = map_y_np.astype(np.float32)

        # ── Aktifkan OpenCL jika diminta & tersedia ────────────────────────
        self._map_x = self._map_x_cpu
        self._map_y = self._map_y_cpu

        if use_opencl:
            try:
                if cv2.ocl.haveOpenCL():
                    cv2.ocl.setUseOpenCL(True)
                    # Upload map ke device memory
                    self._map_x = cv2.UMat(self._map_x_cpu)
                    self._map_y = cv2.UMat(self._map_y_cpu)
                    self.opencl_active = True
                    print("[MOIL] OpenCL aktif — remap akan diakselerasi oleh GPU/iGPU.")
                else:
                    print("[MOIL] OpenCL tidak tersedia di sistem ini. Fallback ke CPU.")
            except Exception as _ocl_err:
                warnings.warn(
                    f"[MOIL] Gagal mengaktifkan OpenCL: {_ocl_err}. Fallback ke CPU."
                )

        if not self.opencl_active:
            print("[MOIL] OpenCL: OFF — menggunakan CPU numpy.")

        print(f"[MOIL] Maps siap. Adjusted focal length ≈ {self.adjusted_focal_length:.1f} px")

    # ── Properti ────────────────────────────────────────────────────────────

    @property
    def adjusted_focal_length(self) -> float:
        """
        Estimasi focal length ekivalen piksel setelah koreksi Moildev.
        Menggunakan parameter5 dibagi calibrationRatio sebagai pendekatan.
        Gunakan nilai ini untuk meng-override aruco.camera_matrix[0,0] & [1,1].
        """
        if self._calibRatio > 0:
            return self._parameter5 / self._calibRatio
        return self._parameter5

    # ── Method Utama ────────────────────────────────────────────────────────

    def update_maps(
        self,
        pitch: float = None,
        yaw: float = None,
        roll: float = None,
        zoom: float = None,
    ) -> None:
        """
        Regenerasi remap maps secara real-time dengan parameter baru.
        Dipanggil oleh AnypointController saat user drag mouse.

        Parameters yang None akan menggunakan nilai saat ini.
        """
        if pitch is not None: self.pitch = max(-110.0, min(110.0, pitch))
        if yaw   is not None: self.yaw   = max(-110.0, min(110.0, yaw))
        if roll  is not None: self.roll  = max(-110.0, min(110.0, roll))
        if zoom  is not None: self.zoom  = max(1.0,   min(20.0,  zoom))

        # Generate maps (sudah native resolusi stream karena init scaled)
        map_x_np, map_y_np = self._moil.maps_anypoint_mode2(
            self.pitch, self.yaw, self.roll, self.zoom
        )
        self._map_x_cpu = map_x_np.astype(np.float32)
        self._map_y_cpu = map_y_np.astype(np.float32)
        if self.opencl_active:
            self._map_x = cv2.UMat(self._map_x_cpu)
            self._map_y = cv2.UMat(self._map_y_cpu)
        else:
            self._map_x = self._map_x_cpu
            self._map_y = self._map_y_cpu

    def undistort(self, frame: np.ndarray) -> np.ndarray:
        """
        Terapkan koreksi Moildev anypoint pada satu frame.

        Parameters
        ----------
        frame : np.ndarray
            Frame BGR dari cv2.VideoCapture(), shape (H, W, 3).

        Returns
        -------
        np.ndarray
            Frame BGR yang sudah terkoreksi, shape sama atau target_size.
        """
        if frame is None:
            return frame

        # Jika OpenCL aktif, upload frame ke UMat
        if self.opencl_active:
            frame_in = cv2.UMat(frame)
        else:
            frame_in = frame

        remapped = cv2.remap(
            frame_in,
            self._map_x,
            self._map_y,
            interpolation=cv2.INTER_CUBIC, # Lebih tajam dari LINEAR
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

        # Download kembali ke numpy jika pakai UMat
        if self.opencl_active:
            remapped = remapped.get()

        # Resize jika target_size dispesifikasi
        if self.target_size is not None:
            remapped = cv2.resize(remapped, self.target_size, interpolation=cv2.INTER_LINEAR)

        return remapped

    def build_aruco_camera_matrix(
        self,
        frame_width: int,
        frame_height: int,
    ) -> np.ndarray:
        """
        Buat camera matrix 3×3 untuk ArUco berdasarkan adjusted_focal_length
        dan pusat gambar yang disesuaikan dengan resolusi streaming.

        Parameters
        ----------
        frame_width, frame_height : int
            Resolusi aktual frame streaming (bukan resolusi sensor penuh).

        Returns
        -------
        np.ndarray shape (3,3)
            Camera matrix K yang siap diinjeksikan ke aruco.camera_matrix.
        """
        # Hitung skala rasio antara resolusi streaming dan resolusi sensor JSON
        scale_x = frame_width  / max(self._image_width,  1)
        scale_y = frame_height / max(self._image_height, 1)
        scale   = (scale_x + scale_y) / 2.0

        fl   = self.adjusted_focal_length * scale
        cx   = frame_width  / 2.0
        cy   = frame_height / 2.0

        K = np.array([
            [fl,  0., cx],
            [0.,  fl, cy],
            [0.,  0.,  1.],
        ], dtype=np.float64)

        return K

    def __repr__(self) -> str:
        return (
            f"MoilUndistorter(camera='{self.camera_name}', "
            f"pitch={self.pitch}, yaw={self.yaw}, roll={self.roll}, zoom={self.zoom}, "
            f"opencl={self.opencl_active})"
        )
