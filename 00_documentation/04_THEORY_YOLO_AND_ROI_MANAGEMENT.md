# Theory of Object Detection: YOLOv8 Region of Interest (ROI)

This document explains the role of the YOLOv8 neural network in the Midas Coffee Machine pipeline, specifically for masking and region-of-interest management.

---

## 1. Dual-Purpose Detection
The system utilizes a custom-trained **YOLOv8s** (Small) model to identify two critical objects in every frame:
1. **The Drip Tray**: The base surface where the coffee cup sits.
2. **The Cup Rim**: The top edge (opening) of the cup.

### 1.1 Why use YOLO for Tray Distance?
Traditional computer vision (like Hough Lines) is easily confused by background clutter or the coffee cup itself. YOLO provides a **Spatial Filter**:
- It identifies exactly where the tray is located.
- It generates a **Binary Mask** that tells the Hough Line detector: *"Only look for lines inside this box, but avoid the cup area."*

### 1.2 Why use YOLO for Cup Height?
To calculate the distance to the cup rim ($Z_{rim}$) using MiDaS, we need a reference point.
- YOLO detects the **Cup Rim Bounding Box**.
- The system then reads the median depth value from the MiDaS depth map *only* within this specific bounding box.
- This ensures that steam, shadows, or the machine nozzle don't interfere with the cup's depth reading.

---

## 2. Dynamic Masking Strategy

### 2.1 The "No-Fly Zone" (Cup Masking)
When a cup is placed on the tray, it obscures the horizontal slats. If the system tries to detect lines on the cup, the distance calculation will fail.
- **Implementation**: The YOLO `cup_rim` bounding box is subtracted from the `tray` mask.
- **Effect**: The system "blindly" ignores the cup, focusing only on the visible tray slats to the left and right of the cup.

### 2.2 Split-Zone Analysis (Left vs. Right)
Because the cup sits in the center, it splits the visible tray into two halves. 
- The system calculates $D_{tray}$ independently for the **Left Zone** and **Right Zone**.
- This provides redundancy: if one side is blocked by a spoon or handle, the other side can still provide an accurate distance reading.

---

## 3. Pixel-to-Real World Mapping
YOLO handles the **Pixel Measurements** ($W_{pixels}$):
- The horizontal width of the detection box for the cup rim is captured.
- This pixel width is then passed into the Pinhole Geometry formula to calculate the real physical diameter ($W_{real}$) in centimeters.

---

## 4. Summary of YOLO Outputs
| Detected Class | Purpose | Data Passed to Pipeline |
| :--- | :--- | :--- |
| **Tray** | Establish ROI | Bounding box, Binary Mask. |
| **Cup Rim** | Measure Rim Depth | Bounding box (for MiDaS ROI). |
| **Cup Rim** | Measure Diameter | Bounding box width (pixels). |
