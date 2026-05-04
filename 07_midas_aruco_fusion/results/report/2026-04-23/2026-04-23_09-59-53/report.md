# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-23 09-59-53

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
| **Average Cup Height** | **7.82 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **7.58 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **1.30 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 0.51 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 21.61 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 7.15 / 8.86 cm | Extremes recorded. |
| **Total Frames / Inferences** | 62 / 62 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

## 4. Screenshots
- ![screenshots/fusion_2026-04-23_095947.jpg](screenshots/fusion_2026-04-23_095947.jpg)
