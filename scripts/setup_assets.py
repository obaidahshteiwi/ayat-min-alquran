#!/usr/bin/env python3
"""Download the Amiri Arabic font and its OFL license from the official repository."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
# Pin to a reviewed upstream commit so the downloaded font is reproducible.
UPSTREAM = "https://raw.githubusercontent.com/aliftype/amiri/d3d0c5cb6fe7196cb4a58608fc5c8ecd2e6e80fa"
FILES = {
    "Amiri-Regular.ttf": f"{UPSTREAM}/fonts/Amiri-Regular.ttf",
    "OFL.txt": f"{UPSTREAM}/OFL.txt",
}


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "AyatMinAlquran/1.0"})
    with urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"Download failed with HTTP {response.status}: {url}")
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Amiri font locally; files are git-ignored.")
    parser.add_argument("--force", action="store_true", help="Replace existing local font and license.")
    args = parser.parse_args()

    target = ROOT / "assets" / "fonts"
    target.mkdir(parents=True, exist_ok=True)
    font_path, license_path = target / "Amiri-Regular.ttf", target / "OFL.txt"
    if not args.force and (font_path.exists() or license_path.exists()):
        raise FileExistsError("A local Amiri font or license already exists. Review it or rerun with --force.")

    font_bytes = fetch(FILES["Amiri-Regular.ttf"])
    license_bytes = fetch(FILES["OFL.txt"])
    if not (font_bytes.startswith(b"\x00\x01\x00\x00") or font_bytes.startswith(b"OTTO")):
        raise RuntimeError("The downloaded font does not have a valid TrueType/OpenType signature.")
    license_text = license_bytes.decode("utf-8")
    if "SIL OPEN FONT LICENSE" not in license_text or "Version 1.1" not in license_text:
        raise RuntimeError("The upstream OFL license could not be verified.")

    font_path.write_bytes(font_bytes)
    license_path.write_bytes(license_bytes)
    print(f"Installed local font: {font_path}")
    print(f"Saved license: {license_path}")
    print("The font and license are excluded from Git by .gitignore.")
    print("Upstream: https://github.com/aliftype/amiri")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
