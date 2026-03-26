import cv2
import numpy as np
import os
import yaml

# Stopping criteria for subpixel corner refinement
criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

def save_calibration(ret, mtx1, dist1, mtx2, dist2, R, T, E, F, left_idx, right_idx):
    calibration_data = {
        'camera_index_left': left_idx,
        'camera_index_right': right_idx,
        'camera_matrix_left': mtx1.tolist(),
        'dist_coeff_left': dist1.tolist(),
        'camera_matrix_right': mtx2.tolist(),
        'dist_coeff_right': dist2.tolist(),
        'R': R.tolist(),
        'T': T.tolist(),
        'E': E.tolist(),
        'F': F.tolist()
    }
    with open('calibration_params.yml', 'w') as outfile:
        yaml.dump(calibration_data, outfile, default_flow_style=False)
    print("Calibration saved to calibration_params.yml")

def select_cameras():
    print("Scanning for available cameras...")
    available_cameras = []
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                available_cameras.append(i)
        cap.release()
    
    if len(available_cameras) < 2:
        print(f"Error: Found only {len(available_cameras)} working cameras: {available_cameras}. Need at least 2.")
        return None, None
        
    print(f"\nAvailable camera indices: {available_cameras}")
    print("Previewing available cameras...")
    
    for idx in available_cameras:
        cap = cv2.VideoCapture(idx)
        ret, frame = cap.read()
        if ret:
            cv2.imshow(f"Camera Preview - Index {idx}", frame)
            print(f"Showing camera {idx}. Press any key on the window to view the next camera.")
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        cap.release()

    print("\nPlease enter the index for the LEFT camera:")
    left_str = input()
    print("Please enter the index for the RIGHT camera:")
    right_str = input()
    
    try:
        left_idx = int(left_str.strip())
        right_idx = int(right_str.strip())
        return left_idx, right_idx
    except ValueError:
        print("Invalid input. Camera indices must be integers.")
        return None, None

def configure_checkerboard():
    print("\n--- Checkerboard Configuration ---")
    print("CRITICAL: You must count the INNER corners of your checkerboard, not the outer squares.")
    print("For example, a standard 8x8 squares chessboard has 7x7 INNER corners.")
    
    try:
        w = int(input("Enter number of INNER corners horizontally (Width): ").strip())
        h = int(input("Enter number of INNER corners vertically (Height): ").strip())
        size = float(input("Enter the physical size of one square (e.g., 2.5 for 2.5cm): ").strip())
        return (w, h), size
    except ValueError:
        print("Invalid input. Using default 9x6 with 2.5 size.")
        return (9, 6), 2.5

