# ArUco + MiDaS Fusion Session Report

**Date/Time:** 2026-04-23 11-28-38

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
| **Average Cup Height** | **13.53 cm** | Mean of all valid predictions. |
| **Median Height (P50)** | **12.24 cm** | Most representative single value. |
| **Precision Error (P95−P5)** | **8.51 cm** | 90% of readings fall within this range. |
| **Standard Deviation ($\sigma$)** | 3.50 cm | Consistency / jitter of the AI model. |
| **Tray Anchor Depth (Z)** | 24.07 cm | Average physical depth of the tray. |
| **Minimum / Maximum Height** | 10.08 / 24.33 cm | Extremes recorded. |
| **Total Frames / Inferences** | 38 / 38 | Pipeline tracking efficiency. |

## 3. Visual Evidence
### Depth Tracking Chart
![Session Chart](session_chart.png)

## 4. Screenshots
- ![screenshots/fusion_2026-04-23_112744.jpg](screenshots/fusion_2026-04-23_112744.jpg)
- ![screenshots/fusion_2026-04-23_112756.jpg](screenshots/fusion_2026-04-23_112756.jpg)
- ![screenshots/fusion_2026-04-23_112830.jpg](screenshots/fusion_2026-04-23_112830.jpg)
