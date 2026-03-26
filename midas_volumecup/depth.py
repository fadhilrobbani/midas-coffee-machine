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

    def process(self, image):
        # Convert BGR to RGB for MiDaS
        original_image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
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
        return prediction

    def get_tray_depth(self, depth_map, roi_coords):
        """ Average/Median depth in the tray region """
        x1, y1, x2, y2 = roi_coords
        roi = depth_map[y1:y2, x1:x2]
        if roi.size == 0:
            return 0
        return float(np.median(roi))
        
    def get_rim_depth(self, depth_map, bbox):
        """ Median depth within a small patch in the center of the bounding box """
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        
        patch_size = 10
        px1 = max(x1, cx - patch_size)
        px2 = min(x2, cx + patch_size)
        py1 = max(y1, cy - patch_size)
        py2 = min(y2, cy + patch_size)
        
        patch = depth_map[py1:py2, px1:px2]
        if patch.size == 0:
            return 0
        return float(np.median(patch))
