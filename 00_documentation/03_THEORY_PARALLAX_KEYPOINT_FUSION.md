# Single-View Parallax Keypoint Metrology: Theory & Implementation

This document outlines the theoretical foundation and practical implementation of the **Parallax Keypoint Method**. This approach calculates absolute physical volume (height and diameter) of an unknown frustum (coffee cup) using a single, static RGB camera and an ArUco marker, entirely bypassing the need for Monocular Depth AI (e.g., MiDaS) and resolving the optical "Catch-22" ambiguity.

---

## 1. The Pinhole "Catch-22" & Depth AI Failure

Traditional single-camera systems attempting to measure an object of unknown size face a projective ambiguity:
$$ W_{pixels} = \frac{f \cdot W_{real}}{Z} $$
To solve for the physical diameter ($W_{real}$), the exact distance to the cup rim ($Z$) must be known. To solve for $Z$, $W_{real}$ must be known. 

Previous iterations of this project attempted to break this Catch-22 by using **Monocular Depth AI (MiDaS)** to guess $Z$ via a Multivariate Linear Regression model. However, AI depth models output relative disparities ($M = a/Z + b$), where the shift ($b$) constantly fluctuates depending on the scene's "global context". When different cups (different colors, shapes, materials) are placed, the context changes, the shift $b$ breaks, and the depth estimation completely fails.

## 2. The Parallax Shift Principle

Instead of relying on AI to guess depth from color gradients, we rely on **pure geometric perspective**. 

In industrial coffee machines, the camera is typically mounted *adjacent* to the nozzle (e.g., offset by 4-5 cm). The cup is placed directly under the nozzle. Because the camera is physically offset from the cup's vertical center axis, the camera views the cup at a slight angle. 

Due to this perspective offset, the center of the cup's top rim and the center of the cup's bottom base will **not align vertically** in the 2D image. The pixel distance between these two centers is directly proportional to the physical height of the cup. This phenomenon is known as **Parallax Shift**.

---

## 3. Core Mathematical Derivation

### 3.1. Assumptions & Prerequisites
- The camera intrinsic matrix is calibrated, providing focal lengths ($f_x, f_y$) and the optical center / principal point ($c_x, c_y$).
- The physical distance from the camera to the drip tray ($Z_{tray}$) is dynamically known via an ArUco marker.
- The cup stands perfectly vertical on the drip tray.

### 3.2. Deriving the Height ($H$)
Let the vertical central axis of the cup be located at a physical distance $X_c$ from the camera's optical axis.
- The bottom center of the cup is at coordinate $(X_c, Y_c, Z_{tray})$.
- The top center of the cup is at coordinate $(X_c, Y_c, Z_{rim})$.

When projected onto the 2D image sensor, their distances from the image's optical center ($c_x, c_y$) in pixels are:
$$ U_{bot} = \frac{\sqrt{(f_x \cdot X_c)^2 + (f_y \cdot Y_c)^2}}{Z_{tray}} $$
$$ U_{top} = \frac{\sqrt{(f_x \cdot X_c)^2 + (f_y \cdot Y_c)^2}}{Z_{rim}} $$

Notice the numerator is identical in both equations. Let's isolate it:
$$ U_{bot} \cdot Z_{tray} = U_{top} \cdot Z_{rim} $$

Rearranging for $Z_{rim}$:
$$ Z_{rim} = Z_{tray} \cdot \left( \frac{U_{bot}}{U_{top}} \right) $$

Since the absolute physical height of the cup ($H$) is the distance from the tray to the rim:
$$ H = Z_{tray} - Z_{rim} $$
$$ H = Z_{tray} \cdot \left( 1 - \frac{U_{bot}}{U_{top}} \right) $$

**This breakthrough formula calculates exact height using only the ArUco tray distance and 2 pixel coordinates, entirely independent of the cup's actual diameter or shape.**

