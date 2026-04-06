# Tray Detector Validation Report (Method B / Hough Lines)

This report summarizes the results of the tray distance (D_tray) detection tests using **Method B** without YOLO (`--no-yolo`). The measurements were performed on three test images with the ground-truth distances indicated in their filenames.

## 1. Test Summary

| Test Filename | Real Distance (Ground Truth) | Measured Distance (D_tray_cm) | Error | Detected Slats (Left/Right) | Status |
|---|---|---|---|---|---|
| `test_tray23.7cm_rim16.1cm...jpg` | **23.7 cm** | **24.0 cm** | +0.3 cm (Good) | 12 / 15 | OK |
| `test_tray30.0cm_rim22.7cm...jpg` | **30.0 cm** | **25.14 cm** | -4.86 cm (Low) | 13 / 12 | OK |
| `test_tray31.8cm_rim23.8cm...jpg` | **31.8 cm** | **25.17 cm** | -6.63 cm (Low) | 14 / 12 | OK |

---

## 2. Results Analysis

Based on the table above, the slat grid detection algorithm (Hough Lines) **consistently and successfully identifies the slat lines** with an "OK" status and a high Confidence score (0.85). The Spatial Non-Maximum Suppression (NMS) filter is highly effective at trimming edge noise, averaging around ±12 to 15 detected slat lines.

However, there is a **mathematical calculation anomaly** when the tray is moved further away (at 30 cm and 31.8 cm). The calculated distance stagnates and remains around ~25.1 cm.

### Possible Causes for the Long-Distance Anomaly:
1. **Camera Auto-Focus Shift:** If the camera being used has an *auto-focus* feature, the optical focal length physically changes as the tray moves further away. This causes distant objects to appear proportionately larger on the sensor (maintaining a constant pixel pitch of ~17 pixels per slat). Consequently, the static `F_PIXEL` calibration multiplier loses its accuracy.
2. **Static Fallback Crop Limitations:** In the `--no-yolo` tests, the static fallback mask crops out the top (33%) and bottom (21%) of the image. When the camera is moved significantly further away, the physical proportion of the tray slats within the image shrinks or shifts, causing the slats to be cut off by the static tolerance boxes. This can distort the median gap distance calculation (*pitch IQR*).

## 3. Recommended Actions
To fix the mathematical measurement inconsistencies for varying geometries, we recommend the following:
- **Lock Camera Focus:** In production, ensure the camera/webcam focus parameter is not set to *auto*, but locked to an absolute distance or *fixed infinity*.
- **Use Cross-Reference Detection:** Enable YOLO (remove the `--no-yolo` argument) so the detector can generate a dynamic reference bounding box that adapts to the optical zoom-in/out of the frame, or cross-reference the gap-based distance with the YOLO mask scale (`Method A`) in the main detector node. 
