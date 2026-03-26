import cv2
import yaml
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from midas_volumecup.depth import MidasDepthEstimator
from midas_volumecup.detector import YoloDetector
from midas_volumecup.volume_math import calculate_z_rim, calculate_volume

class RunnerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MiDaS Volume Runner")
        
        self.running = False
        self.cap = None
        
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # --- Config Variables ---
        cf = ttk.LabelFrame(main_frame, text="Variables", padding="10")
        cf.grid(row=0, column=0, pady=5, sticky=(tk.W, tk.E))
        
        ttk.Label(cf, text="Focal Length (f):").grid(row=0, column=0, sticky=tk.W)
        self.f_var = tk.StringVar(value="800.0")
        ttk.Entry(cf, textvariable=self.f_var, width=10).grid(row=0, column=1)

        ttk.Label(cf, text="Nozzle Height (H_noz):").grid(row=1, column=0, sticky=tk.W)
        self.hnoz_var = tk.StringVar(value="35.0")
        ttk.Entry(cf, textvariable=self.hnoz_var, width=10).grid(row=1, column=1)

        ttk.Label(cf, text="Poly (a,b,c):").grid(row=2, column=0, sticky=tk.W)
        self.abc_var = tk.StringVar(value="0.0, 10.0, 0.0")
        ttk.Entry(cf, textvariable=self.abc_var, width=20).grid(row=2, column=1)

        ttk.Label(cf, text="Tray ROI:").grid(row=3, column=0, sticky=tk.W)
        self.roi_var = tk.StringVar(value="10,400,100,470")
        ttk.Entry(cf, textvariable=self.roi_var, width=20).grid(row=3, column=1)
        
        # Controls
        ctrl = ttk.Frame(main_frame)
        ctrl.grid(row=1, column=0, pady=10)
        
        self.start_btn = ttk.Button(ctrl, text="Start Estimation", command=self.start_loop)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(ctrl, text="Stop", command=self.stop_loop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

    def load_config(self):
        try:
            with open('midas_calibration.yaml', 'r') as f:
                config = yaml.safe_load(f)
                self.f_var.set(str(config.get('focal_length', 800.0)))
                self.abc_var.set(f"{config.get('a',0)},{config.get('b',10)},{config.get('c',0)}")
                roi = config.get('tray_roi', [10,400,100,470])
                self.roi_var.set(f"{roi[0]},{roi[1]},{roi[2]},{roi[3]}")
        except FileNotFoundError:
            pass # Use defaults
            
    def start_loop(self):
        if self.running: return
        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        threading.Thread(target=self.run_estimation, daemon=True).start()

    def stop_loop(self):
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        if self.cap:
            self.cap.release()
            cv2.destroyAllWindows()

    def run_estimation(self):
        try:
            # Parse vars
            focal = float(self.f_var.get())
            h_noz = float(self.hnoz_var.get())
            a, b, c = map(float, self.abc_var.get().split(','))
            tray_roi = tuple(map(int, self.roi_var.get().split(',')))
            
            print("Loading models...")
            depth_estimator = MidasDepthEstimator()
            detector = YoloDetector()
            
            # Use index 0 for now (or read from config if prefer)
            self.cap = cv2.VideoCapture(0)
            
            print("Starting video loop...")
            while self.running:
                ret, frame = self.cap.read()
                if not ret: break
                
                # 1. MiDaS Depth
                depth_map = depth_estimator.process(frame)
                
                # 2. YOLO
                boxes = detector.detect(frame)
                
                volume_text = "Volume: N/A"
                if boxes:
                    best_box = boxes[0]['bbox']
                    xmin, ymin, xmax, ymax = best_box
                    cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
                    
                    w_pixels = max(xmax - xmin, ymax - ymin)
                    
                    m_rim = depth_estimator.get_rim_depth(depth_map, best_box)
                    m_tray = depth_estimator.get_tray_depth(depth_map, tray_roi)
                    
                    if m_tray > 0:
                        z_rim = calculate_z_rim(m_rim, m_tray, a, b, c)
                        h_cup, w_real, volume = calculate_volume(z_rim, h_noz, w_pixels, focal)
                        volume_text = f"Vol: {volume:.0f} mL (H:{h_cup:.1f} W:{w_real:.1f})"
                    
                # Draw Tray ROI
                tx1, ty1, tx2, ty2 = tray_roi
                cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), (255, 0, 0), 2)
                cv2.putText(frame, "Tray ROI", (tx1, ty1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)

                cv2.putText(frame, volume_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                # Visualize Depth
                depth_vis = cv2.normalize(depth_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                depth_vis = cv2.applyColorMap(depth_vis, cv2.COLORMAP_INFERNO)
                
                combined = np.hstack((frame, depth_vis))
                cv2.imshow("MiDaS Volume Estimation", combined)
                
                if cv2.waitKey(1) == 27: # ESC
                    self.stop_loop()
                    break
                    
        except Exception as e:
            print(f"Error in execution loop: {e}")
            self.stop_loop()

if __name__ == "__main__":
    root = tk.Tk()
    app = RunnerApp(root)
    root.mainloop()
