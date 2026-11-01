#!/usr/bin/env python3
"""Render a local 9:16 Quran Shorts video. Never uploads or publishes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quran_source import get_verified_verses  # noqa: E402
from media_rights import validate_media_permission  # noqa: E402


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def probe_duration(audio_path: Path) -> float:
    raw = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)
    ])
    return float(raw)


def make_fallback_landscape(path: Path, width: int, height: int) -> None:
    """Create an original illustrated landscape if no licensed footage is supplied."""
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    top, bottom = (18, 47, 69), (126, 154, 139)
    for y in range(height):
        t = y / max(1, height - 1)
        shade = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(width):
            pixels[x, y] = shade

    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((width * 0.66, height * 0.16, width * 0.84, height * 0.25),
                 fill=(255, 231, 174, 210))
    draw.polygon([
        (0, height * 0.60), (width * 0.25, height * 0.34),
        (width * 0.48, height * 0.61), (width * 0.73, height * 0.39),
        (width, height * 0.64), (width, height), (0, height)
    ], fill=(42, 78, 76, 255))
    draw.polygon([
        (0, height * 0.73), (width * 0.31, height * 0.53),
        (width * 0.57, height * 0.76), (width * 0.82, height * 0.58),
        (width, height * 0.75), (width, height), (0, height)
    ], fill=(27, 59, 57, 255))
    image.save(path)


def load_arabic_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    """Load a font with HarfBuzz/FriBidi shaping through Pillow's RAQM engine."""
    if not features.check_feature("raqm"):
        raise RuntimeError(
            "Pillow was built without libraqm support. Install libraqm-dev, "
            "libharfbuzz-dev and libfribidi-dev, then rebuild Pillow."
        )
    return ImageFont.truetype(
        str(path), size, layout_engine=ImageFont.Layout.RAQM
    )


def arabic_text_bbox(draw: ImageDraw.ImageDraw, text: str,
                     font: ImageFont.FreeTypeFont) -> tuple[int, int, int, int]:
    return draw.textbbox((0, 0), text, font=font, direction="rtl", language="ar")


def arabic_indic_number(number: int) -> str:
    """Format an ayah number using Arabic-Indic digits."""
    return str(number).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def split_tanzil_basmala(verse: str) -> tuple[str, str] | None:
    """Separate the unnumbered opening basmala from Tanzil ayah 1 for surahs 2–114."""
    expected = "بسماللهالرحمنالرحيم"
    letter_map = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"}
    collected = []
    end_index = None
    for index, char in enumerate(verse):
        if char.isspace() or char == "ـ" or unicodedata.category(char).startswith("M"):
            continue
        collected.append(letter_map.get(char, char))
        if len(collected) == len(expected):
            end_index = index + 1
            break
    if "".join(collected) != expected or end_index is None:
        return None

    # Keep diacritics attached to the final letter of the basmala.
    while end_index < len(verse) and (
        verse[end_index] == "ـ"
        or unicodedata.category(verse[end_index]).startswith("M")
    ):
        end_index += 1

    basmala = verse[:end_index].strip()
    remainder = verse[end_index:].lstrip()
    if not basmala or not remainder:
        return None
    return basmala, remainder


def build_display_items(
    verses: list[str], surah_number: int | None, first_ayah: int
) -> list[tuple[str, str]]:
    """Build visual blocks while preserving all original Tanzil verse text."""
    display_verses = list(verses)
    items: list[tuple[str, str]] = []

    # Tanzil stores basmalas for surahs 2–114 in the first ayah record.
    # Display it separately and without a number, as in the Medina Mushaf.
    if surah_number not in (None, 1, 9) and first_ayah == 1:
        split = split_tanzil_basmala(display_verses[0])
        if split is None:
            raise ValueError(
                "Could not safely separate Tanzil's opening basmala from ayah 1. "
                "The source text was left unchanged; refusing ambiguous numbering."
            )
        basmala, first_verse = split
        items.append(("basmala", basmala))
        display_verses[0] = first_verse

    for offset, verse_text in enumerate(display_verses):
        ayah_number = first_ayah + offset
        items.append(("ayah", f"{verse_text} ۝{arabic_indic_number(ayah_number)}"))
    return items


