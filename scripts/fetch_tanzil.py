#!/usr/bin/env python3
"""Fetch the original Tanzil Uthmani text and metadata for local use.

The downloaded Qur'anic text is stored verbatim. This script does not edit it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quran_source import load_tanzil_bytes  # noqa: E402

TEXT_ENDPOINT = "https://tanzil.net/pub/download/index.php"
METADATA_ENDPOINT = "https://tanzil.net/res/text/metadata/quran-data.xml"

TEXT_OPTIONS = {
    "quranType": "uthmani",
    "outType": "txt-2",
    "agree": "true",
    "marks": "true",
    "sajdah": "true",
    "rub": "true",
    "tatweel": "true",
}


def download(url: str) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": "AyatMinAlQuran/1.0 (personal Quran Shorts project)"},
    )
    with urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"Download failed with HTTP {response.status}: {url}")
        return response.read()


def download_text(form_data: dict[str, str]) -> bytes:
    # Tanzil's download page expects a form POST; a GET returns the HTML page,
    # not the selected Quran text file.
    body = urlencode(form_data).encode("ascii")
    request = Request(
        TEXT_ENDPOINT,
        data=body,
        headers={
            "User-Agent": "AyatMinAlQuran/1.0 (personal Quran Shorts project)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://tanzil.net/pub/download/",
        },
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(
                f"Tanzil text download failed with HTTP {response.status}."
            )
        return response.read()


def main() -> int:
    print("Downloading the original Tanzil Uthmani text and chapter metadata...")
    text_bytes = download_text(TEXT_OPTIONS)
    metadata_bytes = download(METADATA_ENDPOINT)

    # Validate both files before writing either one to disk.
    surahs, verses = load_tanzil_bytes(text_bytes, metadata_bytes)
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "tanzil-uthmani.txt").write_bytes(text_bytes)
    (data_dir / "quran-data.xml").write_bytes(metadata_bytes)

    print(f"Validated {len(surahs)} surahs and {len(verses)} ayahs.")
    print("Original text bytes were saved without modifying Qur'anic wording.")
    print("Source: Tanzil Project — https://tanzil.net/")
    print("No video was rendered, uploaded, or published.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
