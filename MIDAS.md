# MiDaS Single-Camera Volume Estimation Guide

This document serves as a comprehensive guide and reference designed for both human developers and AI assistants to quickly understand the structure, algorithms, and modules used in the Single-Camera MiDaS Volume Estimation project.

## Overview
This system estimates the volume of a cup using a **single RGB camera** combined with:
1. **YOLOv8** for 2D cup rim detection and bounding box extraction.
2. **MiDaS (v2.1 Small 256)** for dense relative depth estimation.
3. **Geometric Math & Polynomial Regression** to convert relative depth and 2D bounding boxes into physical attributes (Z-distance, cup height, real width, and volume).

## Directory Structure
The core logic has been refactored into a clear, modular package located in `midas_volumecup/`:

- **`midas_volumecup/depth.py`**: Wraps the MiDaS depth estimator.
  - Generates the relative depth map.
  - Extracts the median relative depth of the cup rim (`M_rim`) and a static tray reference region (`M_tray`).
- **`midas_volumecup/detector.py`**: Wraps YOLOv8s.
  - Loads `weights/cup_detection_v3_12_s_best.pt`, exclusively detecting class `0` (cup rim).
- **`midas_volumecup/volume_math.py`**: Pure math functions.
  - **`calculate_z_rim`**: Uses an offline-calibrated quadratic polynomial ($a*r^2 + b*r + c$) where $r = M_{rim} / M_{tray}$ to compute the true physical distance ($Z_{rim}$) in cm.
  - **`calculate_volume`**: Derives Cup Height ($H_{cup} = H_{nozzle} - Z_{rim}$), Actual physical width of the rim ($W_{real}$ using focal length), and ultimately the physical volume using a simple cylinder formula.

## Executable Scripts and Workflow

### 1. Calibration (`calibrate_midas_volume.py`)
Before running the main estimation, the camera and polynomial parameters must be calibrated.
This script provides a Tkinter GUI to guide you through two steps:

**Step 1: Focal Length ($f$) Calibration**
- Input the **Real Width** (e.g. 8.0 cm) of a known object (like a disc) placed on the tray.
- Input the **Distance Z** from the camera to the object.
- Click **Calculate** and manually draw a bounding box (ROI) around the object. The script calculates focal length $f$ based on pixel width.

**Step 2: Polynomial Calibration ($a, b, c$)**
- Enter the **Tray ROI** coordinates (x1, y1, x2, y2) representing an empty portion of the tray for the $M_{tray}$ reference.
- Place a cup of known height under the nozzle, enter its **True Z_rim** (Camera Nozzle Height - Cup Height), and click **Add Data Point**. This extracts $M_{rim}$ and $M_{tray}$ for that cup.
- Repeat for at least 3 cups of varying sizes.
- Click **Fit Polynomial** to generate the $a, b, c$ coefficients.
- **Save Calibration**: Writes the config to `midas_calibration.yaml`.

### 2. Main Estimation Runner (`run_volumecup_midas.py`)
This script uses the calibration data to estimate volumes in real-time.
- Features a Tkinter GUI displaying the loaded configuration from `midas_calibration.yaml` (Focal length, Nozzle Height, Polynomial constants, and Tray ROI).
- Clicking **Start Estimation** loads the YOLO and MiDaS models into memory and initiates the OpenCV video capture loop.
- The UI renders both the source RGB feed with bounding boxes and the pseudo-colored MiDaS depth map side-by-side, overlaying the live calculated Volume.

## Necessary Weights / Models
For these scripts to function properly, the following weights must exist in the `weights/` directory:
- `weights/midas_v21_small_256.pt`: The MiDaS depth model.
- `weights/cup_detection_v3_12_s_best.pt`: The YOLOv8s object detection model.
