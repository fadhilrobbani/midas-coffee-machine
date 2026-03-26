import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import cv2
import yaml
import numpy as np
import threading

from midas_volumecup.depth import MidasDepthEstimator
from midas_volumecup.detector import YoloDetector
from midas_volumecup.volume_math import calculate_z_rim, calculate_volume, measure_nozzle_height
from midas_volumecup.camera_config import CameraConfig

class RunnerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="MiDaS Volume Runner")
        self.set_default_size(1000, 600)
        self.connect("destroy", self.on_destroy)
        
        self.running = False
        self.cap = None
        self.depth_estimator = None
        self.detector = None
        self.cam_config = None
        self.cam_idx = 0
        self.z_rim_smooth = None
        
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add(hbox)

        vbox_ctrl = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_ctrl.set_border_width(10)
        
        frame_vars = Gtk.Frame(label="Variables (from YAML)")
        vbox_vars = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox_vars.set_border_width(5)
        
        box_f = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_f.pack_start(Gtk.Label(label="Focal Length (f):"), False, False, 0)
        self.entry_f = Gtk.Entry(text="800.0")
        box_f.pack_start(self.entry_f, True, True, 0)
        vbox_vars.pack_start(box_f, False, False, 0)

        box_sig = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_sig.pack_start(Gtk.Label(label="Signal A/B (m,c,mb,cb):"), False, False, 0)
        self.entry_sig = Gtk.Entry(text="1.0, 0.0, 1.0, 0.0")
        box_sig.pack_start(self.entry_sig, True, True, 0)
        vbox_vars.pack_start(box_sig, False, False, 0)

        box_poly = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_poly.pack_start(Gtk.Label(label="Poly (a,b,c):"), False, False, 0)
        self.entry_poly = Gtk.Entry(text="0,10,0")
        box_poly.pack_start(self.entry_poly, True, True, 0)
        vbox_vars.pack_start(box_poly, False, False, 0)

        box_roi = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box_roi.pack_start(Gtk.Label(label="Tray ROI (x1,y1,x2,y2):"), False, False, 0)
        self.entry_roi = Gtk.Entry(text="10,400,100,470")
        box_roi.pack_start(self.entry_roi, True, True, 0)
        vbox_vars.pack_start(box_roi, False, False, 0)

        frame_vars.add(vbox_vars)
        vbox_ctrl.pack_start(frame_vars, False, False, 0)

        self.btn_start = Gtk.Button(label="Start Estimation")
        self.btn_start.connect("clicked", self.on_start_clicked)
        vbox_ctrl.pack_start(self.btn_start, False, False, 10)

        self.btn_stop = Gtk.Button(label="Stop")
        self.btn_stop.connect("clicked", self.on_stop_clicked)
        self.btn_stop.set_sensitive(False)
        vbox_ctrl.pack_start(self.btn_stop, False, False, 0)

        self.lbl_status = Gtk.Label(label="Ready.")
        vbox_ctrl.pack_start(self.lbl_status, False, False, 10)

        hbox.pack_start(vbox_ctrl, False, False, 0)

        self.image = Gtk.Image()
        hbox.pack_start(self.image, True, True, 0)

    def load_config(self):
        try:
            with open('midas_calibration.yaml', 'r') as f:
                config = yaml.safe_load(f)
                self.entry_f.set_text(str(config.get('focal_length', 800.0)))
                self.entry_poly.set_text(f"{config.get('a',0)},{config.get('b',10)},{config.get('c',0)}")
                
                sig_m = config.get('signal_m', 1.0)
                sig_c = config.get('signal_c', 0.0)
                sig_mb = config.get('signal_mb', 1.0)
                
                self.cam_idx = config.get('camera_index', 0)
                
                roi = config.get('tray_roi', [10,400,100,470])
                self.entry_roi.set_text(f"{roi[0]},{roi[1]},{roi[2]},{roi[3]}")
        except FileNotFoundError:
            pass

    def on_start_clicked(self, widget):
        if self.running: return
        self.running = True
        self.btn_start.set_sensitive(False)
        self.btn_stop.set_sensitive(True)
        self.lbl_status.set_text("Loading models...")
        threading.Thread(target=self.run_loop, daemon=True).start()

    def on_stop_clicked(self, widget):
        self.running = False
        self.btn_start.set_sensitive(True)
        self.btn_stop.set_sensitive(False)
        self.lbl_status.set_text("Stopped.")

    def run_loop(self):
        focal = float(self.entry_f.get_text())
        m, c, mb, cb = map(float, self.entry_sig.get_text().split(','))
        a, b, coeff_c = map(float, self.entry_poly.get_text().split(','))
        tray_roi = tuple(map(int, self.entry_roi.get_text().split(',')))
        
        if self.depth_estimator is None: self.depth_estimator = MidasDepthEstimator()
        if self.detector is None: self.detector = YoloDetector()
            
        GLib.idle_add(self.lbl_status.set_text, "Running logic loop...")
        self.cap = cv2.VideoCapture(self.cam_idx)
        
        while self.running:
            ret, frame = self.cap.read()
            if not ret: break
            
            if self.cam_config is None:
                self.cam_config = CameraConfig(frame.shape[1], frame.shape[0])
            
            depth_map = self.depth_estimator.process(frame)
            boxes = self.detector.detect(frame)
            
            # Dynamic Nozzle height via Signal A/B
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            H_nozzle = measure_nozzle_height(gray, self.cam_config, m, c, mb, cb)
            
            volume_text = "Volume: N/A"
            if H_nozzle is not None and boxes:
                best_box = boxes[0]['bbox']
                xmin, ymin, xmax, ymax = best_box
                cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
                
                w_pixels = max(xmax - xmin, ymax - ymin)
                
                # MiDaS raw depth can be negative. Normalize to 0-255 before sampling.
                depth_norm = cv2.normalize(depth_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                
                m_rim = self.depth_estimator.get_rim_depth(depth_norm, best_box)
                m_tray = self.depth_estimator.get_tray_depth(depth_norm, tray_roi)
                
                if m_tray > 0:
                    z_rim_raw = calculate_z_rim(m_rim, m_tray, a, b, coeff_c)
                    
                    # Temporal Smoothing (Exponential Moving Average)
                    if self.z_rim_smooth is None:
                        self.z_rim_smooth = z_rim_raw
                    else:
                        self.z_rim_smooth = 0.8 * self.z_rim_smooth + 0.2 * z_rim_raw
                        
                    h_cup, w_real, volume = calculate_volume(self.z_rim_smooth, H_nozzle, w_pixels, focal)
                    
                    volume_text = f"H_cam: {H_nozzle:.1f}cm | Z_rim: {self.z_rim_smooth:.1f}cm | Vol: {volume:.0f}mL"
                
            tx1, ty1, tx2, ty2 = tray_roi
            cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), (255, 0, 0), 2)
            cv2.putText(frame, "Tray ROI", (tx1, ty1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)
            cv2.putText(frame, volume_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            depth_vis = cv2.normalize(depth_map, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            depth_vis = cv2.applyColorMap(depth_vis, cv2.COLORMAP_INFERNO)
            
            combined = np.hstack((frame, depth_vis))
            
            rgb = cv2.cvtColor(combined, cv2.COLOR_BGR2RGB)
            height, width, ch = rgb.shape
            pb = GdkPixbuf.Pixbuf.new_from_data(rgb.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8, width, height, width*3)
            GLib.idle_add(self.image.set_from_pixbuf, pb)
            
        if self.cap: self.cap.release()

    def on_destroy(self, widget):
        self.running = False
        Gtk.main_quit()

if __name__ == "__main__":
    win = RunnerWindow()
    win.show_all()
    Gtk.main()
