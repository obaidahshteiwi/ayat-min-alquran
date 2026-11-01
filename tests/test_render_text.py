from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from render_short import (  # noqa: E402
    arabic_indic_number,
    build_display_items,
    format_ayah_reference,
    split_tanzil_basmala,
)


BASMALA = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
AL_FIL_1 = "أَلَمْ تَرَ كَيْفَ فَعَلَ رَبُّكَ بِأَصْحَابِ الْفِيلِ"


class QuranRenderTextTests(unittest.TestCase):
    def test_arabic_indic_numbers(self):
        self.assertEqual(arabic_indic_number(105), "١٠٥")

    def test_tanzil_basmala_is_separated_without_rewriting_it(self):
        source = f"{BASMALA} {AL_FIL_1}"
        self.assertEqual(split_tanzil_basmala(source), (BASMALA, AL_FIL_1))

    def test_surah_al_fil_display_has_unumbered_basmala_and_numbered_ayahs(self):
        items = build_display_items(
            [f"{BASMALA} {AL_FIL_1}", "أَلَمْ يَجْعَلْ كَيْدَهُمْ فِي تَضْلِيلٍ"],
            105,
            1,
        )
        self.assertEqual(items[0], ("basmala", BASMALA))
        self.assertIn("۝١", items[1][1])
        self.assertIn(AL_FIL_1, items[1][1])
        self.assertIn("۝٢", items[2][1])

    def test_fatihah_basmala_remains_numbered_as_ayah_one(self):
        items = build_display_items([BASMALA], 1, 1)
        self.assertEqual(items, [("ayah", f"{BASMALA} ۝١")])

    def test_tawbah_does_not_add_a_basmala_block(self):
        items = build_display_items(["بَرَاءَةٌ مِنَ اللَّهِ"], 9, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], "ayah")

    def test_reference_uses_unambiguous_arabic_number_range(self):
        self.assertEqual(
            format_ayah_reference("الفيل", 1, 5),
            "سورة الفيل • من الآية ١ إلى الآية ٥",
        )


if __name__ == "__main__":
    unittest.main()
