"""Read Tanzil Uthmani text without altering the source verse strings."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

TOTAL_SURAHS = 114
TOTAL_AYAHS = 6236
REQUIRED_NOTICE = (
    "TANZIL QURAN TEXT",
    "COPYRIGHT (C) 2007-2021 TANZIL PROJECT",
    "CHANGING IT IS NOT ALLOWED",
)


class QuranSourceError(ValueError):
    """Raised when the local Tanzil source files are missing or inconsistent."""


def parse_metadata(metadata_bytes: bytes) -> dict[int, dict[str, Any]]:
    try:
        root = ET.fromstring(metadata_bytes)
    except ET.ParseError as exc:
        raise QuranSourceError(f"Invalid Tanzil metadata XML: {exc}") from exc

    surahs: dict[int, dict[str, Any]] = {}
    for node in root.findall(".//sura"):
        try:
            number = int(node.attrib["index"])
            ayah_count = int(node.attrib["ayas"])
            arabic_name = node.attrib["name"]
        except (KeyError, ValueError) as exc:
            raise QuranSourceError("A Tanzil surah metadata record is incomplete.") from exc

        if number in surahs or not 1 <= number <= TOTAL_SURAHS or not arabic_name:
            raise QuranSourceError(f"Invalid or duplicate surah metadata: {number}")
        surahs[number] = {"name": arabic_name, "ayah_count": ayah_count}

    if len(surahs) != TOTAL_SURAHS or sorted(surahs) != list(range(1, TOTAL_SURAHS + 1)):
        raise QuranSourceError(f"Expected metadata for exactly {TOTAL_SURAHS} surahs.")

    return surahs


def parse_verse_rows(text_bytes: bytes, surahs: dict[int, dict[str, Any]]) -> dict[str, str]:
    try:
        source_text = text_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise QuranSourceError("Tanzil text is not valid UTF-8.") from exc

    upper_text = source_text.upper()
    missing_notice = [part for part in REQUIRED_NOTICE if part not in upper_text]
    if missing_notice:
        raise QuranSourceError(
            "The Tanzil copyright notice was not found in the downloaded text. "
            "Refusing to accept an unverified or incomplete file."
        )

    verses: dict[str, str] = {}
    for line_number, raw_line in enumerate(source_text.splitlines(), start=1):
        if not raw_line or raw_line.startswith("#"):
            continue

        fields = raw_line.split("|", 2)
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
            continue

        surah_number = int(fields[0])
        ayah_number = int(fields[1])
        verse_text = fields[2]  # Keep the Qur'anic source string verbatim.

        if surah_number not in surahs:
            raise QuranSourceError(f"Unknown surah number on line {line_number}.")
        if not 1 <= ayah_number <= surahs[surah_number]["ayah_count"]:
            raise QuranSourceError(f"Invalid ayah number on line {line_number}.")
        if not verse_text:
            raise QuranSourceError(f"Empty ayah text on line {line_number}.")

        key = f"{surah_number}:{ayah_number}"
        if key in verses:
            raise QuranSourceError(f"Duplicate ayah record: {key}")
        verses[key] = verse_text

    if len(verses) != TOTAL_AYAHS:
        raise QuranSourceError(
            f"Expected {TOTAL_AYAHS} ayahs, but found {len(verses)}."
        )

    for surah_number, info in surahs.items():
        expected = {f"{surah_number}:{n}" for n in range(1, info["ayah_count"] + 1)}
        actual = {key for key in verses if key.startswith(f"{surah_number}:")}
        if actual != expected:
            raise QuranSourceError(
                f"Surah {surah_number} has missing or unexpected ayah numbers."
            )

    return verses


def load_tanzil_bytes(text_bytes: bytes, metadata_bytes: bytes):
    surahs = parse_metadata(metadata_bytes)
    verses = parse_verse_rows(text_bytes, surahs)
    return surahs, verses


def load_local_tanzil(data_dir: Path):
    text_path = data_dir / "tanzil-uthmani.txt"
    metadata_path = data_dir / "quran-data.xml"
    if not text_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError(
            "Tanzil files are missing. Run: python scripts/fetch_tanzil.py"
        )
    return load_tanzil_bytes(text_path.read_bytes(), metadata_path.read_bytes())



def get_verified_verses(
    data_dir: Path,
    surah_number: int,
    first_ayah: int,
    last_ayah: int,
) -> tuple[list[str], str]:
    """Return a consecutive range of unmodified verse strings from Tanzil."""
    surahs, verses = load_local_tanzil(data_dir)
    if surah_number not in surahs:
        raise QuranSourceError(f"Unknown surah number: {surah_number}")
    if first_ayah < 1 or last_ayah < first_ayah:
        raise QuranSourceError("The ayah range must be positive and in ascending order.")
    if last_ayah > surahs[surah_number]["ayah_count"]:
        raise QuranSourceError(
            f"Surah {surah_number} has only {surahs[surah_number]['ayah_count']} ayahs."
        )

    keys = [f"{surah_number}:{number}" for number in range(first_ayah, last_ayah + 1)]
    try:
        selected = [verses[key] for key in keys]
    except KeyError as exc:
        raise QuranSourceError(f"Missing ayah in requested range: {exc.args[0]}") from exc
    return selected, surahs[surah_number]["name"]


def get_verified_verse(data_dir: Path, surah_number: int, ayah_number: int):
    selected, surah_name = get_verified_verses(
        data_dir, surah_number, ayah_number, ayah_number
    )
    return selected[0], surah_name
