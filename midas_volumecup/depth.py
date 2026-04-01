import torch
import numpy as np
import cv2
import sys
import os

# Ensure we can import midas properly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from midas.model_loader import load_model

class MidasDepthEstimator:
    def __init__(self, weights_path="weights/midas_v21_small_256.pt", model_type="midas_v21_small_256"):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Loading MiDaS model from {weights_path} onto {self.device}...")
        self.model, self.transform, self.net_w, self.net_h = load_model(
            self.device, weights_path, model_type, optimize=False, height=None, square=False
        )
        self.model.eval()
        
        # Temporal smoothing state
        self.prev_prediction = None
        self.ema_alpha = 0.4  # Balance between 40% new inference, 60% historical memory

    def process(self, image):
        # 1. Apply CLAHE to the L channel of LAB color space to scientifically safely stabilize room lighting
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        clahe_image = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
        
        # 2. Convert to RGB for MiDaS
        original_image_rgb = cv2.cvtColor(clahe_image, cv2.COLOR_BGR2RGB)
        img_input = self.transform({"image": original_image_rgb / 255.0})["image"]
        sample = torch.from_numpy(img_input).to(self.device).unsqueeze(0)
        
        with torch.no_grad():
            prediction = self.model.forward(sample)
            prediction = (
                torch.nn.functional.interpolate(
                    prediction.unsqueeze(1),
                    size=original_image_rgb.shape[:2],
                    mode="bicubic",
                    align_corners=False,
                )
                .squeeze()
                .cpu()
                .numpy()
            )
            
        # Global Temporal Smoothing Filter (Vectorized EMA)
        if self.prev_prediction is None or self.prev_prediction.shape != prediction.shape:
            self.prev_prediction = prediction
        else:
            prediction = (self.ema_alpha * prediction) + ((1.0 - self.ema_alpha) * self.prev_prediction)
            self.prev_prediction = prediction
            
        return prediction.astype(np.float32)

    def get_tray_depth(self, depth_map, roi_coords):
        """ Average/Median depth in the tray region """
        x1, y1, x2, y2 = roi_coords
        roi = depth_map[y1:y2, x1:x2]
        if roi.size == 0:
            return 0
        return float(np.median(roi))
        
    def get_rim_depth(self, depth_map, bbox):
        """ Median depth within a horizontal strip along the physical lip of the cup """
        x1, y1, x2, y2 = bbox
        
        # We sample the physical ceramic lip (just inside the bottom edge of the bounding box)
        thickness_inward = max(4, (y2 - y1) // 10)
        
        # Take a wide horizontal strip across the cup rather than a tiny center dot
        px1 = max(x1, x1 + (x2 - x1) // 4)
        px2 = min(x2, x2 - (x2 - x1) // 4)
        
        # Sample just the bottom lip, pushing exactly 'thickness' pixels inward from the YOLO edge
        py1 = max(y1, y2 - thickness_inward)
        py2 = y2
        
        patch = depth_map[py1:py2, px1:px2]
        if patch.size == 0:
            return 0
        return float(np.median(patch))
