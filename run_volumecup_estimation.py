import os
import cv2
import numpy as np
import torch
import yaml
import time
from midas.model_loader import default_models, load_model
import utils

# Suppress Wayland error on some Linux distributions
os.environ['QT_QPA_PLATFORM'] = 'xcb'

def load_calibration_params(filepath='calibration_params.yml'):
    if not os.path.exists(filepath):
        print(f"Calibration file {filepath} not found. Please run the calibration GUI first.")
        return None
    with open(filepath, 'r') as stream:
        params = yaml.safe_load(stream)
    
    # Convert lists back to numpy arrays
    params['camera_matrix_left'] = np.array(params['camera_matrix_left'])
    params['dist_coeff_left'] = np.array(params['dist_coeff_left'])
    params['camera_matrix_right'] = np.array(params['camera_matrix_right'])
    params['dist_coeff_right'] = np.array(params['dist_coeff_right'])
    params['R'] = np.array(params['R'])
    params['T'] = np.array(params['T'])
    return params

def load_yolo_model(weights_path):
    import sys
    import os
    if not os.path.exists(weights_path):
        print(f"YOLO weights not found at {weights_path}")
        return None
    try:
        # Prevent YOLOv5 from loading the local 'utils.py'
        curr_dir = os.path.abspath(os.path.dirname(__file__))
        original_path = sys.path.copy()
        # Remove empty strings and current dir from sys.path
        sys.path = [p for p in sys.path if p != '' and os.path.abspath(p) != curr_dir]
        
        # Remove cached 'utils' module if it was already loaded globally
        local_utils = None
        if 'utils' in sys.modules:
            local_utils = sys.modules.pop('utils')

        # Load YOLO
        model = torch.hub.load('ultralytics/yolov5', 'custom', path=weights_path, force_reload=True)
        
        # Clean up global state
        sys.path = original_path
        if local_utils:
            sys.modules['utils'] = local_utils
            
        return model
    except Exception as e:
        print(f"Failed to load YOLO model: {e}")
        return None

def process_midas(device, model, transform, image, net_w, net_h):
    # Normalize and convert image for MiDaS
    original_image_rgb = np.flip(image, 2)  # BGR to RGB
    img_input = transform({"image": original_image_rgb / 255.0})["image"]
    sample = torch.from_numpy(img_input).to(device).unsqueeze(0)
    
    with torch.no_grad():
        prediction = model.forward(sample)
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

def main():
    # 1. Load Calibration Parameters
    calib = load_calibration_params()
    if calib is None:
        return
    
    mtx_l = calib['camera_matrix_left']
    dist_l = calib['dist_coeff_left']
    focal_length_x = mtx_l[0, 0] # fx for left camera

    # 2. Setup Stereo Matching (SGBM)
    stereo = cv2.StereoSGBM_create(
        minDisparity=0,
        numDisparities=16*5, # Must be divisible by 16
        blockSize=5,
        P1=8 * 3 * 5**2,
        P2=32 * 3 * 5**2,
        disp12MaxDiff=1,
        uniquenessRatio=15,
        speckleWindowSize=0,
        speckleRange=2,
        preFilterCap=63,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY
    )

    baseline = np.linalg.norm(calib['T']) # Baseline distance in metric units

    # 3. Load Models (MiDaS and YOLO)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    midas_type = "midas_v21_small_256"
    midas_weights = default_models[midas_type]
    print(f"Loading MiDaS: {midas_type}")
    midas_model, transform, net_w, net_h = load_model(device, midas_weights, midas_type, False, None, False)

    yolo_weights = "weights/cup_detection_v3_12_s_best.pt"
    print(f"Loading YOLO: {yolo_weights}")
    yolo_model = load_yolo_model(yolo_weights)
    if yolo_model is None:
        print("Continuing without YOLO. Will not calculate volume automatically.")

    # 4. Connect to Cameras
    left_idx = calib.get('camera_index_left', 0)
    right_idx = calib.get('camera_index_right', 1)
    
    print(f"Connecting to Left Camera ({left_idx}) and Right Camera ({right_idx})...")
    cap_left = cv2.VideoCapture(left_idx)
    cap_right = cv2.VideoCapture(right_idx)

    if not cap_left.isOpened() or not cap_right.isOpened():
        print("Error: Could not open one or both stereo cameras.")
        return

    print("Starting Main Loop... Press ESC to quit.")

    while True:
        ret_l, frame_l = cap_left.read()
        ret_r, frame_r = cap_right.read()

        if not ret_l or not ret_r:
            break

        # A. Rectify Images (Optional but recommended for precise stereo)
        # Assuming simple undistort for now, full rectification requires stereoRectify outputs
        frame_l_undistorted = cv2.undistort(frame_l, mtx_l, dist_l)
        
        # B. Get YOLO Bounding Box
        bbox = None
        if yolo_model:
            results = yolo_model(frame_l_undistorted)
            df = results.pandas().xyxy[0]
            if not df.empty:
                # Get the highest confidence cup
                best_det = df.iloc[0]
                bbox = (int(best_det['xmin']), int(best_det['ymin']), int(best_det['xmax']), int(best_det['ymax']))
        
        # C. Get Relative MiDaS Depth
        midas_depth = process_midas(device, midas_model, transform, frame_l_undistorted, net_w, net_h)
        
        # Normalize MiDaS for visualization
        depth_min = midas_depth.min()
        depth_max = midas_depth.max()
        midas_vis = 255 * (midas_depth - depth_min) / (depth_max - depth_min)
        midas_vis = cv2.applyColorMap(np.uint8(midas_vis), cv2.COLORMAP_INFERNO)

        # D. Get Sparse Metric Depth from Stereo (Simplified mapping)
        # Note: True stereo fusion requires aligning disparity and MiDaS mathematically.
        # Here we simulate the extraction logic for Phase 5.
        
        volume_text = "Volume: N/A"
        if bbox is not None:
            xmin, ymin, xmax, ymax = bbox
            cv2.rectangle(frame_l_undistorted, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
            
            # --- Phase 5 Logic ---
            # 1. Pixel Diameter -> Longest side
            width = xmax - xmin
            height = ymax - ymin
            diameter_px = max(width, height)
            r_px = diameter_px / 2.0
            
            # 2. Sample Depth (Relative for now in this skeleton script)
            # In a fully fused map, these would be absolute cm/mm
            rim_depth_val = np.median(midas_depth[ymin:ymax, xmin:xmax]) 
            
            # Dummy logic to illustrate the formula structure until true fusion is calibrated
            # r_metric = (r_px * Z_rim_metric) / focal_length_x
            # volume = np.pi * (r_metric**2) * h_metric
            volume_text = f"Cup detected. R_px: {r_px:.1f}"

        cv2.putText(frame_l_undistorted, volume_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        # Combine Original + Bbox and Depth Map
        combined = np.hstack((frame_l_undistorted, midas_vis))
        cv2.imshow("Volume Estimation (Left: RGB+YOLO | Right: MiDaS Depth)", combined)

        if cv2.waitKey(1) == 27:
            break

    cap_left.release()
    cap_right.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
