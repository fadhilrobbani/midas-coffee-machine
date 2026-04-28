import torch
import os
import sys

class YoloDetector:
    def __init__(self, weights_path="../weights/cup_detection_v3_12_s_best.pt"):
        print(f"Loading YOLO model from {weights_path}...")
        self.is_ultralytics = False
        try:
            # Try loading via Ultralytics (YOLOv8)
            from ultralytics import YOLO
            self.model = YOLO(weights_path)
            self.is_ultralytics = True
            print("Successfully loaded via Ultralytics (YOLOv8).")
        except ImportError:
            print("ultralytics module not found. Falling back to torch.hub YOLOv5...")
            # Fallback for YOLOv5
            curr_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            original_path = sys.path.copy()
            sys.path = [p for p in sys.path if p != '' and os.path.abspath(p) != curr_dir]
            local_utils = sys.modules.pop('utils', None)
            
            self.model = torch.hub.load('ultralytics/yolov5', 'custom', path=weights_path, force_reload=True)
            
            sys.path = original_path
            if local_utils:
                sys.modules['utils'] = local_utils

    def detect(self, frame, roi_ratio: float = 1.0):
        """ 
        Returns list of dicts: [{'bbox': (x1,y1,x2,y2), 'conf': float}] 
        Args:
            frame: BGR image
            roi_ratio: Rasio ROI tengah (0.0 - 1.0). 1.0 = full frame.
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

        boxes = []
        if self.is_ultralytics:
            # Optimize: use imgsz=320 to speed up inference on CPU
            results = self.model(detect_frame, verbose=False, imgsz=320)
            if len(results) > 0:
                for det in results[0].boxes:
                    cls_id = int(det.cls[0].item())
                    # Only return class 0 (cup rim)
                    if cls_id == 0:
                        x1, y1, x2, y2 = map(int, det.xyxy[0].tolist())
                        conf = float(det.conf[0].item())
                        
                        # Shift back to original coordinates
                        x1, x2 = x1 + dw, x2 + dw
                        y1, y2 = y1 + dh, y2 + dh
                        boxes.append({"bbox": (x1, y1, x2, y2), "conf": conf})
        else:
            results = self.model(detect_frame)
            df = results.pandas().xyxy[0]
            for _, row in df.iterrows():
                if int(row['class']) == 0:
                    x1, y1, x2, y2 = int(row['xmin']), int(row['ymin']), int(row['xmax']), int(row['ymax'])
                    
                    # Shift back to original coordinates
                    x1, x2 = x1 + dw, x2 + dw
                    y1, y2 = y1 + dh, y2 + dh
                    boxes.append({
                        "bbox": (x1, y1, x2, y2),
                        "conf": float(row['confidence'])
                    })
        
        # Sort by confidence descending
        return sorted(boxes, key=lambda b: b['conf'], reverse=True)
