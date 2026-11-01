from __future__ import annotations

import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quran_source import (  # noqa: E402
    QuranSourceError,
    get_verified_verse,
    get_verified_verses,
    load_tanzil_bytes,
    parse_verse_rows,
)

AYAH_COUNTS = [7,286,200,176,120,165,206,75,129,109,123,111,43,52,99,128,111,110,98,135,112,78,118,64,77,227,93,88,69,60,34,30,73,54,45,83,182,88,75,85,54,53,89,59,37,35,38,29,18,45,60,49,62,55,78,96,29,22,24,13,14,11,11,18,12,12,30,52,52,44,28,28,20,56,40,31,50,40,46,42,29,19,36,25,22,17,19,26,30,20,15,21,11,8,8,19,5,8,8,11,11,8,3,9,5,4,7,3,6,3,5,4,5,6]


def synthetic_metadata() -> bytes:
    root = ET.Element("quran-data")
    for number, count in enumerate(AYAH_COUNTS, start=1):
        ET.SubElement(
            root,
            "sura",
            {"index": str(number), "ayas": str(count), "name": f"سورة اختبار {number}"},
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def synthetic_text() -> bytes:
    lines = [
        "# Tanzil Quran Text",
        "# Copyright (C) 2007-2021 Tanzil Project",
        "# License: Creative Commons Attribution 3.0",
        "# This text is verbatim; CHANGING IT IS NOT ALLOWED.",
    ]
    for surah_number, count in enumerate(AYAH_COUNTS, start=1):
        for ayah_number in range(1, count + 1):
            # Deliberately synthetic text: these are parser tests, not Qur'anic content.
            lines.append(f"{surah_number}|{ayah_number}|نص اختبار {surah_number}-{ayah_number}")
    return ("\n".join(lines) + "\n").encode("utf-8")


class QuranSourceTests(unittest.TestCase):
    def test_complete_dataset_parses_and_preserves_text(self):
        surahs, verses = load_tanzil_bytes(synthetic_text(), synthetic_metadata())
        self.assertEqual(len(surahs), 114)
        self.assertEqual(len(verses), 6236)
        self.assertEqual(verses["2:255"], "نص اختبار 2-255")
        self.assertEqual(surahs[2]["ayah_count"], 286)

    def test_missing_copyright_notice_is_rejected(self):
        text = synthetic_text().replace(
            b"# This text is verbatim; CHANGING IT IS NOT ALLOWED.\n", b"# terms omitted\n"
        )
        with self.assertRaises(QuranSourceError):
            load_tanzil_bytes(text, synthetic_metadata())

    def test_duplicate_ayah_is_rejected(self):
        text = synthetic_text() + b"2|255|duplicate\n"
        with self.assertRaisesRegex(QuranSourceError, "Duplicate ayah"):
            load_tanzil_bytes(text, synthetic_metadata())

    def test_incomplete_corpus_is_rejected(self):
        rows = synthetic_text().decode("utf-8").splitlines()
        rows.pop()
        with self.assertRaisesRegex(QuranSourceError, "Expected 6236"):
            load_tanzil_bytes(("\n".join(rows) + "\n").encode("utf-8"), synthetic_metadata())

    def test_local_verse_lookup_uses_the_verified_source(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            (data_dir / "tanzil-uthmani.txt").write_bytes(synthetic_text())
            (data_dir / "quran-data.xml").write_bytes(synthetic_metadata())
            verse, surah = get_verified_verse(data_dir, 1, 1)
        self.assertEqual(verse, "نص اختبار 1-1")
        self.assertEqual(surah, "سورة اختبار 1")

    def test_consecutive_verse_range_preserves_order_and_source_strings(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            (data_dir / "tanzil-uthmani.txt").write_bytes(synthetic_text())
            (data_dir / "quran-data.xml").write_bytes(synthetic_metadata())
            verses, surah = get_verified_verses(data_dir, 105, 1, 5)
        self.assertEqual(verses, [f"نص اختبار 105-{n}" for n in range(1, 6)])
        self.assertEqual(surah, "سورة اختبار 105")

    def test_invalid_verse_range_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            (data_dir / "tanzil-uthmani.txt").write_bytes(synthetic_text())
            (data_dir / "quran-data.xml").write_bytes(synthetic_metadata())
            with self.assertRaisesRegex(QuranSourceError, "ascending order"):
                get_verified_verses(data_dir, 105, 5, 1)


if __name__ == "__main__":
    unittest.main()
