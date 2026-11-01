"""Fail closed unless local media has recorded YouTube reuse permission."""

from __future__ import annotations

import json
from pathlib import Path


class MediaRightsError(ValueError):
    """Raised when media permission metadata is missing or insufficient."""


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def validate_media_permission(
    *,
    root: Path,
    asset_path: Path,
    manifest_path: Path,
    media_kind: str,
) -> dict:
    if not manifest_path.is_file():
        raise MediaRightsError(
            f"Missing {media_kind} rights manifest: {manifest_path}. "
            "Do not use this media until its YouTube reuse rights are documented."
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise MediaRightsError(f"Cannot read {media_kind} rights manifest: {exc}") from exc

    declared_asset = manifest.get("asset_file", "")
    if not declared_asset or _resolve(root, declared_asset) != asset_path.resolve():
        raise MediaRightsError(
            f"The rights manifest asset_file must match the selected {media_kind} file."
        )

    for field in ("rights_holder", "license_name"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise MediaRightsError(f"The {media_kind} rights manifest needs a non-empty {field}.")

    if manifest.get("youtube_upload_allowed") is not True:
        raise MediaRightsError(
            f"YouTube reuse is not explicitly approved in the {media_kind} rights manifest."
        )

    license_url = str(manifest.get("license_url", "")).strip()
    evidence_value = str(manifest.get("permission_evidence_file", "")).strip()
    if license_url:
        if not str(manifest.get("attribution", "")).strip():
            raise MediaRightsError(
                f"The {media_kind} license has a URL; provide the exact required attribution."
            )
    elif evidence_value:
        evidence_path = _resolve(root, evidence_value)
        if not evidence_path.is_file():
            raise MediaRightsError(
                f"The permission evidence file does not exist: {evidence_path}"
            )
    else:
        raise MediaRightsError(
            f"The {media_kind} manifest needs either a license_url with attribution "
            "or a local permission_evidence_file."
        )

    return manifest
