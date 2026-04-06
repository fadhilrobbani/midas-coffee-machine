import os
import sys
import cv2
import numpy as np
import argparse

# Ensure project root is in path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from midas_volumecup.depth import MidasDepthEstimator

def test_image(image_path, output_path=None):
    if not os.path.exists(image_path):
        print(f"Error: Image not found at {image_path}")
        return

    # Initialize Estimator
    print("Loading MiDaS Model...")
    estimator = MidasDepthEstimator()

    # Load Image
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not read image at {image_path}")
        return

    print(f"Processing {image_path}...")
    # Process Depth
    depth = estimator.process(img)

    # Normalize for visualization
    depth_norm = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    heatmap = cv2.applyColorMap(depth_norm, cv2.COLORMAP_INFERNO)

    # Combine Side-by-Side
    combined = np.hstack((img, heatmap))

    # Save or Show
    if output_path is None:
        output_path = "output_test_side_by_side.png"
    
    cv2.imwrite(output_path, combined)
    print(f"Success! Side-by-side result saved to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test MiDaS on a single image and generate side-by-side comparison.")
    parser.add_argument("-i", "--input", required=True, help="Path to input image")
    parser.add_argument("-o", "--output", default="output_depth_test.png", help="Path to save the result")
    
    args = parser.parse_args()
    test_image(args.input, args.output)
