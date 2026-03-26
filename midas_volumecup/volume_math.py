import math
import numpy as np

def calculate_z_rim(m_rim: float, m_tray: float, a: float, b: float, c: float) -> float:
    ratio = m_rim / m_tray
    # Mathematically grounded Inverse Depth mapping (Z ≈ 1/d)
    if ratio + b == 0:
        return 0.0
    return (a / (ratio + b)) + c

def calculate_volume(z_rim: float, h_nozzle: float, w_pixels: float, focal_length: float):
    if z_rim <= 0 or focal_length <= 0:
        return 0.0, 0.0, 0.0
        
    h_cup = h_nozzle - z_rim
    w_real = (w_pixels * z_rim) / focal_length
    
    radius_cm = w_real / 2.0
    volume = math.pi * (radius_cm ** 2) * h_cup
    
    return h_cup, w_real, volume

def extract_signal_features(frame_grayscale, cam_config):
    """
    Extracts purely math properties from raw camera frame: R_trans (Signal A) and dark_ratio (Signal B)
    """
    row_means = np.mean(frame_grayscale, axis=1)
    
    bright_zone = row_means[cam_config.BRIGHT_ROW_START:cam_config.BRIGHT_ROW_END]
    if bright_zone.size == 0: return None, None
        
    I_max = np.max(bright_zone)
    threshold = I_max * 0.60
    
    R_trans = None
    for r in range(cam_config.SEARCH_ROW_START, cam_config.H - 1):
        if row_means[r] >= threshold > row_means[r + 1]:
            denom = row_means[r] - row_means[r + 1]
            if abs(denom) > 1e-6:
                R_trans = r + (row_means[r] - threshold) / denom
            else:
                R_trans = r
            break
            
    search_roi = frame_grayscale[cam_config.SEARCH_ROW_START:, :]
    dark_ratio = float(np.sum(search_roi < 40)) / search_roi.size
    
    return R_trans, dark_ratio

def measure_nozzle_height(frame_grayscale, cam_config, m, c, m_b_norm, c_b_norm):
    """
    Computes H_nozzle dynamically merging Signal A and Signal B.
    """
    R_trans, dark_ratio = extract_signal_features(frame_grayscale, cam_config)
    if R_trans is None: return None
        
    H_A = m * R_trans + c
    H_B = m_b_norm * dark_ratio + c_b_norm
    
    return 0.70 * H_A + 0.30 * H_B
