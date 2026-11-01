#!/usr/bin/env python3
"""Download reviewed CC0 starter assets from Wikimedia Commons.

The downloader checks the Commons API license metadata and the file SHA-1.
Downloaded binary assets and generated rights manifests remain local.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API = "https://commons.wikimedia.org/w/api.php"

ASSETS = [
    {
        "kind": "audio",
        "title": "Chapter 105, Al-Fil (Murattal) - Recitation of the Holy Qur'an.mp3",
        "destination": ROOT / "assets" / "audio" / "al-fil-105.mp3",
        "manifest": ROOT / "assets" / "audio" / "audio-rights.json",
        "mime": "audio/mpeg",
        "duration": (30.0, 60.0),
    },
    {
        "kind": "background video",
        "title": "Misty river 47 seconds.webm",
        "destination": ROOT / "assets" / "backgrounds" / "misty-river-47s.webm",
        "manifest": ROOT / "assets" / "backgrounds" / "background-rights.json",
        "mime": "video/webm",
        "duration": (35.0, 60.0),
    },
]


def fetch(url: str, max_bytes: int = 150_000_000) -> bytes:
    request = Request(
        url,
        headers={"User-Agent": "AyatMinAlquran/1.0 (personal Quran Shorts project)"},
    )
    with urlopen(request, timeout=90) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} while downloading {url}")
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise RuntimeError("The download exceeded the configured safety limit.")
    return content


def clean_metadata(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def get_commons_file(title: str) -> dict:
    params = urlencode({
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "titles": f"File:{title}",
        "prop": "imageinfo",
        "iiprop": "url|size|sha1|mime|extmetadata",
    })
    response = json.loads(fetch(f"{API}?{params}", 4_000_000).decode("utf-8"))
    pages = response.get("query", {}).get("pages", [])
    if not pages or "missing" in pages[0]:
        raise RuntimeError(f"Commons file not found: {title}")
    image_info = pages[0].get("imageinfo", [])
    if not image_info:
        raise RuntimeError(f"Commons file metadata is missing: {title}")
    return image_info[0]


def duration_seconds(path: Path) -> float:
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is required to validate the media durations.")
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download verified CC0 recitation and nature media locally."
    )
    parser.add_argument("--force", action="store_true", help="Replace existing local starter media.")
    args = parser.parse_args()

    for item in ASSETS:
        if not args.force and (item["destination"].exists() or item["manifest"].exists()):
            raise FileExistsError(
                f"{item['kind']} file or rights manifest already exists. "
                "Inspect it first or use --force."
            )

    for item in ASSETS:
        title = item["title"]
        info = get_commons_file(title)
        metadata = info.get("extmetadata", {})
        license_name = clean_metadata(metadata.get("LicenseShortName", {}).get("value", ""))
        license_url = clean_metadata(metadata.get("LicenseUrl", {}).get("value", ""))
        author = clean_metadata(metadata.get("Artist", {}).get("value", ""))

        if "CC0" not in license_name.upper():
            raise RuntimeError(
                f"Refusing {title}: Commons did not report CC0 1.0 (reported {license_name!r})."
            )
        if "publicdomain/zero/1.0" not in license_url:
            raise RuntimeError(f"Unexpected CC0 license URL for {title}: {license_url!r}")
        if info.get("mime") != item["mime"]:
            raise RuntimeError(f"Unexpected media type for {title}: {info.get('mime')!r}")
        if not info.get("url") or not info.get("sha1") or not author:
            raise RuntimeError(f"Commons metadata for {title} is incomplete.")
        expected_size = int(info.get("size", 0))
        if expected_size <= 0 or expected_size > 150_000_000:
            raise RuntimeError(f"Unexpected file size for {title}: {expected_size}")

        data = fetch(info["url"])
        digest = hashlib.sha1(data).hexdigest()
        if digest.lower() != str(info["sha1"]).lower():
            raise RuntimeError(f"SHA-1 verification failed for {title}.")
        if len(data) != expected_size:
            raise RuntimeError(f"Downloaded file size mismatch for {title}.")

        destination: Path = item["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

        file_page = (
            "https://commons.wikimedia.org/wiki/File:"
            + quote(title.replace(" ", "_"), safe=",:()'_-.")
        )
        attribution = (
            f"{title} — author/uploader: {author}; CC0 1.0; Wikimedia Commons: {file_page}"
        )
        manifest = {
            "asset_file": destination.relative_to(ROOT).as_posix(),
            "reciter": (
                "Not separately identified in the file description"
                if item["kind"] == "audio" else ""
            ),
            "rights_holder": author,
            "license_name": license_name,
            "license_url": license_url,
            "permission_evidence_file": "",
            "youtube_upload_allowed": True,
            "monetization_allowed": True,
            "attribution": attribution,
            "source_url": file_page,
            "source_sha1": digest,
            "notes": (
                "The Commons file page identifies this as the uploader's own work "
                "and states that the copyright holder dedicates it under CC0. "
                "The script rechecks the license metadata and file hash on each download."
            ),
        }
        manifest_path: Path = item["manifest"]
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        seconds = duration_seconds(destination)
        minimum, maximum = item["duration"]
        if not minimum <= seconds <= maximum:
            raise RuntimeError(
                f"{item['kind']} duration {seconds:.2f}s is outside {minimum:.0f}–{maximum:.0f}s."
            )
        print(
            f"Verified {item['kind']}: {destination.name}; {seconds:.2f}s; "
            f"{license_name}; SHA-1 OK."
        )

    print("Starter media saved locally. No upload, publication, or Git commit was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
