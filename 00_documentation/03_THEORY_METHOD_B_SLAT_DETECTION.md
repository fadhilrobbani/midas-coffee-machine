# Theory of Tray Distance Estimation: Horizontal Slat Pitch (Method B)

This document explains the mathematical and computer vision theories used to estimate the absolute camera altitude ($D_{tray}$) by analyzing the geometric patterns (slats) of the Jura coffee machine drip tray.

---

## 1. Physical Foundation: The Slat-Pitch Principle
Most professional coffee machine drip trays feature a series of parallel horizontal slats or grooves. These slats have a known, fixed physical spacing (the **Real Pitch**, $P_{real}$).

In a pinhole camera model, the angular size of these slats on the sensor is inversely proportional to their distance from the lens. By measuring the **Pixel Pitch** ($p_{pixel}$) between slats in the image, we can back-calculate the distance $D_{tray}$.

### 1.1 The Geometric Formula
For a camera mounted overhead with a tilt angle $\theta$, the relationship is:

$$ D_{tray} = \frac{f_{pixel} \times P_{real} \times \cos(\theta)}{p_{pixel}} $$

Where:
- **$D_{tray}$**: Vertical distance from camera to tray surface (cm).
- **$f_{pixel}$**: Camera focal length in pixels.
- **$P_{real}$**: Physical distance between slats (e.g., 0.8 cm).
- **$\theta$**: Camera tilt angle relative to the floor (vertical).
- **$p_{pixel}$**: Average vertical distance between detected lines in the image (pixels).

---

## 2. Computer Vision Pipeline (The "How-To")

To get stable readings, the system executes a multi-stage vision pipeline:

### 2.1 ROI Masking (YOLOv8 Integration)
A major challenge is the coffee cup itself, which obscures the tray patterns.
1. **YOLO Detection**: The system detects the cup rim.
2. **Dynamic Masking**: It creates a "No-Fly Zone" over the cup.
3. **Split-Zone Analysis**: The remaining tray area is split into **Left** and **Right** zones. Lines are detected independently in each zone to prevent "bridging" errors across the cup.

### 2.2 Slat Identification (Hough Transform)
1. **Canny Edge Detection**: Identifies sharp gradients (the edges of the slats).
2. **Hough Line Transform**: Groups edge pixels into infinite lines.
3. **Angular Filtering**: Only lines within ±2 degrees of horizontal are accepted.

### 2.3 Spatial NMS & Clustering
One physical slat often produces multiple Hough Lines. To ensure an accurate "Slat Count," the system applies **Spatial Non-Maximum Suppression (NMS)**:
- Lines within a 5-pixel vertical proximity are merged into a single **Clustered Line**.
- This results in exactly one mathematical line per physical slat.

---

## 3. Advanced Challenges & Software Solutions

### 3.1 The Auto-Focus Scaling Problem
Most webcam lenses use "Internal Focusing." As the tray moves further away, the lens scales the focal length ($f_{pixel}$) to keep the image sharp.
- **Problem**: This scaling exactly cancels out the perspective change, making the $p_{pixel}$ appear constant (~17.5px) regardless of distance.
- **Result**: Distance measurements "stagnate" at ~25cm.

### 3.2 Slat-Count Correction Theory (The "Proxy" Method)
While $p_{pixel}$ might stay constant due to auto-focus, the total **Number of Slats** visible in the frame (or a fixed ROI) still changes because the FOV (Field of View) shifts.
We use the **Slat Ratio** as a correction factor:

$$ \text{Correction} = \sqrt{\frac{\text{REF\_SLATS}}{\text{Total Slats Detected}}} $$

Where **REF_SLATS** is the count at the calibration distance (e.g., 27 slats at 25cm). 
- If fewer slats are seen (e.g., 15), the system knows the tray is actually further away and scales $D_{tray}$ up.

---

## 4. Stability & Filtering
To prevent "jumping" values in live video, the system applies **Temporal Smoothing**:
1. It maintains a rolling buffer of the last 7 frames.
2. It calculates the **Median** of these 7 frames.
3. This eliminates outliers caused by momentary glints or shadows.

---

## 5. Summary Table
| Feature | Theory / Tool | Purpose |
| :--- | :--- | :--- |
| **ROI** | YOLOv8 | Detect cup and isolate tray zones. |
| **Lines** | Hough Transform | Translate pixels into geometric slats. |
| **Accuracy** | Slat-Count Ratio | Compensate for Auto-Focus lens scaling. |
| **Stability** | Rolling Median | Remove frame-to-frame jitter. |
