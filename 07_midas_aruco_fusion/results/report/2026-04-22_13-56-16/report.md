# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-22 13-56-16

## 1. Parameters
Parameters used during this AI depth fusion session:

| Parameter | Value |
| :--- | :--- |
| **Physical Marker Size** | 1.5 cm |
| **Calibration Model** | 2-Point Linear (m=0.13702, c=0.11043) |
| **Camera Focal Length** | 660.8 px |

## 2. Global Stability Summary
Statistical summary of cup height predictions gathered over the running frames:

| Metric | Value | Description |
| :--- | :--- | :--- |
| **Average Cup Height** | **6.90 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **7.04 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **1.09 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 0.45 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 23.06 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 6.31 / 7.46 cm | Extremes recorded. |
| **Total Frames / Inferences** | 30 / 30 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

## 4. Screenshots
- ![screenshots/fusion_2026-04-22_135615.jpg](screenshots/fusion_2026-04-22_135615.jpg)
