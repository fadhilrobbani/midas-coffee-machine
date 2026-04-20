"""
tray_detector — Pipeline Deteksi Jarak Kamera ke Tray (D_tray_cm)
Mesin Kopi Jura — Computer Vision Research Division

Tiga metode hierarkis:
  A) Apparent Width Tray (fallback)
  B) Horizontal Slat Pitch (primary)
  C) Homografi 4 Corner + PnP (backup presisi)
"""

from .pipeline import TrayDistancePipeline

__all__ = ["TrayDistancePipeline"]
__version__ = "1.0.0"
