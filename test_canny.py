import cv2, numpy as np, math

img = cv2.imread('picture_2026-04-02_11-56-36.jpg')
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
enhanced = clahe.apply(gray)
blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)

edges = cv2.Canny(blurred, 20, 80)

h, w = img.shape[:2]
box_y1 = int(h * 0.33)
box_y2 = int(h * 0.79)
mid_x = w // 2
skip_radius = 80
lx2 = max(0, mid_x - skip_radius)
lx1 = max(0, lx2 - 200)

strict_mask = np.zeros_like(edges)
strict_mask[box_y1:box_y2, lx1:lx2] = 255
edges_masked = cv2.bitwise_and(edges, strict_mask)

lines = cv2.HoughLinesP(edges_masked, 1, np.pi/180, 25, minLineLength=25, maxLineGap=15)
print(f"Mask left box: x={lx1}..{lx2}, y={box_y1}..{box_y2}")

if lines is not None:
    print(f"Found {len(lines)} raw lines in left box")
    count_horiz = 0
    for l in lines:
        x1, y1, x2, y2 = l[0]
        angle = abs(math.degrees(math.atan2(y2-y1, x2-x1)))
        if angle < 10 or angle > 170:
            count_horiz += 1
    print(f"Horizontal lines: {count_horiz}")
else:
    print("Found 0 lines")

