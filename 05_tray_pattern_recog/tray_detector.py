import cv2
import numpy as np
import os
import yaml
import sys

import argparse

# Dynamic root directory (one level up from this script's directory)
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from midas_volumecup.detector import YoloDetector
import glob

def load_calibration(params_path):
    """ Loads camera intrinsics for the right camera (index 2). """
    try:
        with open(params_path, 'r') as f:
            data = yaml.safe_load(f)
            # Right camera (index 2) matrix and dist coeffs
            K = np.array(data['camera_matrix_right'], dtype=np.float32)
            D = np.array(data['dist_coeff_right'], dtype=np.float32).flatten()
            return K, D
    except Exception as e:
        print(f"Error loading calibration: {e}")
        return None, None

def detect_tray_pattern(image_path, output_dir, detector, K, D):
    # Load image
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image {image_path}")
        return
    
    # 0. UNDISTORT first (Radial distortion correction)
    if K is not None and D is not None:
        # We can use getOptimalNewCameraMatrix for better coverage, but standard undistort is fine for now
        # h, w = img.shape[:2]
        # new_K, roi = cv2.getOptimalNewCameraMatrix(K, D, (w,h), 1, (w,h))
        img = cv2.undistort(img, K, D)

    display_img = img.copy()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    
    # 1. Detect cup to define dynamic ROIs
    boxes = detector.detect(img)
    
    # Define ROIs [x1, y1, x2, y2]
    # Fallback ROIs
    left_roi = [10, 150, 200, 350]
    right_roi = [440, 150, 630, 350]
    
    if boxes:
        cup_bbox = boxes[0]['bbox'] # (x1, y1, x2, y2)
        cx1, cy1, cx2, cy2 = cup_bbox
        # Draw cup bbox for reference
        cv2.rectangle(display_img, (cx1, cy1), (cx2, cy2), (0, 255, 255), 2)
        
        # New ROI Logic based on user's request:
        # - Vertical height Centered: 50% of cup width
        # - Lateral buffers: ~30% of cup width
        cup_w = cx2 - cx1
        cup_h = cy2 - cy1
        cy_center = (cy1 + cy2) // 2
        
        target_h = int(cup_w * 0.5)
        ry1 = max(0, cy_center - target_h // 2)
        ry2 = min(h, cy_center + target_h // 2)
        
        target_w = int(cup_w * 0.3)
        # Left ROI (clamped to cup left edge)
        left_roi = [max(0, cx1 - target_w), ry1, cx1 - 5, ry2]
        # Right ROI (clamped to cup right edge)
        right_roi = [cx2 + 5, ry1, min(w, cx2 + target_w), ry2]
    
    # Final check: skip if ROI is too small
    rois = []
    for r in [left_roi, right_roi]:
        if (r[2] - r[0]) > 5 and (r[3] - r[1]) > 5:
            rois.append(r)

    # Process each ROI with stricter filtering
    for roi in rois:
        rx1, ry1, rx2, ry2 = map(int, roi)
        cv2.rectangle(display_img, (rx1, ry1), (rx2, ry2), (255, 0, 0), 2)
        
        roi_gray = gray[ry1:ry2, rx1:rx2]
        # Equalize or enhance contrast for slats?
        # roi_gray = cv2.equalizeHist(roi_gray)
        roi_blurred = cv2.GaussianBlur(roi_gray, (5, 5), 0)
        
        # A. Line Detection (HoughLinesP) for slats
        # Stricter thresholds to reduce noise
        edges = cv2.Canny(roi_blurred, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=25, minLineLength=25, maxLineGap=12)
        
        valid_lines = []
        if lines is not None:
            for line in lines:
                lx1, ly1, lx2, ly2 = line[0]
                glx1, gly1 = lx1 + rx1, ly1 + ry1
                glx2, gly2 = lx2 + rx1, ly2 + ry1
                
                # Strict Horizontal Filter (±3 degrees)
                angle = abs(np.arctan2(gly2 - gly1, glx2 - glx1) * 180.0 / np.pi)
                if angle < 3 or angle > 177:
                    cv2.line(display_img, (glx1, gly1), (glx2, gly2), (0, 255, 0), 2)
                    valid_lines.append(((glx1, gly1), (glx2, gly2)))

        # B. Corner Detection (Restricted with lower count)
        # To reduce noise, only take clear corners
        corners = cv2.goodFeaturesToTrack(roi_blurred, maxCorners=25, qualityLevel=0.02, minDistance=10)
        if corners is not None:
            corners = np.intp(corners)
            for i in corners:
                cx, cy = i.ravel()
                cv2.circle(display_img, (int(cx + rx1), int(cy + ry1)), 3, (0, 0, 255), -1)

    # Save results
    base_name = os.path.basename(image_path)
    output_path = os.path.join(output_dir, f"v4_detected_{base_name}")
    cv2.imwrite(output_path, display_img)
    print(f"Results saved to: {output_path}")
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tray Pattern Detector")
    parser.add_argument("--image", type=str, help="Path to a single image file")
    parser.add_argument("--input_dir", type=str, help="Directory containing images to process")
    parser.add_argument("--output_dir", type=str, help="Directory to save results")
    parser.add_argument("--weights", type=str, help="Path to YOLO weights")
    parser.add_argument("--params", type=str, help="Path to calibration parameters YAML")
    
    args = parser.parse_args()

    # Defaults
    output_dir = args.output_dir if args.output_dir else os.path.join(root_dir, "05_tray_pattern_recog/results")
    params_file = args.params if args.params else os.path.join(root_dir, "calibration_params.yml")
    weights_path = args.weights if args.weights else os.path.join(root_dir, "weights/cup_detection_v3_12_s_best.pt")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    K, D = load_calibration(params_file)
    detector = YoloDetector(weights_path=weights_path)

    if args.image:
        # Process single image
        detect_tray_pattern(args.image, output_dir, detector, K, D)
    else:
        # Process directory (default or specified)
        snapshots_dir = args.input_dir if args.input_dir else os.path.join(root_dir, "01_calibration/calibration_snapshots")
        if os.path.exists(snapshots_dir):
            snapshots = [f for f in os.listdir(snapshots_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            for snapshot in snapshots:
                image_path = os.path.join(snapshots_dir, snapshot)
                detect_tray_pattern(image_path, output_dir, detector, K, D)
        else:
            print(f"Error: Input directory {snapshots_dir} does not exist.")