def main():
    left_idx, right_idx = select_cameras()
    if left_idx is None or right_idx is None:
        return

    checkerboard_dims, square_size = configure_checkerboard()
    
    # Prepare object points
    objp = np.zeros((checkerboard_dims[0] * checkerboard_dims[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:checkerboard_dims[0], 0:checkerboard_dims[1]].T.reshape(-1, 2)
    objp = objp * square_size

    objpoints = [] 
    imgpoints_left = [] 
    imgpoints_right = [] 

    print(f"\nOpening LEFT camera ({left_idx}) and RIGHT camera ({right_idx})...")
    cap_left = cv2.VideoCapture(left_idx)
    capt_right = cv2.VideoCapture(right_idx)

    if not cap_left.isOpened() or not capt_right.isOpened():
        print("Error: Could not open the selected cameras.")
        return

    cap_left.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap_left.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    capt_right.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    capt_right.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("\n--- Stereo Calibration GUI ---")
    print(f"Looking for a {checkerboard_dims[0]}x{checkerboard_dims[1]} checkerboard.")
    print("The checkerboard lines will be drawn on the live feed when detected.")
    print("Press 'c' to CAPTURE a frame ONLY when both cameras show the colored lines.")
    print("Press 'q' to QUIT and perform calibration when you have enough frames (15+).")

    frame_count = 0
    img_shape = None

    while True:
        ret1, frame_left = cap_left.read()
        ret2, frame_right = capt_right.read()

        if not ret1 or not ret2:
            print("Failed to grab frames")
            break

        if img_shape is None:
            img_shape = frame_left.shape[:2]

        gray_left = cv2.cvtColor(frame_left, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(frame_right, cv2.COLOR_BGR2GRAY)

        # Continously search and draw for visual feedback using FAST_CHECK
        ret_left, corners_left = cv2.findChessboardCorners(gray_left, checkerboard_dims, cv2.CALIB_CB_FAST_CHECK)
        ret_right, corners_right = cv2.findChessboardCorners(gray_right, checkerboard_dims, cv2.CALIB_CB_FAST_CHECK)
        
        vis_left = frame_left.copy()
        vis_right = frame_right.copy()

        if ret_left:
            cv2.drawChessboardCorners(vis_left, checkerboard_dims, corners_left, ret_left)
        if ret_right:
            cv2.drawChessboardCorners(vis_right, checkerboard_dims, corners_right, ret_right)

        status_color = (0, 255, 0) if (ret_left and ret_right) else (0, 0, 255)
        status_text = "READY TO CAPTURE ('c')" if (ret_left and ret_right) else "MOVE PATTERN / ADJUST LIGHT"

        cv2.putText(vis_left, f"Captured: {frame_count}/15+", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(vis_right, status_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

        combined = np.hstack((vis_left, vis_right))
        cv2.imshow('Stereo Calibration (Left | Right)', combined)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('c'):
            if ret_left and ret_right:
                # Need to find corners properly without FAST_CHECK for accuracy before subpix
                ret_left_full, corners_left_full = cv2.findChessboardCorners(gray_left, checkerboard_dims, None)
                ret_right_full, corners_right_full = cv2.findChessboardCorners(gray_right, checkerboard_dims, None)
                
                if ret_left_full and ret_right_full:
                    corners_left_sub = cv2.cornerSubPix(gray_left, corners_left_full, (11, 11), (-1, -1), criteria)
                    corners_right_sub = cv2.cornerSubPix(gray_right, corners_right_full, (11, 11), (-1, -1), criteria)

                    objpoints.append(objp)
                    imgpoints_left.append(corners_left_sub)
                    imgpoints_right.append(corners_right_sub)

                    frame_count += 1
                    print(f"Captured perfectly aligned stereo frame {frame_count}!")
                    
                    # Flash white to indicate capture
                    flash = np.ones_like(combined) * 255
                    cv2.imshow('Stereo Calibration (Left | Right)', flash)
                    cv2.waitKey(100)
            else:
                print("Cannot capture: Checkerboard is not fully visible in BOTH cameras right now.")

        elif key == ord('q'):
            break

    cv2.destroyAllWindows()
    cap_left.release()
    capt_right.release()

    if frame_count > 0:
        print("\nStarting Calibration... Please wait.")
        # 1. Calibrate Left Camera individually
        ret_l, mtx_l, dist_l, rvecs_l, tvecs_l = cv2.calibrateCamera(objpoints, imgpoints_left, gray_left.shape[::-1], None, None)
        
        # 2. Calibrate Right Camera individually
        ret_r, mtx_r, dist_r, rvecs_r, tvecs_r = cv2.calibrateCamera(objpoints, imgpoints_right, gray_right.shape[::-1], None, None)

        print("Individual calibration done. Running stereo calibration...")

        # 3. Stereo Calibrate
        flags = 0
        flags |= cv2.CALIB_FIX_INTRINSIC
        stereocalib_criteria = (cv2.TERM_CRITERIA_MAX_ITER + cv2.TERM_CRITERIA_EPS, 100, 1e-5)
        ret, M1, d1, M2, d2, R, T, E, F = cv2.stereoCalibrate(
            objpoints, imgpoints_left, imgpoints_right,
            mtx_l, dist_l,
            mtx_r, dist_r,
            gray_left.shape[::-1],
            criteria=stereocalib_criteria,
            flags=flags)

        print(f"Stereo Calibration RSME: {ret}")
        save_calibration(ret, M1, d1, M2, d2, R, T, E, F, left_idx, right_idx)
    else:
        print("No valid frames captured. Exiting without calibrating.")

if __name__ == '__main__':
    os.environ['QT_QPA_PLATFORM'] = 'xcb'
    main()
