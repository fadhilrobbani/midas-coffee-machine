import cv2
import numpy as np
import argparse
import yaml
import os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0, help="Camera index")
    ap.add_argument("--rows", type=int, default=6, help="Chessboard inner corners (rows)")
    ap.add_argument("--cols", type=int, default=9, help="Chessboard inner corners (cols)")
    ap.add_argument("--square-size", type=float, default=2.0, help="Square physical size in cm")
    ap.add_argument("--fisheye-model", action="store_true", help="Use strict cv2.fisheye calibration equations")
    args = ap.parse_args()

    # termination criteria
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    # prepare object points, like (0,0,0), (1,0,0), (2,0,0) ....,(cols,rows,0)
    objp = np.zeros((args.rows * args.cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:args.cols, 0:args.rows].T.reshape(-1, 2)
    objp *= args.square_size

    objpoints = [] # 3d point in real world space
    imgpoints = [] # 2d points in image plane.

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"Error: Could not open camera {args.camera}")
        return

    print("========================================")
    print(" 📷 AUTO-FOCAL FISHEYE CALIBRATION TOOL")
    print(f" Chessboard Size : {args.cols} cols x {args.rows} rows")
    print("========================================")
    print("Petunjuk:")
    print("1. Arahkan papan catur ke kamera dari berbagai sisi.")
    print("2. Tekan [SPASI] untuk memotret saat ada tulisan DETECTED.")
    print("3. Kumpulkan minimal 10 foto.")
    print("4. Tekan [ C ] untuk menghitung Focal Length dan Simpan.")
    print("[ Q ] Quit tanpa menyimpan\n")

    captured_imgs = 0
    img_shape = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if img_shape is None:
            img_shape = gray.shape[::-1]

        # Find the chess board corners
        ret_cb, corners = cv2.findChessboardCorners(gray, (args.cols, args.rows), None)

        display_frame = frame.copy()
        if ret_cb:
            cv2.drawChessboardCorners(display_frame, (args.cols, args.rows), corners, ret_cb)
            cv2.putText(display_frame, "CORNERS DETECTED [PRESS SPACE]", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(display_frame, "SEARCHING CHESSBOARD...", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.putText(display_frame, f"Captured: {captured_imgs}", (15, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        cv2.imshow("Lens Calibrator", display_frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord(' '):
            if ret_cb:
                corners2 = cv2.cornerSubPix(gray, corners, (11,11), (-1,-1), criteria)
                objpoints.append(objp)
                imgpoints.append(corners2)
                captured_imgs += 1
                print(f"[+] Snapshot #{captured_imgs} saved.")
            else:
                print("[-] Chessboard not detected clearly. Try moving it.")
        elif key == ord('c') or key == ord('C'):
            if captured_imgs >= 5:
                print("\n[CALIB] Menghitung Focal Length dan Distorsi. Mohon tunggu...")
                break
            else:
                print(f"[!] Dapatkan minimal 5 gambar (baru {captured_imgs}). Idealnya 10-15.")
        elif key == ord('q') or key == ord('Q'):
            print("Dibatalkan.")
            cap.release()
            cv2.destroyAllWindows()
            return

    cap.release()
    cv2.destroyAllWindows()

    if captured_imgs < 5:
        return

    # Kalibrasi
    print("Menghitung Intrinsic Matrix...")
    if args.fisheye_model:
        objpoints = [np.expand_dims(x, 1) for x in objpoints]
        imgpoints = [np.expand_dims(x, 1) for x in imgpoints]
        K = np.zeros((3, 3))
        D = np.zeros((4, 1))
        rvecs = [np.zeros((1, 1, 3), dtype=np.float64) for _ in range(len(objpoints))]
        tvecs = [np.zeros((1, 1, 3), dtype=np.float64) for _ in range(len(objpoints))]
        
        calibration_flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC + cv2.fisheye.CALIB_FIX_SKEW
        ret, K, D, rvecs, tvecs = cv2.fisheye.calibrate(
            objpoints, imgpoints, img_shape, K, D, rvecs, tvecs, calibration_flags,
            (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-6)
        )
        is_fisheye = True
    else:
        ret, K, D, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, img_shape, None, None)
        is_fisheye = False

    print("\n[SUKSES] Kalibrasi selesai!")
    print(f"Focal Length X (fx) : {K[0,0]:.1f} px")
    print(f"Focal Length Y (fy) : {K[1,1]:.1f} px")
    print(f"Titik Pusat (cx,cy) : {K[0,2]:.1f}, {K[1,2]:.1f}")
    print("Distorsi (D)        :", D.flatten())
    
    out_dict = {
        "is_fisheye_model": is_fisheye,
        "camera_matrix": K.tolist(),
        "dist_coeffs": D.tolist(),
        "img_shape": list(img_shape) if img_shape else None
    }

    out_path = os.path.join(os.path.dirname(__file__), "focal_length_calibration.yaml")
    with open(out_path, "w") as f:
        yaml.dump(out_dict, f, default_flow_style=False)
    print(f"\n[OK] Profil Focal Length Lensa berhasil disimpan ke:\n     {out_path}")

if __name__ == "__main__":
    main()
