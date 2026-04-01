# MiDaS Single-Camera Volume Estimation Guide

This document serves as a comprehensive guide and reference designed for both human developers and AI assistants to quickly understand the structure, algorithms, and modules used in the Single-Camera MiDaS Volume Estimation project.

## Overview
This system estimates the volume of a cup using a **single RGB camera** combined with:
1. **YOLOv8** for 2D cup rim detection and bounding box extraction.
2. **MiDaS (v2.1 Small 256)** for dense relative depth estimation.
3. **Geometric Math & Linear Inverse Regression** to convert relative depth and 2D bounding boxes into physical attributes (Z-distance, cup height, real width, and volume).

## Directory Structure
The core logic has been refactored into a clear, modular package located in `midas_volumecup/`:

- **`midas_volumecup/depth.py`**: Wraps the MiDaS depth estimator.
  - Generates the relative depth map.
  - Extracts the median relative depth of the cup rim (`M_rim`) and a static tray reference region (`M_tray`).
- **`midas_volumecup/detector.py`**: Wraps YOLOv8s.
  - Loads `weights/cup_detection_v3_12_s_best.pt`, exclusively detecting class `0` (cup rim).
- **`midas_volumecup/volume_math.py`**: Pure math functions.
  - **`calculate_z_rim`**: Uses an offline-calibrated linear regression on an inverted axis ($a*(1/r) + c$) where $r = M_{rim} / M_{tray}$ to compute the true physical distance ($Z_{rim}$) in cm. This physics-grounded model replaces fragile quadratic polynomials.
  - **`calculate_volume`**: Derives Cup Height ($H_{cup} = H_{nozzle} - Z_{rim}$), Actual physical width of the rim ($W_{real}$ using focal length), and ultimately the physical volume using a simple cylinder formula.

## Executable Scripts and Workflow

### 1. Calibration (`calibrate_midas_volume.py`)
Before running the primary volume estimator, you must capture the properties of your environment and camera. The GUI provides a live split-screen preview: the left side shows your standard RGB camera feed with YOLO's bounding box overlays, and the right side shows MiDaS depth mapping. This setup allows you to see precisely what the models are detecting.

#### Step 0: Signal A/B Calibration (Dynamic Nozzle Altitude)
Because the camera nozzle moves up and down during brewing, the software needs to dynamically calculate its own altitude ($H_{nozzle}$) purely by reading the shadows on the tray.
1. Physically move the coffee machine's nozzle block to a known height (e.g., lower it to exact `20.0 cm`).
2. In the "Signal A/B" section of the UI, enter that exact measured altitude in the **True Nozzle H (cm)** field.
3. Click **Capture Signal Data Point**. The code grabs the exact shadow transition sub-pixel ($R_{trans}$) for Signal A, and the total raw dark ratio for Signal B.
4. Move the nozzle back up to a completely different height (e.g., `35.0 cm`), type the new true height, and click **Capture Signal Data Point** again.
5. Capture at least 2 heights (preferably 3 or 4 points mapping the full range of motion of the rail).
6. Click **Fit Linear Regression (A & B)**. The code perfectly calculates the $m, c, m_b, c_b$ physics coefficients simultaneously!

#### Step 1: Focal Length ($f$) Calibration
The script needs to understand how pixels on your specific camera correlate to real-world measurements.
1. Place a reference object of a known size (e.g., An 8.0 cm disc or square) onto the tray.
2. In the "Focal Length" section of the UI, enter the **Real Width (cm)** of the object (e.g., `8.0`).
3. Enter the exact **Distance Z (cm)** from your camera lens to that object.
4. Click **Capture & Select ROI Object**.
5. A pop-up OpenCV window will appear showing the captured frame. Click and drag your mouse to draw a box tightly around the reference object, then press **Enter** or **Space** on your keyboard to lock it in. The UI will instantly display the computed focal length `f`.

#### Step 2: Inverse Depth Calibration ($a, b, c$)
MiDaS doesn't output true depth in cm; it outputs relative depth. We build an indestructible linear relationship between MiDaS' mathematically inverted relative depth ratio ($1 / (M_{rim}/M_{tray})$) and True Z distance.
1. Enter the **Tray ROI**. This is a bounding box `(x1, y1, x2, y2)` referencing an empty patch of the tray that will never be occluded. You will see a blue "Tray ROI" box drawn continuously on the live preview frame. Make sure it rests on flat, empty tray space.
2. Place your first cup under the nozzle. Make sure the green YOLO "Rim" bounding box locks onto the top of the cup in the live preview.
3. Measure the exact physical distance from the camera lens to the cup rim. Enter this in the **True Z_rim (cm)** field.
4. Click **Capture Data Point**. The UI will extract the $M_{rim}$ inside the YOLO box and $M_{tray}$ inside your Tray ROI and log the point to a persistent JSON dataset.
5. Swap the cup out for a different-sized cup, enter the new **True Z_rim (cm)**, and click **Capture Data Point**. 
6. Repeat until you have at least **3 data points** from cups of varying heights.
7. Click **Fit Polynomial Curve** (now acts as Linear Fit). The script runs a robust 1D mathematical `np.polyfit` over the inverted axis to compute pure linear bounds for $a$ and $c$, safely bypassing noisy AI jitter.

*(Note: The runtime backend automatically applies CLAHE dynamic lighting compensation, robust horizontal strip lip-sampling, and Exponential Moving Average smoothing on the backend for industrial stability).*

8. Finally, click **Save Calibration**. Your Signal constants, $f$, and $a,b,c$ values are written to `midas_calibration.yaml` where the runner script can automatically read them!

### 2. Main Estimation Runner (`run_volumecup_midas.py`)
This script uses the calibration data to estimate volumes in real-time.
- Features a Tkinter GUI displaying the loaded configuration from `midas_calibration.yaml` (Focal length, Nozzle Height, Polynomial constants, and Tray ROI).
- Clicking **Start Estimation** loads the YOLO and MiDaS models into memory and initiates the OpenCV video capture loop.
- The UI renders both the source RGB feed with bounding boxes and the pseudo-colored MiDaS depth map side-by-side, overlaying the live calculated Volume.

## Necessary Weights / Models
For these scripts to function properly, the following weights must exist in the `weights/` directory:
- `weights/midas_v21_small_256.pt`: The MiDaS depth model.
- `weights/cup_detection_v3_12_s_best.pt`: The YOLOv8s object detection model.
