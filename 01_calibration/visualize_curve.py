import yaml
import numpy as np
import matplotlib
matplotlib.use('Agg') # Safe for batch/headless runs
import matplotlib.pyplot as plt
import os

def visualize_calibration():
    # Correct relative paths for the new directory structure
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    config_path = os.path.join(root_dir, 'midas_calibration.yaml')
    output_path = os.path.join(os.path.dirname(__file__), 'calibration_curve.png')

    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found.")
        return

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Simplified Inverse Depth Parameters (Linear Regression on Inverted Axis)
    a = config.get('a', 0)
    b = config.get('b', 0) # b is usually 0 in our new pure linear model
    c = config.get('c', 0)

    # Use a range of ratios suitable for the Inverse Model (Z = a/R + c)
    r_values = np.linspace(0.5, 3.0, 500)
    z_values = (a / (r_values + b)) + c

    # Styling for a "WOW" effect
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
    
    # Plot the curve with a nice gradient-like look
    ax.plot(r_values, z_values, color='#00f2ff', linewidth=3, label=f'Inverse Fit (a={a:.1f}, c={c:.1f})')
    
    # Add some glow effect
    for i in range(1, 5):
        ax.plot(r_values, z_values, color='#00f2ff', linewidth=3+i, alpha=0.1)

    ax.set_title("MiDaS Calibration: Distance vs Ratio (Inverse Model)", fontfamily='sans-serif', fontsize=16, fontweight='bold', pad=20, color='white')
    ax.set_xlabel("AI Ratio (M_rim / M_tray)", fontfamily='sans-serif', fontsize=12, labelpad=10)
    ax.set_ylabel("Distance Z (mm)", fontfamily='sans-serif', fontsize=12, labelpad=10)
    
    ax.grid(True, linestyle='--', alpha=0.3, color='#444444')
    ax.legend(frameon=False, loc='upper right')
    
    # Customize spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#666666')
    ax.spines['bottom'].set_color('#666666')

    plt.tight_layout()
    plt.savefig(output_path, transparent=False, facecolor='#111111')
    print(f"Plot saved to {output_path}")

if __name__ == "__main__":
    visualize_calibration()
