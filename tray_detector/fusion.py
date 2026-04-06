"""
fusion.py — Fusi Metode & Hierarki Eksekusi

Menggabungkan hasil dari Metode A, B, C menggunakan hierarki prioritas
dan weighted average untuk menghasilkan D_tray_cm final.

Hierarki:
  1. B + C keduanya valid → weighted average (B primary, C validasi)
  2. B saja valid → gunakan B
  3. C saja valid → gunakan C
  4. A saja → gunakan A (last resort)
  5. Tidak ada → INSUFFICIENT_DATA
"""


def fuse_results(result_a, result_b, result_c):
    """
    Fusi hasil dari ketiga metode sesuai hierarki prioritas.

    Args:
        result_a: dict dari method_a atau None
        result_b: dict dari method_b atau None
        result_c: dict dari method_c atau None

    Returns:
        dict: output schema final dengan semua field
    """
    b_valid = (result_b is not None and
               result_b.get("D_tray_cm") is not None and
               result_b.get("confidence", 0) > 0)

    c_valid = (result_c is not None and
               result_c.get("D_tray_cm") is not None and
               result_c.get("confidence", 0) > 0)

    a_valid = (result_a is not None and
               result_a.get("D_tray_cm") is not None and
               result_a.get("confidence", 0) > 0)

    # ── Prioritas 1: B + C keduanya valid ────────────────────────────────
    if b_valid and c_valid:
        D_b = result_b["D_tray_cm"]
        D_c = result_c["D_tray_cm"]
        conf_b = result_b["confidence"]
        conf_c = result_c["confidence"]

        D_fused = (D_b * conf_b + D_c * conf_c) / (conf_b + conf_c)
        conf_fused = min((conf_b + conf_c) / 2.0 * 1.1, 1.0)  # bonus fusi

        return _build_output(
            D_tray_cm=round(D_fused, 2),
            method_used="B+C",
            confidence=round(conf_fused, 3),
            status=result_b.get("status", "OK"),
            result_b=result_b,
            notes=None,
        )

    # ── Prioritas 2: B saja ──────────────────────────────────────────────
    if b_valid:
        return _build_output(
            D_tray_cm=result_b["D_tray_cm"],
            method_used="B",
            confidence=result_b["confidence"],
            status=result_b.get("status", "OK"),
            result_b=result_b,
            notes=result_b.get("notes"),
        )

    # ── Prioritas 3: C saja ──────────────────────────────────────────────
    if c_valid:
        return _build_output(
            D_tray_cm=result_c["D_tray_cm"],
            method_used="C",
            confidence=result_c["confidence"],
            status=result_c.get("status", "OK"),
            result_b=None,
            notes=result_c.get("notes"),
        )

    # ── Prioritas 4: A saja (last resort) ────────────────────────────────
    if a_valid:
        return _build_output(
            D_tray_cm=result_a["D_tray_cm"],
            method_used="A",
            confidence=result_a["confidence"],
            status=result_a.get("status", "OK"),
            result_b=None,
            notes=result_a.get("notes"),
        )

    # ── Gagal: tidak ada data valid ──────────────────────────────────────
    return _build_output(
        D_tray_cm=None,
        method_used="NONE",
        confidence=0.0,
        status="INSUFFICIENT_DATA",
        result_b=result_b,
        notes="Semua metode gagal — tidak ada data valid",
    )


def _build_output(D_tray_cm, method_used, confidence, status,
                   result_b=None, notes=None):
    """Bangun output dict sesuai schema dokumen."""
    return {
        "D_tray_cm": D_tray_cm,
        "method_used": method_used,
        "confidence": confidence,
        "status": status,
        "D_left_cm": result_b["D_left_cm"] if result_b else None,
        "D_right_cm": result_b["D_right_cm"] if result_b else None,
        "lines_left": result_b["lines_left"] if result_b else 0,
        "lines_right": result_b["lines_right"] if result_b else 0,
        "notes": notes,
    }
