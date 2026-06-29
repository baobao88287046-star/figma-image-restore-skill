#!/usr/bin/env python3
"""Verify that a restore manifest has the evidence required to call a pass done."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from PIL import Image


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def latest_version(manifest: dict, requested: Optional[str]) -> Optional[dict]:
    versions = manifest.get("versions") or []
    if requested:
        for version in versions:
            if version.get("version") == requested:
                return version
        return None
    return versions[-1] if versions else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--require-figma", action="store_true")
    parser.add_argument("--require-figma-screenshot", action="store_true")
    parser.add_argument("--require-layout-report", action="store_true")
    parser.add_argument("--require-ocr-report", action="store_true")
    parser.add_argument("--require-icon-report", action="store_true")
    parser.add_argument("--require-module-report", action="store_true")
    parser.add_argument("--fail-on-open-issues", action="store_true")
    parser.add_argument("--allow-remaining-issues", action="store_true")
    args = parser.parse_args()

    manifest_path = args.manifest.expanduser().resolve()
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    manifest = json.loads(manifest_path.read_text())
    source = manifest.get("source") or {}
    source_width = source.get("width")
    source_height = source.get("height")
    acceptance = manifest.get("acceptance") or {}
    version = latest_version(manifest, args.version)

    issues = []
    warnings = []
    if not version:
        issues.append(f"Version not found: {args.version or '<latest>'}")
    else:
        svg_path = Path(version.get("svg_path") or "")
        render_path = Path(version.get("local_render_path") or "")
        if not svg_path.exists():
            issues.append(f"SVG missing: {svg_path}")
        if not render_path.exists():
            issues.append(f"Local render missing: {render_path}")
        else:
            width, height = image_size(render_path)
            if source_width and width != source_width:
                issues.append(f"Render width {width} does not match source width {source_width}")
            if source_height and height != source_height:
                issues.append(f"Render height {height} does not match source height {source_height}")

        for path in version.get("comparison_paths") or []:
            if not Path(path).exists():
                issues.append(f"Comparison missing: {path}")
        if not version.get("comparison_paths"):
            issues.append("No comparison_paths recorded for version")

        if args.require_layout_report:
            layout_report = Path(version.get("layout_report_path") or "")
            if not layout_report.exists():
                issues.append(f"Layout report is required but missing: {layout_report}")
        if args.require_ocr_report:
            ocr_report = Path(version.get("ocr_report_path") or "")
            if not ocr_report.exists():
                issues.append(f"OCR report is required but missing: {ocr_report}")
        if args.require_icon_report:
            icon_reports = version.get("icon_report_paths") or []
            if not icon_reports:
                issues.append("Icon report is required but missing")
            for path in icon_reports:
                if not Path(path).exists():
                    issues.append(f"Icon report missing: {path}")
        if args.require_module_report:
            module_report = Path(version.get("module_report_path") or "")
            if not module_report.exists():
                issues.append(f"Repeated module report is required but missing: {module_report}")

        if args.require_figma and not version.get("figma_node_url"):
            issues.append("Figma node URL is required but missing")
        if version.get("remaining_issues") and not args.allow_remaining_issues:
            warnings.append(
                f"Version records remaining issues: {len(version.get('remaining_issues') or [])}"
            )

    required_acceptance = [
        "text_bounds_checked",
        "source_crops_created",
        "local_render_compared",
        "figma_paste_verified" if args.require_figma else None,
        "figma_screenshot_compared" if args.require_figma_screenshot else None,
    ]
    for key in [item for item in required_acceptance if item]:
        if not acceptance.get(key):
            issues.append(f"Acceptance flag is false or missing: {key}")

    if manifest.get("open_issues") and args.fail_on_open_issues:
        issues.append(f"Manifest has open issues: {len(manifest.get('open_issues') or [])}")

    payload = {
        "ok": not issues,
        "manifest": str(manifest_path),
        "version": version.get("version") if version else None,
        "issues": issues,
        "warnings": warnings,
        "acceptance": acceptance,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
