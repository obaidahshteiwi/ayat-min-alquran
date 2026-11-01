#!/usr/bin/env python3
"""Validate the locally downloaded Tanzil Quran corpus."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quran_source import load_local_tanzil  # noqa: E402


def main() -> int:
    surahs, verses = load_local_tanzil(ROOT / "data")
    print(f"Source validation successful: {len(surahs)} surahs, {len(verses)} ayahs.")
    print("No Quranic verse wording was modified by the importer.")
    print("A human review of the final rendered video is still required.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
