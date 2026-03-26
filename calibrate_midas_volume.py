import cv2
import yaml
import numpy as np
import tkinter as tk
from tkinter import messagebox, ttk
from midas_volumecup.depth import MidasDepthEstimator
from midas_volumecup.detector import YoloDetector
from scipy.optimize import curve_fit
import threading
import time

class CalibrationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MiDaS Volume Calibration")
        
        # Load models asynchronously to not freeze GUI
        self.depth_estimator = None
        self.detector = None
        
        self.data_points = [] # list of dicts: {'M_rim': x, 'M_tray': y, 'Z_rim': z}
        
        self.setup_ui()
        threading.Thread(target=self.load_models, daemon=True).start()

    def load_models(self):
        self.status_var.set("Loading MiDaS...")
        self.depth_estimator = MidasDepthEstimator()
        self.status_var.set("Loading YOLO...")
        self.detector = YoloDetector()
        self.status_var.set("Models loaded! Ready.")

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # --- Camera Setup ---
        ttk.Label(main_frame, text="Camera Index:").grid(row=0, column=0, sticky=tk.W)
        self.cam_idx_var = tk.StringVar(value="0")
        ttk.Entry(main_frame, textvariable=self.cam_idx_var, width=5).grid(row=0, column=1, sticky=tk.W)

        # --- Focus Length Calibration ---
        lf_frame = ttk.LabelFrame(main_frame, text="Step 1: Focal Length (f)", padding="10")
        lf_frame.grid(row=1, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
        
        ttk.Label(lf_frame, text="Real Width (cm):").grid(row=0, column=0, sticky=tk.W)
        self.w_real_var = tk.StringVar(value="8.0")
        ttk.Entry(lf_frame, textvariable=self.w_real_var, width=10).grid(row=0, column=1)
        
        ttk.Label(lf_frame, text="Distance Z (cm):").grid(row=1, column=0, sticky=tk.W)
        self.z_dist_var = tk.StringVar(value="30.0")
        ttk.Entry(lf_frame, textvariable=self.z_dist_var, width=10).grid(row=1, column=1)
        
        ttk.Button(lf_frame, text="Calculate f (Select Object)", command=self.calculate_focal).grid(row=2, column=0, columnspan=2, pady=5)
        
        self.focal_var = tk.StringVar(value="Not calculated")
        ttk.Label(lf_frame, text="f = ").grid(row=3, column=0, sticky=tk.E)
        ttk.Label(lf_frame, textvariable=self.focal_var).grid(row=3, column=1, sticky=tk.W)

        # --- Polynomial Calibration ---
        poly_frame = ttk.LabelFrame(main_frame, text="Step 2: Polynomial Coefficients", padding="10")
        poly_frame.grid(row=2, column=0, columnspan=2, pady=10, sticky=(tk.W, tk.E))
        
        ttk.Label(poly_frame, text="Tray ROI (x1,y1,x2,y2):").grid(row=0, column=0, sticky=tk.W)
        self.tray_roi_var = tk.StringVar(value="10,400,100,470")
        ttk.Entry(poly_frame, textvariable=self.tray_roi_var, width=20).grid(row=0, column=1)

        ttk.Label(poly_frame, text="True Z_rim (cm):").grid(row=1, column=0, sticky=tk.W)
        self.z_rim_true_var = tk.StringVar(value="25.0")
        ttk.Entry(poly_frame, textvariable=self.z_rim_true_var, width=10).grid(row=1, column=1)

        ttk.Button(poly_frame, text="Add Data Point (Capture)", command=self.add_data_point).grid(row=2, column=0, columnspan=2, pady=5)
        
        self.points_var = tk.StringVar(value="Points Collected: 0")
        ttk.Label(poly_frame, textvariable=self.points_var).grid(row=3, column=0, columnspan=2)

        ttk.Button(poly_frame, text="Fit Polynomial", command=self.fit_polynomial).grid(row=4, column=0, columnspan=2, pady=5)
        
        self.poly_var = tk.StringVar(value="Coefficients: None")
        ttk.Label(poly_frame, textvariable=self.poly_var).grid(row=5, column=0, columnspan=2)

        # --- Save ---
        ttk.Button(main_frame, text="Save Calibration", command=self.save_calibration).grid(row=3, column=0, columnspan=2, pady=10)
        
        self.status_var = tk.StringVar(value="Initializing...")
        ttk.Label(main_frame, textvariable=self.status_var, foreground="blue").grid(row=4, column=0, columnspan=2)

    def capture_frame(self):
        try:
            cam_idx = int(self.cam_idx_var.get())
            cap = cv2.VideoCapture(cam_idx)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                raise Exception("Failed to grab frame.")
            return frame
        except Exception as e:
            messagebox.showerror("Camera Error", str(e))
            return None

    def calculate_focal(self):
        frame = self.capture_frame()
        if frame is None: return
        
        try:
            w_real = float(self.w_real_var.get())
            z_dist = float(self.z_dist_var.get())
        except ValueError:
            messagebox.showerror("Input Error", "Invalid Real Width or Distance.")
            return
            
        r = cv2.selectROI("Select Object", frame, showCrosshair=True)
        cv2.destroyWindow("Select Object")
        
        if r[2] == 0 or r[3] == 0:
            return # Cancelled
            
        # r is (x, y, w, h)
        w_pixels = max(r[2], r[3]) # longest side
        
        # f = (W_pixels * Z) / W_real
        focal_length = (w_pixels * z_dist) / w_real
        self.focal_var.set(f"{focal_length:.2f}")

    def add_data_point(self):
        if self.depth_estimator is None or self.detector is None:
            messagebox.showwarning("Models", "Models are still loading...")
            return
            
        try:
            true_z_rim = float(self.z_rim_true_var.get())
            roi_str = self.tray_roi_var.get()
            tray_roi = tuple(map(int, roi_str.split(',')))
        except ValueError:
            messagebox.showerror("Input Error", "Invalid Z_rim or Tray ROI format.")
            return

        frame = self.capture_frame()
        if frame is None: return

        # Get depth map
        depth_map = self.depth_estimator.process(frame)
        
        # Detect cup
        boxes = self.detector.detect(frame)
        if not boxes:
            messagebox.showerror("Detection Error", "No cup rim detected!")
            return
            
        best_box = boxes[0]['bbox']
        
        m_rim = self.depth_estimator.get_rim_depth(depth_map, best_box)
        m_tray = self.depth_estimator.get_tray_depth(depth_map, tray_roi)
        
        if m_tray <= 0:
            messagebox.showerror("Depth Error", "Invalid M_tray depth.")
            return

        self.data_points.append({
            'M_rim': m_rim,
            'M_tray': m_tray,
            'Z_rim': true_z_rim
        })
        
        self.points_var.set(f"Points Collected: {len(self.data_points)}")
        messagebox.showinfo("Success", f"Recorded Point!\nM_rim: {m_rim:.2f}\nM_tray: {m_tray:.2f}\nZ_rim: {true_z_rim}")

    def fit_polynomial(self):
        if len(self.data_points) < 3:
            messagebox.showerror("Fit Error", "Need at least 3 points to fit a quadratic polynomial.")
            return
            
        x_data = []
        y_data = []
        for p in self.data_points:
            ratio = p['M_rim'] / p['M_tray']
            x_data.append(ratio)
            y_data.append(p['Z_rim'])
            
        x_data = np.array(x_data)
        y_data = np.array(y_data)
        
        def quadratic(ratio, a, b, c):
            return a * (ratio**2) + b * ratio + c
            
        try:
            popt, _ = curve_fit(quadratic, x_data, y_data)
            a, b, c = popt
            self.poly_var.set(f"a={a:.4f}, b={b:.4f}, c={c:.4f}")
            self.current_coeffs = (a, b, c)
        except Exception as e:
            messagebox.showerror("Fit Error", str(e))

    def save_calibration(self):
        try:
            focal_str = self.focal_var.get()
            if focal_str == "Not calculated":
                raise ValueError("Focal length not calculated.")
            focal = float(focal_str)
            
            if not hasattr(self, 'current_coeffs'):
                raise ValueError("Polynomial not fitted.")
                
            a, b, c = self.current_coeffs
            roi_str = self.tray_roi_var.get()
            tray_roi = list(map(int, roi_str.split(',')))
            
            config = {
                'focal_length': focal,
                'a': float(a),
                'b': float(b),
                'c': float(c),
                'tray_roi': tray_roi,
                'camera_index': int(self.cam_idx_var.get())
            }
            
            with open('midas_calibration.yaml', 'w') as f:
                yaml.dump(config, f)
            messagebox.showinfo("Success", "Calibration saved to midas_calibration.yaml")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = CalibrationApp(root)
    root.mainloop()
