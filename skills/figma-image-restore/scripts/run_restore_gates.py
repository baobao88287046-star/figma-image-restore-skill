#!/usr/bin/env python3
"""Run the standard local QA gates for one restore SVG version."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


def run(command: list[str], allow_fail: bool = False) -> tuple[int, str]:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode != 0 and not allow_fail:
        raise RuntimeError(result.stdout)
    return result.returncode, result.stdout


def load_json_from_stdout(stdout: str) -> dict:
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"No JSON object found in output: {stdout!r}")
    return json.loads(stdout[start : end + 1])


def update_manifest(
    manifest_path: Path,
    version_name: str,
    svg_path: Path,
    render_path: Path,
    comparison_paths: list[str],
    comparison_report: Path,
    layout_report: Optional[Path] = None,
    layout_overlay: Optional[Path] = None,
    ocr_report: Optional[Path] = None,
    icon_reports: Optional[list[str]] = None,
    icon_contact_sheets: Optional[list[str]] = None,
    module_report: Optional[Path] = None,
) -> None:
    manifest = json.loads(manifest_path.read_text())
    versions = manifest.setdefault("versions", [])
    version = None
    for candidate in versions:
        if candidate.get("version") == version_name:
            version = candidate
            break
    if version is None:
        version = {"version": version_name}
        versions.append(version)

    version.setdefault("svg_path", str(svg_path))
    version["local_render_path"] = str(render_path)
    version["comparison_paths"] = comparison_paths
    version["comparison_report_path"] = str(comparison_report)
    if layout_report:
        version["layout_report_path"] = str(layout_report)
    if layout_overlay:
        version["layout_overlay_path"] = str(layout_overlay)
    if ocr_report:
        version["ocr_report_path"] = str(ocr_report)
    if icon_reports:
        version["icon_report_paths"] = icon_reports
    if icon_contact_sheets:
        version["icon_contact_sheets"] = icon_contact_sheets
    if module_report:
        version["module_report_path"] = str(module_report)
    version.setdefault("remaining_issues", [])

    acceptance = manifest.setdefault("acceptance", {})
    acceptance["text_bounds_checked"] = True
    acceptance["local_render_compared"] = True
    if layout_report:
        acceptance["layout_extracted"] = True
    if ocr_report:
        acceptance["ocr_text_checked"] = True
    if icon_reports:
        acceptance["icon_strip_checked"] = True
    if module_report:
        acceptance["repeated_modules_checked"] = True

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--screen-width", type=int, required=True)
    parser.add_argument("--screen-height", type=int, required=True)
    parser.add_argument("--region", action="append", default=[])
    parser.add_argument("--extract-layout", action="store_true")
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--ocr-lang", default="chi_sim+eng")
    parser.add_argument("--require-ocr-pass", action="store_true")
    parser.add_argument("--icon-region", action="append", default=[])
    parser.add_argument("--module-card", action="append", default=[], help="Repeated module box as name:x,y,w,h")
    parser.add_argument("--partial-module-card", action="append", default=[], help="Clipped preview module as full logical name:x,y,w,h")
    parser.add_argument("--module-tolerance", type=float, default=3.0)
    parser.add_argument("--module-font-tolerance", type=float, default=0.1)
    parser.add_argument("--require-figma", action="store_true")
    parser.add_argument("--allow-remaining-issues", action="store_true")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    source = args.source.expanduser().resolve()
    svg = args.svg.expanduser().resolve()
    manifest = args.manifest.expanduser().resolve()
    run_dir = manifest.parent
    renders = run_dir / "renders"
    comparisons = run_dir / "comparisons" / args.version
    render = renders / f"{svg.stem}_gate_full.png"

    render_cmd = [
        sys.executable,
        str(script_dir / "render_svg_full.py"),
        str(svg),
        "--out",
        str(render),
        "--expected-width",
        str(args.screen_width),
        "--expected-height",
        str(args.screen_height),
    ]
    text_cmd = [
        sys.executable,
        str(script_dir / "check_svg_text_bounds.py"),
        str(svg),
        "--screen-width",
        str(args.screen_width),
        "--safe-margin",
        "20",
    ]
    compare_cmd = [
        sys.executable,
        str(script_dir / "compare_regions.py"),
        str(source),
        str(render),
        "--outdir",
        str(comparisons),
        "--label",
        args.version,
    ]
    for region in args.region:
        compare_cmd.extend(["--region", region])

    outputs = {}
    layout_report = None
    layout_overlay = None
    if args.extract_layout:
        layout_dir = comparisons / "layout"
        layout_report = layout_dir / f"{args.version}_layout.json"
        layout_overlay = layout_dir / f"{args.version}_layout_overlay.png"
        layout_cmd = [
            sys.executable,
            str(script_dir / "extract_layout.py"),
            str(source),
            "--out",
            str(layout_report),
            "--overlay",
            str(layout_overlay),
        ]
        _, layout_stdout = run(layout_cmd)
        outputs["layout"] = load_json_from_stdout(layout_stdout)

    _, render_stdout = run(render_cmd)
    outputs["render"] = load_json_from_stdout(render_stdout)
    _, text_stdout = run(text_cmd)
    outputs["text_bounds"] = text_stdout.strip()
    compare_code, compare_stdout = run(compare_cmd, allow_fail=True)
    outputs["comparison"] = load_json_from_stdout(compare_stdout)

    ocr_report = None
    ocr_code = 0
    if args.ocr:
        ocr_report = comparisons / f"{args.version}_ocr_report.json"
        ocr_cmd = [
            sys.executable,
            str(script_dir / "ocr_text_check.py"),
            "--source",
            str(source),
            "--svg",
            str(svg),
            "--out",
            str(ocr_report),
            "--lang",
            args.ocr_lang,
        ]
        if args.require_ocr_pass:
            ocr_cmd.append("--fail-on-missing")
        ocr_code, ocr_stdout = run(ocr_cmd, allow_fail=True)
        outputs["ocr"] = load_json_from_stdout(ocr_stdout)

    icon_reports = []
    icon_contact_sheets = []
    icon_code = 0
    if args.icon_region:
        icon_dir = comparisons / "icons"
        icon_cmd = [
            sys.executable,
            str(script_dir / "compare_icon_strip.py"),
            str(source),
            str(render),
            "--outdir",
            str(icon_dir),
            "--label",
            args.version,
        ]
        for region in args.icon_region:
            icon_cmd.extend(["--region", region])
        icon_code, icon_stdout = run(icon_cmd, allow_fail=True)
        outputs["icons"] = load_json_from_stdout(icon_stdout)
        if outputs["icons"].get("report"):
            icon_reports.append(outputs["icons"]["report"])
        icon_contact_sheets.extend(
            region["contact_sheet"] for region in outputs["icons"].get("regions", [])
        )

    module_report = None
    module_code = 0
    if args.module_card or args.partial_module_card:
        module_report = comparisons / f"{args.version}_module_report.json"
        module_cmd = [
            sys.executable,
            str(script_dir / "check_repeated_modules.py"),
            str(svg),
            "--out",
            str(module_report),
            "--tolerance",
            str(args.module_tolerance),
            "--font-tolerance",
            str(args.module_font_tolerance),
        ]
        for card in args.module_card:
            module_cmd.extend(["--card", card])
        for card in args.partial_module_card:
            module_cmd.extend(["--partial-card", card])
        module_code, module_stdout = run(module_cmd, allow_fail=True)
        outputs["modules"] = load_json_from_stdout(module_stdout)

    comparison_paths = [outputs["comparison"]["global"]["contact_sheet"]]
    comparison_paths.extend(region["contact_sheet"] for region in outputs["comparison"].get("regions", []))
    comparison_report = comparisons / f"{args.version}_report.json"
    update_manifest(
        manifest,
        args.version,
        svg,
        render,
        comparison_paths,
        comparison_report,
        layout_report=layout_report,
        layout_overlay=layout_overlay,
        ocr_report=ocr_report,
        icon_reports=icon_reports,
        icon_contact_sheets=icon_contact_sheets,
        module_report=module_report,
    )

    verify_cmd = [
        sys.executable,
        str(script_dir / "verify_manifest.py"),
        str(manifest),
        "--version",
        args.version,
    ]
    if args.require_figma:
        verify_cmd.append("--require-figma")
    if args.extract_layout:
        verify_cmd.append("--require-layout-report")
    if args.ocr:
        verify_cmd.append("--require-ocr-report")
    if args.icon_region:
        verify_cmd.append("--require-icon-report")
    if args.module_card or args.partial_module_card:
        verify_cmd.append("--require-module-report")
    if args.allow_remaining_issues:
        verify_cmd.append("--allow-remaining-issues")
    verify_code, verify_stdout = run(verify_cmd, allow_fail=True)
    outputs["manifest"] = load_json_from_stdout(verify_stdout)

    ok = (
        compare_code == 0
        and verify_code == 0
        and ocr_code == 0
        and icon_code == 0
        and module_code == 0
        and outputs["comparison"].get("ok")
    )
    outputs["ok"] = bool(ok)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
