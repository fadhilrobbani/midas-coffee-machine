import numpy as np

def calc_height_1point(m_rim: float, m_tray: float, z_tray: float, K: float) -> float:
    if m_tray <= 0 or z_tray <= 0: return 0.0
    ratio = m_rim / m_tray
    if ratio <= 0: return 0.0
    cup_height = z_tray * (1.0 - K / ratio)
    return cup_height if cup_height > 0 else 0.0

def calc_height_2point(m_rim: float, m_tray: float, z_tray: float, m: float, c: float) -> float:
    if m_tray <= 0 or z_tray <= 0: return 0.0
    ratio = m_rim / m_tray
    if ratio <= 0: return 0.0
    cup_height = z_tray * (m * ratio + c)
    return cup_height if cup_height > 0 else 0.0

def calc_height_zgrid(m_rim: float, m_tray: float, z_tray: float, poly_K: list) -> float:
    if m_tray <= 0 or z_tray <= 0: return 0.0
    ratio = m_rim / m_tray
    if ratio <= 0: return 0.0
    K_live = float(np.polyval(poly_K, z_tray))
    cup_height = z_tray * (1.0 - K_live / ratio)
    return cup_height if cup_height > 0 else 0.0

def calc_height_bbox(m_rim: float, m_tray: float, z_tray: float, bbox: tuple,
                     m_ref: float, c_ref: float, ref_area: float) -> float:
    if m_tray <= 0 or z_tray <= 0: return 0.0
    ratio = m_rim / m_tray
    if ratio <= 0: return 0.0
    x1, y1, x2, y2 = bbox
    live_area = max(1.0, float((x2 - x1) * (y2 - y1)))
    scale = ref_area / live_area
    m_adj = m_ref * scale
    cup_height = z_tray * (m_adj * ratio + c_ref)
    return cup_height if cup_height > 0 else 0.0

def calc_height_geom(z_tray: float, bbox: tuple, focal_length_px: float, poly_Kgeom: list) -> float:
    if z_tray <= 0 or focal_length_px <= 0: return 0.0
    x1, y1, x2, y2 = bbox
    bbox_h_px = max(1.0, float(y2 - y1))
    K_live = float(np.polyval(poly_Kgeom, z_tray))
    cup_height = z_tray * (bbox_h_px / focal_length_px) * K_live
    return cup_height if cup_height > 0 else 0.0

def calc_height_bilateral_zgrid(m_rim: float, m_tray: float, z_tray: float, poly_m: list, poly_c: list) -> float:
    if m_tray <= 0 or z_tray <= 0: return 0.0
    ratio = m_rim / m_tray
    if ratio <= 0: return 0.0
    m_live = float(np.polyval(poly_m, z_tray))
    c_live = float(np.polyval(poly_c, z_tray))
    cup_height = z_tray * (m_live * ratio + c_live)
    return cup_height if cup_height > 0 else 0.0

def calc_height_analytic(z_tray: float, bbox: tuple, A: float, B: float) -> float:
    if z_tray <= 0: return 0.0
    x1, y1, x2, y2 = bbox
    bbox_h = float(y2 - y1)
    denom = (bbox_h + B)
    if abs(denom) < 1e-4: return 0.0
    cup_height = (bbox_h * z_tray - A) / denom
    return cup_height if cup_height > 0 else 0.0
