import math

def calculate_z_rim(m_rim, m_tray, a, b, c):
    """
    Calculate physical Z_rim distance using quadratic polynomial over depth ratio.
    Z_rim = a * (ratio^2) + b * ratio + c
    """
    ratio = m_rim / m_tray if m_tray > 0 else 0
    return a * (ratio ** 2) + b * ratio + c

def calculate_volume(z_rim, h_nozzle, w_pixels, f):
    """
    Calculate cup height, physical width, and estimated volume.
    Volume is computed treating the cup as a simple cylinder based on the rim diameter.
    Returns: (h_cup_cm, w_real_cm, volume_mL)
    """
    h_cup = h_nozzle - z_rim
    w_real = (w_pixels * z_rim) / f if f > 0 else 0
    
    # Volume in mL or cm^3
    radius_cm = w_real / 2.0
    volume = math.pi * (radius_cm ** 2) * h_cup
    
    return h_cup, w_real, volume