def format_ayah_reference(surah_name: str, first_ayah: int, last_ayah: int) -> str:
    if first_ayah == last_ayah:
        return f"سورة {surah_name} • الآية {arabic_indic_number(first_ayah)}"
    return (
        f"سورة {surah_name} • من الآية "
        f"{arabic_indic_number(first_ayah)} إلى الآية {arabic_indic_number(last_ayah)}"
    )


def wrap_arabic(text: str, font: ImageFont.FreeTypeFont,
                draw: ImageDraw.ImageDraw, max_width: int) -> list[str]:
    """Wrap logical Arabic text; RAQM shapes and orders it only while rendering."""
    lines: list[str] = []
    paragraphs = text.splitlines() or [text]
    for paragraph in paragraphs:
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            bbox = arabic_text_bbox(draw, candidate, font)
            if current and bbox[2] - bbox[0] > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def draw_centered_arabic(draw: ImageDraw.ImageDraw, text: str, y: int,
                         font: ImageFont.FreeTypeFont, width: int,
                         fill: str, stroke_width: int = 0,
                         stroke_fill: str | None = None) -> int:
    bbox = arabic_text_bbox(draw, text, font)
    x = (width - (bbox[2] - bbox[0])) // 2 - bbox[0]
    draw.text(
        (x, y - bbox[1]), text, font=font, fill=fill,
        stroke_width=stroke_width, stroke_fill=stroke_fill,
        direction="rtl", language="ar",
    )
    return bbox[3] - bbox[1]


