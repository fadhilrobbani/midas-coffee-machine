"""
midas_volumecup/depth.py — MiDaS Depth Estimator with ONNX Runtime acceleration
==================================================================================
Backend: ONNX Runtime (default) → PyTorch fallback (jika ORT tidak tersedia).

Optimasi:
  1. ONNX Runtime CPU: ~350ms/frame vs PyTorch default ~5500ms (16× speedup).
  2. ROI-cropped inference: crop ke area gelas+ArUco sebelum MiDaS.
     Frame 2592×1944 → 256×256 = 10× downscale (detail rendah).
     ROI ~300×300 → 256×256 = detail jauh lebih tinggi per piksel.
  3. Bilateral post-processing: edge-aware smoothing (+20ms, SNR +20%).
  4. Thread optimization: torch.set_num_threads(8) untuk PyTorch fallback.
"""

import torch
import numpy as np
import cv2
import sys
import os

# Ensure we can import midas properly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from midas.model_loader import load_model


class MidasDepthEstimator:
    def __init__(self, weights_path="../weights/midas_v21_small_256.pt",
                 model_type="midas_v21_small_256",
                 use_onnx=True):
        """
        Parameters
        ----------
        weights_path : str
            Path ke file .pt PyTorch weights.
        model_type : str
            Tipe model MiDaS (default: midas_v21_small_256).
        use_onnx : bool
            Jika True, coba gunakan ONNX Runtime. Auto-export .onnx jika belum ada.
            Fallback ke PyTorch jika ONNX Runtime tidak terinstall.
        """
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._backend = "pytorch"  # default, akan diubah jika ONNX berhasil

        # Optimasi thread count untuk PyTorch CPU
        # Benchmark menunjukkan 8 threads optimal, default 4 menyebabkan contention
        if self.device.type == "cpu":
            n_threads = max(os.cpu_count() or 4, 8)
            torch.set_num_threads(n_threads)
            try:
                torch.set_num_interop_threads(1)
            except RuntimeError:
                pass  # Sudah di-set sebelumnya, aman untuk dilanjutkan

        print(f"Loading MiDaS model from {weights_path} onto {self.device}...")
        self.model, self.transform, self.net_w, self.net_h = load_model(
            self.device, weights_path, model_type, optimize=False, height=None, square=False
        )
        self.model.eval()

        # Temporal smoothing state
        self.prev_prediction = None
        self.ema_alpha = 0.4  # Balance between 40% new inference, 60% historical memory

        # ── ONNX Runtime setup ──────────────────────────────────────────────
        self._ort_session = None
        if use_onnx:
            onnx_path = weights_path.replace('.pt', '.onnx')
            self._try_init_onnx(onnx_path, weights_path)

        print(f"[MiDaS] Backend: {self._backend.upper()} | "
              f"Threads: {torch.get_num_threads()} | "
              f"Net: {self.net_w}×{self.net_h}")

    def _try_init_onnx(self, onnx_path, pt_path):
        """Coba inisialisasi ONNX Runtime. Auto-export jika belum ada."""
        try:
            import onnxruntime as ort
        except ImportError:
            print("[MiDaS] onnxruntime not installed → using PyTorch.")
            return

        # Auto-export dari PyTorch jika .onnx belum ada
        if not os.path.exists(onnx_path):
            print(f"[MiDaS] Exporting ONNX to {onnx_path}...")
            try:
                # Buat dummy input sesuai transform
                dummy_rgb = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
                inp = self.transform({"image": dummy_rgb.astype(np.float32) / 255.0})["image"]
                dummy_tensor = torch.from_numpy(inp).unsqueeze(0)
                torch.onnx.export(
                    self.model, dummy_tensor, onnx_path,
                    input_names=["input"], output_names=["output"],
                    opset_version=14,
                    dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
                )
                print(f"[MiDaS] ONNX exported: {os.path.getsize(onnx_path)/1024/1024:.1f} MB")
            except Exception as e:
                print(f"[MiDaS] ONNX export failed: {e} → using PyTorch.")
                return

        # Load ONNX session
        try:
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = max(os.cpu_count() or 4, 4)
            sess_opts.inter_op_num_threads = 1
            sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._ort_session = ort.InferenceSession(
                onnx_path, sess_opts, providers=["CPUExecutionProvider"]
            )
            self._backend = "onnx"
            print(f"[MiDaS] ONNX Runtime loaded successfully.")
        except Exception as e:
            print(f"[MiDaS] ONNX session init failed: {e} → using PyTorch.")
            self._ort_session = None

    # ── ROI Crop & Paste (static methods untuk testability) ──────────────

    @staticmethod
    def _crop_roi(frame: np.ndarray, roi_bbox: tuple, pad_pct: float = 0.2) -> np.ndarray:
        """
        Crop frame ke area ROI dengan padding.

        Parameters
        ----------
        frame : np.ndarray, shape (H, W, 3)
        roi_bbox : tuple (x1, y1, x2, y2)
        pad_pct : float
            Persentase padding relatif terhadap ukuran ROI.

        Returns
        -------
        np.ndarray, cropped region.
        """
        x1, y1, x2, y2 = roi_bbox
        h_frame, w_frame = frame.shape[:2]
        roi_w = x2 - x1
        roi_h = y2 - y1

        pad_x = int(roi_w * pad_pct)
        pad_y = int(roi_h * pad_pct)

        cx1 = max(0, x1 - pad_x)
        cy1 = max(0, y1 - pad_y)
        cx2 = min(w_frame, x2 + pad_x)
        cy2 = min(h_frame, y2 + pad_y)

        return frame[cy1:cy2, cx1:cx2].copy()

    @staticmethod
    def _paste_depth(depth_roi: np.ndarray, roi_bbox: tuple,
                     frame_shape: tuple, pad_pct: float = 0.0) -> np.ndarray:
        """
        Paste depth result dari ROI inference ke full-frame depth map.

        Parameters
        ----------
        depth_roi : np.ndarray, depth output dari ROI inference.
        roi_bbox : tuple (x1, y1, x2, y2), koordinat ROI di frame asli.
        frame_shape : tuple (H, W), shape frame asli.
        pad_pct : float, padding yang digunakan saat crop.

        Returns
        -------
        np.ndarray, full-frame depth map (area di luar ROI = 0).
        """
        h_full, w_full = frame_shape
        x1, y1, x2, y2 = roi_bbox
        roi_w = x2 - x1
        roi_h = y2 - y1

        pad_x = int(roi_w * pad_pct)
        pad_y = int(roi_h * pad_pct)

        # Koordinat crop di frame asli (sama dengan _crop_roi)
        cx1 = max(0, x1 - pad_x)
        cy1 = max(0, y1 - pad_y)
        cx2 = min(w_full, x2 + pad_x)
        cy2 = min(h_full, y2 + pad_y)

        target_h = cy2 - cy1
        target_w = cx2 - cx1

        # Resize depth_roi ke ukuran crop region
        depth_resized = cv2.resize(
            depth_roi, (target_w, target_h), interpolation=cv2.INTER_LINEAR
        )

        full_depth = np.zeros((h_full, w_full), dtype=np.float32)
        full_depth[cy1:cy2, cx1:cx2] = depth_resized
        return full_depth

    # ── Bilateral Post-Processing ────────────────────────────────────────

    @staticmethod
    def _bilateral_smooth(depth_map: np.ndarray) -> np.ndarray:
        """
        Edge-aware bilateral smoothing pada depth map.

        Mengurangi noise MiDaS tanpa merusak edge tajam (rim vs tray boundary).
        Hanya ~20ms overhead.

        Parameters
        ----------
        depth_map : np.ndarray float32, raw depth dari MiDaS.

        Returns
        -------
        np.ndarray float32, smoothed depth.
        """
        return cv2.bilateralFilter(depth_map, d=5, sigmaColor=50, sigmaSpace=50)

    # ── Core Inference ───────────────────────────────────────────────────

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """CLAHE + RGB conversion + MiDaS transform → numpy array."""
        # Apply CLAHE to the L channel of LAB color space
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        clahe_image = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)

        # Convert to RGB for MiDaS
        original_image_rgb = cv2.cvtColor(clahe_image, cv2.COLOR_BGR2RGB)
        img_input = self.transform({"image": original_image_rgb / 255.0})["image"]
        return img_input, original_image_rgb.shape[:2]

    def _infer_pytorch(self, img_input: np.ndarray, output_size: tuple) -> np.ndarray:
        """Run inference via PyTorch."""
        sample = torch.from_numpy(img_input).to(self.device).unsqueeze(0)
        with torch.no_grad():
            prediction = self.model.forward(sample)
            prediction = (
                torch.nn.functional.interpolate(
                    prediction.unsqueeze(1),
                    size=output_size,
                    mode="bicubic",
                    align_corners=False,
                )
                .squeeze()
                .cpu()
                .numpy()
            )
        return prediction

    def _infer_onnx(self, img_input: np.ndarray, output_size: tuple) -> np.ndarray:
        """Run inference via ONNX Runtime."""
        ort_input = img_input.astype(np.float32)[np.newaxis]
        raw_output = self._ort_session.run(None, {"input": ort_input})[0]
        # raw_output shape: (1, H_net, W_net) — squeeze batch dim
        raw_output = raw_output.squeeze()
        # Resize ke output_size (sama seperti bicubic interpolate di PyTorch)
        prediction = cv2.resize(
            raw_output, (output_size[1], output_size[0]),
            interpolation=cv2.INTER_CUBIC
        )
        return prediction

    def process(self, image, roi_bbox=None):
        """
        Jalankan MiDaS depth estimation pada frame.

        Parameters
        ----------
        image : np.ndarray, shape (H, W, 3) BGR.
        roi_bbox : tuple (x1, y1, x2, y2) or None.
            Jika diberikan, crop ke ROI sebelum inference → detail lebih tinggi.
            Output tetap full-frame depth map (area di luar ROI = 0).

        Returns
        -------
        np.ndarray float32, depth map shape (H, W).
        """
        pad_pct = 0.2

        # ── ROI crop (opsional) ──────────────────────────────────────────
        if roi_bbox is not None:
            cropped = self._crop_roi(image, roi_bbox, pad_pct=pad_pct)
            # Resize ROI ke ukuran standar agar MiDaS transform menghasilkan
            # dimensi konsisten (penting untuk ONNX fixed-shape compatibility).
            # Kualitas tetap tinggi karena ROI sudah fokus ke area kecil.
            std_h, std_w = 480, 640
            cropped_resized = cv2.resize(cropped, (std_w, std_h), interpolation=cv2.INTER_LINEAR)
            img_input, img_size = self._preprocess(cropped_resized)
        else:
            img_input, img_size = self._preprocess(image)

        # ── Inference (ONNX atau PyTorch) ────────────────────────────────
        if self._backend == "onnx" and self._ort_session is not None:
            prediction = self._infer_onnx(img_input, img_size)
        else:
            prediction = self._infer_pytorch(img_input, img_size)

        # ── Bilateral post-processing ────────────────────────────────────
        prediction = self._bilateral_smooth(prediction.astype(np.float32))

        # ── Paste kembali ke full-frame jika ROI mode ────────────────────
        if roi_bbox is not None:
            prediction = self._paste_depth(
                prediction, roi_bbox, image.shape[:2], pad_pct=pad_pct
            )

        # ── Global Temporal Smoothing Filter (Vectorized EMA) ────────────
        if self.prev_prediction is None or self.prev_prediction.shape != prediction.shape:
            self.prev_prediction = prediction
        else:
            prediction = (self.ema_alpha * prediction) + ((1.0 - self.ema_alpha) * self.prev_prediction)
            self.prev_prediction = prediction

        return prediction.astype(np.float32)

    def get_standardized_depth(self, depth_map):
        """ 
        Converts raw depth (disparity) to a standardized 0-1000 scale.
        Uses a fixed saturation point to ensure values are comparable across frames.
        """
        # We use a fixed scale factor. Higher = further distance.
        # MiDaS small typically produces values in the range 0-3000+
        # Using 2500 as a 'saturation' point for 1000 scale.
        SATURATION_POINT = 2500.0 
        scale = 1000.0 / SATURATION_POINT
        standardized = np.clip(depth_map * scale, 0, 1000).astype(np.float32)
        return standardized

    def get_tray_depth(self, depth_map, roi_coords):
        """ Average/Median depth in the tray region """
        # Ensure we are using standardized values if depth_map is raw disparity
        if depth_map.max() > 1000:
             depth_map = self.get_standardized_depth(depth_map)
             
        x1, y1, x2, y2 = roi_coords
        roi = depth_map[y1:y2, x1:x2]
        if roi.size == 0:
            return 0
        return float(np.median(roi))
        
    def get_rim_depth(self, depth_map, bbox):
        """ Median depth within a horizontal strip along the physical lip of the cup """
        # Ensure we are using standardized values if depth_map is raw disparity
        if depth_map.max() > 1000:
             depth_map = self.get_standardized_depth(depth_map)

        x1, y1, x2, y2 = bbox
        
        # We sample the physical ceramic rim (TOP edge of the bounding box)
        thickness_inward = max(4, (y2 - y1) // 10)
        
        # Take a wide horizontal strip across the cup
        px1 = max(x1, x1 + (x2 - x1) // 4)
        px2 = min(x2, x2 - (x2 - x1) // 4)
        
        # Sample the TOP rim, pushing 'thickness' pixels inward from the top edge (y1)
        py1 = y1
        py2 = min(y2, y1 + thickness_inward)
        
        patch = depth_map[py1:py2, px1:px2]
        if patch.size == 0:
            return 0
            
        # MiDaS outputs disparity (higher value = closer to camera). 
        # Using np.max finds the absolute highest peak (the rim itself) 
        # and naturally ignores the 'smudgery' or background/table pixels blending into the ROI.
        return float(np.max(patch))
