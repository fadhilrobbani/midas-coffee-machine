# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-23 14-47-04

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
| **Average Cup Height** | **11.40 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **11.40 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **0.06 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 0.02 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 22.56 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 11.35 / 11.43 cm | Extremes recorded. |
| **Total Frames / Inferences** | 35 / 35 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

