# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-23 11-48-29

## 1. Parameters
Parameters used during this AI depth fusion session:

| Parameter | Value |
| :--- | :--- |
| **Physical Marker Size** | 1.5 cm |
| **Calibration Model** | 1-Point K-Factor |
| **Camera Focal Length** | 660.8 px |

## 2. Global Stability Summary
Statistical summary of cup height predictions gathered over the running frames:

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Average Cup Height** | **27.57 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **24.00 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **23.34 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 8.09 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 26.88 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 17.99 / 45.71 cm | Extremes recorded. |
| **Total Frames / Inferences** | 39 / 37 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

## 4. Screenshots
- ![screenshots/fusion_2026-04-23_114825.jpg](screenshots/fusion_2026-04-23_114825.jpg)
