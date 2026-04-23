# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-22 11-57-34

## 1. Parameters
Parameters used during this AI depth fusion session:

| Parameter | Value |
| :--- | :--- |
| **Physical Marker Size** | 1.5 cm |
| **Calibration Model** | 1-Point K-Factor (K=0.79388) |
| **Camera Focal Length** | 660.8 px |

## 2. Global Stability Summary
Statistical summary of cup height predictions gathered over the running frames:

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Average Cup Height** | **8.26 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **8.25 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **0.76 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 0.27 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 24.92 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 7.86 / 8.98 cm | Extremes recorded. |
| **Total Frames / Inferences** | 30 / 29 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