def make_text_overlay(path: Path, display_items: list[tuple[str, str]],
                      reference: str, cfg: dict, show_tanzil_credit: bool) -> None:
    width, height = int(cfg["video"]["width"]), int(cfg["video"]["height"])
    typography = cfg["typography"]
    font_path = ROOT / typography["font_path"]
    if not font_path.is_file():
        raise FileNotFoundError(
            f"Arabic font not found: {font_path}. Add a properly licensed font and update config.json."
        )

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    verse_font = load_arabic_font(font_path, int(typography["font_size"]))
    basmala_font = load_arabic_font(font_path, int(typography.get("basmala_font_size", 48)))
    ref_font = load_arabic_font(font_path, int(typography["reference_font_size"]))
    credit_font = load_arabic_font(
        font_path, max(20, int(typography["reference_font_size"]) // 2)
    )

    blocks = []
    line_gap = 12
    block_gap = 25
    for kind, text in display_items:
        font = basmala_font if kind == "basmala" else verse_font
        lines = wrap_arabic(text, font, draw, int(width * 0.84))
        heights = [
            (bbox := arabic_text_bbox(draw, line, font))[3] - bbox[1]
            for line in lines
        ]
        blocks.append((kind, lines, heights, font))

    text_height = sum(sum(block[2]) for block in blocks)
    text_height += line_gap * sum(max(0, len(block[1]) - 1) for block in blocks)
    text_height += block_gap * max(0, len(blocks) - 1)

    ref_box = arabic_text_bbox(draw, reference, ref_font)
    ref_height = ref_box[3] - ref_box[1]
    credit_display = "المصدر: مشروع تنزيل - Tanzil.net" if show_tanzil_credit else ""
    credit_box = (
        arabic_text_bbox(draw, credit_display, credit_font)
        if credit_display else (0, 0, 0, 0)
    )
    credit_height = credit_box[3] - credit_box[1]
    separator_gap = 34
    total_height = text_height + separator_gap + ref_height
    if show_tanzil_credit:
        total_height += 20 + credit_height
    if total_height > height - 220:
        raise ValueError(
            "The selected ayahs do not fit safely in one vertical Short. "
            "Use a shorter ayah range so every ayah number remains readable."
        )

    y = (height - total_height) // 2
    color = typography.get("text_color", "#FFFFFF")
    panel_top = max(80, y - 48)
    panel_bottom = min(height - 80, y + total_height + 48)
    draw.rounded_rectangle(
        (width * 0.055, panel_top, width * 0.945, panel_bottom),
        radius=38, fill=(0, 0, 0, 112), outline=(255, 255, 255, 58), width=2
    )

    for block_index, (kind, lines, heights, font) in enumerate(blocks):
        fill = "#F4DFA8" if kind == "basmala" else color
        for line, line_height in zip(lines, heights):
            draw_centered_arabic(
                draw, line, y, font, width, fill,
                stroke_width=1, stroke_fill=(0, 0, 0, 165)
            )
            y += line_height + line_gap
        if lines:
            y -= line_gap
        if block_index < len(blocks) - 1:
            y += block_gap

    y += separator_gap
    draw_centered_arabic(
        draw, reference, y, ref_font, width, "#F4DFA8",
        stroke_width=1, stroke_fill=(0, 0, 0, 150)
    )
    if show_tanzil_credit:
        y += ref_height + 20
        draw_centered_arabic(
            draw, credit_display, y, credit_font, width, "#FFFFFF",
            stroke_width=1, stroke_fill=(0, 0, 0, 150)
        )
    canvas.save(path)

def parse_verse(args):
    if args.verse_key or args.verse_range:
        source_value = args.verse_key or args.verse_range
        try:
            surah_part, ayah_part = source_value.split(":", 1)
            surah_number = int(surah_part)
            if args.verse_key:
                first_ayah = last_ayah = int(ayah_part)
            else:
                first_part, last_part = ayah_part.split("-", 1)
                first_ayah, last_ayah = int(first_part), int(last_part)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Use --verse-key SURAH:AYAH or --verse-range SURAH:FIRST-LAST."
            ) from exc

        verse_list, surah_name = get_verified_verses(
            ROOT / "data", surah_number, first_ayah, last_ayah
        )
        display_items = build_display_items(verse_list, surah_number, first_ayah)
        verse_ids = [
            f"{surah_number}:{number}"
            for number in range(first_ayah, last_ayah + 1)
        ]
        return (
            display_items, surah_name, surah_number, first_ayah, last_ayah,
            verse_ids, True
        )

    if not args.verse or not args.surah or args.ayah is None:
        raise ValueError(
            "Use --verse-key, --verse-range, or provide --verse, --surah, and --ayah together."
        )
    if args.ayah < 1:
        raise ValueError("Manual ayah number must be positive.")
    manual_id = f"manual:{args.surah}:{args.ayah}"
    manual_items = [("ayah", f"{args.verse} ۝{arabic_indic_number(args.ayah)}")]
    return manual_items, args.surah, None, args.ayah, args.ayah, [manual_id], False

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a local Quran Shorts video; no upload or publishing is performed."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--verse-key", help="Verified Tanzil verse key, e.g. 2:255.")
    source.add_argument("--verse-range", help="Consecutive verified range, e.g. 105:1-5.")
    source.add_argument("--verse", help="Manual verse text; use only after checking it against a Mushaf.")
    parser.add_argument("--surah", help="Required with manual --verse.")
    parser.add_argument("--ayah", type=int, help="Required with manual --verse.")
    parser.add_argument("--audio", help="Path to a licensed recitation audio file.")
    parser.add_argument("--audio-license", help="Local JSON rights manifest for the recitation.")
    parser.add_argument("--background", help="Optional licensed background video file.")
    parser.add_argument("--background-license", help="Local JSON rights manifest for the background video.")
    parser.add_argument("--config", default="config.json", help="Path to local config JSON.")
    parser.add_argument("--output", help="Optional output MP4 path.")
    parser.add_argument("--allow-repeat", action="store_true",
                        help="Allow rendering a verse already in the registry.")
    args = parser.parse_args()

    for executable in ("ffmpeg", "ffprobe"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"{executable} is required and must be available on PATH.")

    display_items, surah_name, surah_number, first_ayah, last_ayah, verse_ids, source_verified = parse_verse(args)

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    cfg = load_json(config_path)

    audio = Path(args.audio or cfg["media"].get("audio_file", ""))
    if not audio.is_absolute():
        audio = (ROOT / audio).resolve()
    if not audio.is_file():
        raise FileNotFoundError("A licensed recitation file is required. Set --audio or media.audio_file.")

    audio_license = Path(args.audio_license or cfg["media"].get("audio_license_file", ""))
    if not audio_license.is_absolute():
        audio_license = (ROOT / audio_license).resolve()
    validate_media_permission(
        root=ROOT, asset_path=audio, manifest_path=audio_license, media_kind="recitation audio"
    )

    duration = probe_duration(audio)
    min_duration = float(cfg["video"]["min_duration_seconds"])
    max_duration = float(cfg["video"]["max_duration_seconds"])
    if not min_duration <= duration <= max_duration:
        raise ValueError(f"Audio duration is {duration:.1f}s; expected {min_duration:.0f}–{max_duration:.0f}s.")

    registry_path = ROOT / "data" / "used_verses.json"
    registry = load_json(registry_path)
    already_used = sorted(set(verse_ids).intersection(registry.get("used", [])))
    if already_used and not args.allow_repeat:
        raise ValueError(f"These verses were already used: {', '.join(already_used)}")

    width, height = int(cfg["video"]["width"]), int(cfg["video"]["height"])
    fps = int(cfg["video"]["fps"])
    output_dir = ROOT / cfg["video"]["output_directory"]
    output_dir.mkdir(parents=True, exist_ok=True)
    if surah_number:
        file_stem = (
            f"s{surah_number:03}-a{first_ayah:03}"
            if first_ayah == last_ayah
            else f"s{surah_number:03}-a{first_ayah:03}-{last_ayah:03}"
        )
    else:
        file_stem = f"manual-a{first_ayah:03}"
    output = Path(args.output) if args.output else output_dir / f"{file_stem}.mp4"
    if not output.is_absolute():
        output = (ROOT / output).resolve()

    work_dir = ROOT / ".render_tmp"
    work_dir.mkdir(exist_ok=True)
    background_image = work_dir / "landscape.png"
    overlay_image = work_dir / "verse_overlay.png"
    make_fallback_landscape(background_image, width, height)
    reference = format_ayah_reference(surah_name, first_ayah, last_ayah)
    make_text_overlay(overlay_image, display_items, reference, cfg, source_verified)

    background_video = args.background or cfg["media"].get("background_video", "")
    if background_video:
        bg_path = Path(background_video)
        if not bg_path.is_absolute():
            bg_path = (ROOT / bg_path).resolve()
        if not bg_path.is_file():
            raise FileNotFoundError(f"Background video not found: {bg_path}")
        background_license = Path(
            args.background_license or cfg["media"].get("background_license_file", "")
        )
        if not background_license.is_absolute():
            background_license = (ROOT / background_license).resolve()
        validate_media_permission(
            root=ROOT, asset_path=bg_path, manifest_path=background_license,
            media_kind="background video"
        )
        inputs = [
            "-stream_loop", "-1", "-i", str(bg_path), "-i", str(audio),
            "-loop", "1", "-framerate", str(fps), "-i", str(overlay_image),
        ]
        base_filter = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},trim=duration={duration}[bg];"
        )
    else:
        inputs = [
            "-loop", "1", "-framerate", str(fps), "-i", str(background_image),
            "-i", str(audio),
            "-loop", "1", "-framerate", str(fps), "-i", str(overlay_image),
        ]
        base_filter = (
            f"[0:v]scale={width}:{height},zoompan=z='min(zoom+0.0005,1.06)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={width}x{height}:fps={fps}[bg];"
        )

    filter_complex = base_filter + "[bg][2:v]overlay=0:0:format=auto,format=yuv420p[v]"
    command = [
        "ffmpeg", "-y", *inputs, "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a:0", "-t", str(duration),
        "-c:v", "libx264", "-preset", "medium", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)
    ]
    run(command)

    if not args.allow_repeat:
        registry.setdefault("used", []).extend(verse_ids)
        registry_path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(f"Video created locally: {output}")
    if not source_verified:
        print("WARNING: Manual verse text was supplied; its wording was not source-validated by this tool.")
    print("No upload, publication, scheduling, or YouTube API call was performed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
