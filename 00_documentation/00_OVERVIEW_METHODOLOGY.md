# Midas Coffee Machine: Computer Vision Methodology Overview

This directory contains the complete theoretical and mathematical foundation for the Midas Coffee Machine precision volume and distance estimation system.

---

## 1. Document Index

| File | Content |
| :--- | :--- |
| **[01_THEORY_Z_TRAY_ESTIMATION.md](./01_THEORY_Z_TRAY_ESTIMATION.md)** | Absolute camera altitude estimation using **Anchor ROIs** and **Polynomial Regression** via Monocular AI (MiDaS). |
| **[02_THEORY_Z_RIM_ESTIMATION.md](./02_THEORY_Z_RIM_ESTIMATION.md)** | Cup height and diameter estimation using **Pinhole Geometry** and MiDaS **Relative-to-Absolute scaling**. |
| **[03_THEORY_METHOD_B_SLAT_DETECTION.md](./03_THEORY_METHOD_B_SLAT_DETECTION.md)** | Precision Tray Pattern Recognition (Method B) using **Horizontal Slat Pitch** and Hough Line transforms. |
| **[04_THEORY_YOLO_AND_ROI_MANAGEMENT.md](./04_THEORY_YOLO_AND_ROI_MANAGEMENT.md)** | Neural Network **Object Detection (YOLOv8)** for dynamic masking, cup isolation, and region-of-interest extraction. |

---

## 2. Integrated Pipeline Architecture

The system operates as a unified, dual-stream vision pipeline:

### Stream A: Tray Distance Tracking ($Z_{tray}$)
- **Objective**: Determine the absolute vertical distance from the camera to the tray.
- **Primary Method**: **Method B (Slat Pitch)**. Uses the physical geometry of the tray slats to calculate distance.
- **Calibration Anchor**: Uses a locked focal length ($f$) and physical pitch ($P_{real}$) to establish a ground truth baseline.

### Stream B: Cup Volumetrics ($H_{cup}, W_{real}$)
- **Objective**: Measure the cup's height and diameter to calculate volume in milliliters (mL).
- **Primary Method**: **MiDaS Scaling**. Uses the ratio between the detected Cup Rim and the Tray Surface.
- **Dependency**: Requires the live $Z_{tray}$ from Stream A to resolve the scale ambiguity of the AI depth model.

---

## 3. Accuracy & Resilience Core Logic

To survive real-world environments (varying nozzle heights & cup sizes), the system employs three "Safety Nets":

1. **Slat-Count Ratio Correction**: Compensates for software-induced lens scaling (auto-focus) by analyzing how many slats are visible in the frame.
2. **Temporal Median Filtering**: Smooths out ultrasonic noise and glints from the stainless-steel tray.
3. **CLAHE Normalization**: Enhances visibility in low-light contexts to ensure Hough Lines are always detectable.

---

## 4. Summary of Formulas

- **Tray Distance**: $D = (f \cdot P \cdot \cos\theta) / p$
- **Rim Distance**: $Z_{rim} = (Z_{tray} / R) \cdot \alpha$
- **Cup Height**: $H = Z_{tray} - Z_{rim}$
- **Cup Diameter**: $W = (w_{px} \cdot Z_{rim}) / f$
- **Volume**: $V = \pi \cdot (W / 2)^2 \cdot H$
