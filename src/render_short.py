#!/usr/bin/env python3
"""Render a local 9:16 Quran Shorts video. Never uploads or publishes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

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


def shape_arabic(text: str) -> str:
    # Presentation shaping is applied only for display; the source verse is not rewritten.
    return get_display(arabic_reshaper.reshape(text))


def wrap_arabic(text: str, font: ImageFont.FreeTypeFont,
                draw: ImageDraw.ImageDraw, max_width: int) -> list[str]:
    lines: list[str] = []
    paragraphs = text.splitlines() or [text]
    for paragraph in paragraphs:
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            shaped = shape_arabic(candidate)
            if current and draw.textbbox((0, 0), shaped, font=font)[2] > max_width:
                lines.append(shape_arabic(current))
                current = word
            else:
                current = candidate
        if current:
            lines.append(shape_arabic(current))
    return lines


def make_text_overlay(path: Path, verse: str, reference: str, cfg: dict,
                      show_tanzil_credit: bool) -> None:
    width, height = int(cfg["video"]["width"]), int(cfg["video"]["height"])
    typography = cfg["typography"]
    font_path = ROOT / typography["font_path"]
    if not font_path.is_file():
        raise FileNotFoundError(
            f"Arabic font not found: {font_path}. Add a properly licensed font and update config.json."
        )

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    verse_font = ImageFont.truetype(str(font_path), int(typography["font_size"]))
    ref_font = ImageFont.truetype(str(font_path), int(typography["reference_font_size"]))
    credit_font = ImageFont.truetype(str(font_path), max(20, int(typography["reference_font_size"]) // 2))

    lines = wrap_arabic(verse, verse_font, draw, int(width * 0.84))
    line_gap = 28
    line_heights = [
        draw.textbbox((0, 0), line, font=verse_font)[3] -
        draw.textbbox((0, 0), line, font=verse_font)[1]
        for line in lines
    ]
    ref_display = shape_arabic(reference)
    ref_box = draw.textbbox((0, 0), ref_display, font=ref_font)
    ref_height = ref_box[3] - ref_box[1]

    credit_display = shape_arabic("المصدر: مشروع تنزيل - Tanzil.net") if show_tanzil_credit else ""
    credit_box = draw.textbbox((0, 0), credit_display, font=credit_font) if credit_display else (0, 0, 0, 0)
    credit_height = credit_box[3] - credit_box[1]
    total_height = sum(line_heights) + line_gap * max(0, len(lines) - 1) + 45 + ref_height
    if show_tanzil_credit:
        total_height += 24 + credit_height

    y = (height - total_height) // 2
    color = typography.get("text_color", "#FFFFFF")
    panel_top, panel_bottom = max(80, y - 55), min(height - 80, y + total_height + 55)
    draw.rounded_rectangle(
        (width * 0.06, panel_top, width * 0.94, panel_bottom),
        radius=38, fill=(0, 0, 0, 92), outline=(255, 255, 255, 45), width=2
    )

    for line, line_height in zip(lines, line_heights):
        box = draw.textbbox((0, 0), line, font=verse_font, stroke_width=1)
        x = (width - (box[2] - box[0])) // 2
        draw.text((x, y), line, font=verse_font, fill=color,
                  stroke_width=1, stroke_fill=(0, 0, 0, 150))
        y += line_height + line_gap

    y += 45
    x = (width - (ref_box[2] - ref_box[0])) // 2
    draw.text((x, y), ref_display, font=ref_font, fill="#F4DFA8",
              stroke_width=1, stroke_fill=(0, 0, 0, 150))

    if show_tanzil_credit:
        y += ref_height + 24
        x = (width - (credit_box[2] - credit_box[0])) // 2
        draw.text((x, y), credit_display, font=credit_font, fill="#FFFFFF",
                  stroke_width=1, stroke_fill=(0, 0, 0, 150))

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
        verse_text = "\n".join(verse_list)
        verse_ids = [
            f"{surah_number}:{number}"
            for number in range(first_ayah, last_ayah + 1)
        ]
        return (
            verse_text, surah_name, surah_number, first_ayah, last_ayah,
            verse_ids, True
        )

    if not args.verse or not args.surah or args.ayah is None:
        raise ValueError(
            "Use --verse-key, --verse-range, or provide --verse, --surah, and --ayah together."
        )
    if args.ayah < 1:
        raise ValueError("Manual ayah number must be positive.")
    manual_id = f"manual:{args.surah}:{args.ayah}"
    return args.verse, args.surah, None, args.ayah, args.ayah, [manual_id], False

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

    verse_text, surah_name, surah_number, first_ayah, last_ayah, verse_ids, source_verified = parse_verse(args)

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
    ayah_label = (
        f"الآية {first_ayah}"
        if first_ayah == last_ayah
        else f"الآيات {first_ayah}–{last_ayah}"
    )
    reference = f"سورة {surah_name} • {ayah_label}"
    make_text_overlay(overlay_image, verse_text, reference, cfg, source_verified)

    duration_frames = max(1, int(duration * fps))
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
        inputs = ["-stream_loop", "-1", "-i", str(bg_path), "-i", str(audio),
                  "-loop", "1", "-i", str(overlay_image)]
        base_filter = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},trim=duration={duration}[bg];"
        )
    else:
        inputs = ["-loop", "1", "-i", str(background_image), "-i", str(audio),
                  "-loop", "1", "-i", str(overlay_image)]
        base_filter = (
            f"[0:v]scale={width}:{height},zoompan=z='min(zoom+0.0005,1.06)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={duration_frames}:s={width}x{height}:fps={fps}[bg];"
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
