"""
generate_marker.py — Generate ArUco Marker Image (Siap Print)

Menghasilkan file PNG marker ArUco yang bisa dicetak dan ditempelkan
pada tray mesin kopi sebagai referensi deteksi jarak.

Contoh:
  python generate_marker.py
  python generate_marker.py --id 42 --size 400 --dictionary DICT_5X5_100
  python generate_marker.py --id 0 --size 600 --output my_marker.png
"""

import argparse
import os
import cv2

# ── Dictionary mapping ──────────────────────────────────────────────────
DICT_MAP = {
    "DICT_4X4_50":   cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100":  cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250":  cv2.aruco.DICT_4X4_250,
    "DICT_5X5_50":   cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100":  cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250":  cv2.aruco.DICT_5X5_250,
    "DICT_6X6_50":   cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100":  cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250":  cv2.aruco.DICT_6X6_250,
    "DICT_7X7_50":   cv2.aruco.DICT_7X7_50,
    "DICT_7X7_100":  cv2.aruco.DICT_7X7_100,
    "DICT_7X7_250":  cv2.aruco.DICT_7X7_250,
}


def generate_marker(marker_id=0, size_px=400, dictionary_name="DICT_4X4_50",
                    border_bits=1, output_path=None):
    """
    Generate ArUco marker dan simpan sebagai PNG.

    Args:
        marker_id: ID marker (0-49 untuk DICT_4X4_50)
        size_px: Ukuran marker dalam piksel (tanpa border putih)
        dictionary_name: Nama dictionary ArUco
        border_bits: Jumlah bit border hitam di sekeliling marker
        output_path: Path output file PNG

    Returns:
        Path file yang disimpan
    """
    if dictionary_name not in DICT_MAP:
        raise ValueError(f"Dictionary tidak dikenal: {dictionary_name}\n"
                         f"Pilihan: {list(DICT_MAP.keys())}")

    aruco_dict = cv2.aruco.Dictionary_get(DICT_MAP[dictionary_name])

    # Generate marker image
    marker_img = cv2.aruco.drawMarker(aruco_dict, marker_id, size_px, borderBits=border_bits)

    # Tambah border putih (untuk kemudahan pemotongan saat print)
    border_px = size_px // 4
    import numpy as np
    canvas = np.ones((size_px + 2 * border_px, size_px + 2 * border_px), dtype=np.uint8) * 255
    canvas[border_px:border_px + size_px, border_px:border_px + size_px] = marker_img

    # Default output path
    if output_path is None:
        output_dir = os.path.join(os.path.dirname(__file__), "markers")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir,
                                   f"aruco_{dictionary_name}_id{marker_id}_{size_px}px.png")

    cv2.imwrite(output_path, canvas)
    print(f"✅ Marker generated:")
    print(f"   Dictionary : {dictionary_name}")
    print(f"   ID         : {marker_id}")
    print(f"   Size       : {size_px}px (+ {border_px}px white border each side)")
    print(f"   Total      : {canvas.shape[1]}x{canvas.shape[0]}px")
    print(f"   Saved to   : {output_path}")
    print()
    print(f"💡 Tips: Print marker ini dan ukur sisi hitamnya (tanpa border putih).")
    print(f"   Gunakan --marker-size <cm> saat menjalankan run_aruco.py")
    print(f"   sesuai ukuran fisik cetakan.")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate ArUco Marker Image (siap print)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python generate_marker.py                          # Default: DICT_4X4_50, ID=0, 400px
  python generate_marker.py --id 5 --size 600        # ID 5, ukuran 600px
  python generate_marker.py --dictionary DICT_5X5_50 # Dictionary 5x5

Dictionary yang tersedia:
  DICT_4X4_50   (rekomendasi: paling tangguh untuk blur/kecil)
  DICT_4X4_100, DICT_4X4_250
  DICT_5X5_50, DICT_5X5_100, DICT_5X5_250
  DICT_6X6_50, DICT_6X6_100, DICT_6X6_250
  DICT_7X7_50, DICT_7X7_100, DICT_7X7_250
        """,
    )

    parser.add_argument("--id", type=int, default=0,
                        help="Marker ID (default: 0)")
    parser.add_argument("--size", type=int, default=400,
                        help="Ukuran marker dalam piksel (default: 400)")
    parser.add_argument("--dictionary", type=str, default="DICT_4X4_50",
                        choices=list(DICT_MAP.keys()),
                        help="ArUco dictionary (default: DICT_4X4_50)")
    parser.add_argument("--border-bits", type=int, default=1,
                        help="Border bits (default: 1)")
    parser.add_argument("--output", type=str, default=None,
                        help="Path output file PNG")

    args = parser.parse_args()
    generate_marker(
        marker_id=args.id,
        size_px=args.size,
        dictionary_name=args.dictionary,
        border_bits=args.border_bits,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