### 3.3. Deriving the Diameter ($W_{real}$)
Once $Z_{rim}$ is solved, the Catch-22 is broken. The physical diameter of the top rim can be calculated using the standard pinhole equation:
$$ W_{real} = \frac{W_{pixels\_top} \cdot Z_{rim}}{f_x} $$

---

## 4. End-to-End System Pipeline

The implementation shifts from Depth AI (MiDaS) to Keypoint AI (YOLO-Pose):

1. **Fast Track (ArUco):** Continuously tracks the marker on the drip tray to provide a highly stable $Z_{tray}$.
2. **Pose Inference (YOLOv8-Pose):** To avoid the difficulty of human annotators guessing an "invisible center" in the air or behind the cup, the model is trained to detect 4 highly visible physical edges:
   - $P_{top\_left}$: Leftmost edge of the top rim.
   - $P_{top\_right}$: Rightmost edge of the top rim.
   - $P_{bot\_left}$: Leftmost point where the bottom base touches the tray.
   - $P_{bot\_right}$: Rightmost point where the bottom base touches the tray.
3. **Geometry Calculation:**
   - Calculate the invisible centers using midpoints:
     - $P_{top\_center} = \text{Midpoint}(P_{top\_left}, P_{top\_right})$
     - $P_{bot\_center} = \text{Midpoint}(P_{bot\_left}, P_{bot\_right})$
   - Calculate $U_{top}$ (distance from $P_{top\_center}$ to $(c_x, c_y)$).
   - Calculate $U_{bot}$ (distance from $P_{bot\_center}$ to $(c_x, c_y)$).
   - Compute height $H$ using the Parallax formula.
   - Compute top rim pixel width $W_{pixels\_top}$ = distance between $P_{left}$ and $P_{right}$.
   - Compute real diameter $W_{real}$ using the Pinhole formula.
4. **Volume Estimation:** Apply the standard frustum/cylinder volume formula using $H$ and $W_{real}$.

---

## 5. Weaknesses & Limitations

While mathematically robust, this method is bound by specific physical constraints:

1. **The "Dead Center" Blindspot:** 
   If the cup's vertical axis aligns *perfectly* with the camera's optical axis (i.e., the cup is exactly dead-center under the lens), $U_{top}$ and $U_{bot}$ both become $0$. The formula attempts to divide by zero ($0/0$) and mathematically collapses. **Mitigation:** Ensure the camera is physically mounted at a slight offset from the nozzle.
2. **Keypoint Sensitivity:**
   The formula heavily relies on the precision of the YOLO-Pose model. A jitter of 2-3 pixels on the $P_{bot\_center}$ estimation can translate to a few millimeters of error in the final height, especially if the camera focal length is short.
3. **Bottom Base Occlusion:**
   For extremely wide cups, the top rim may physically obscure the view of the bottom base where it touches the tray. The YOLO-Pose AI must "infer" or guess the location of the bottom center based on the visible outer edges of the base. If the inference is poor, accuracy drops.
4. **Strict Principal Point Calibration:**
   The algorithm assumes the optical center $(c_x, c_y)$ is perfectly calibrated. Using the naive image center `(width/2, height/2)` without proper checkerboard calibration will skew the $U$ distances and warp the height result.

---

## 6. Dataset & Training Requirements

Unlike Semantic Depth models (MiDaS) which require massive, varied datasets to generalize context, YOLOv8-Pose models learn rigid geometric structures.

- **Dataset Size:** Because coffee cups share a very universal structure, you only need **300 to 500 annotated images**.
- **Variance Needed:** Ensure the dataset contains:
  - Various cup types (clear plastic, paper, ceramic, matte, glossy).
  - Various lighting conditions (ambient light, machine LED on/off).
  - Cups placed at different positions on the tray (to train the AI on different perspective distortions).
- **Annotation Method:** Use tools like CVAT or Roboflow. Label the object as `cup` and place the 4 distinct keypoints mentioned in Section 4. Even if the bottom center is slightly occluded, place the keypoint where it logically should be to force the network to learn structural inference.
