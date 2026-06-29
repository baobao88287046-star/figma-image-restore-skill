#!/usr/bin/env python3
"""Create a repeatable work directory for an image-to-Figma restore run."""

import argparse
import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_dimensions(path: Path):
    data = path.read_bytes()

    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return width, height, "png"

    if data.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 9 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            pos += 2
            if marker in (0xD8, 0xD9):
                continue
            if pos + 2 > len(data):
                break
            size = struct.unpack(">H", data[pos : pos + 2])[0]
            if size < 2 or pos + size > len(data):
                break
            if marker in range(0xC0, 0xD0) and marker not in (0xC4, 0xC8, 0xCC):
                height, width = struct.unpack(">HH", data[pos + 3 : pos + 7])
                return width, height, "jpeg"
            pos += size

    return None, None, "unknown"


def safe_label(path: Path, label: Optional[str]) -> str:
    base = label or path.stem
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in base.lower())
    safe = "-".join(part for part in safe.split("-") if part)
    return safe or "restore"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Source PNG/JPG screenshot.")
    parser.add_argument("--outdir", type=Path, default=Path("figma_restore_runs"))
    parser.add_argument("--label", help="Stable run label, defaults to source stem.")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.exists():
        print(f"Source not found: {source}", file=sys.stderr)
        return 2

    width, height, kind = image_dimensions(source)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_name = f"{timestamp}-{safe_label(source, args.label)}"
    run_dir = args.outdir.expanduser().resolve() / run_name

    dirs = {
        "assets": run_dir / "assets",
        "crops": run_dir / "crops",
        "renders": run_dir / "renders",
        "figma_screenshots": run_dir / "figma-screenshots",
        "comparisons": run_dir / "comparisons",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=False)

    manifest = {
        "run_name": run_name,
        "created_at_utc": timestamp,
        "source": {
            "path": str(source),
            "sha256": file_sha256(source),
            "format": kind,
            "width": width,
            "height": height,
        },
        "directories": {key: str(value) for key, value in dirs.items()},
        "versions": [],
        "open_issues": [],
        "acceptance": {
            "text_bounds_checked": False,
            "source_crops_created": False,
            "local_render_compared": False,
            "figma_paste_verified": False,
            "figma_screenshot_compared": False,
        },
    }
    manifest_path = run_dir / "restore_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
