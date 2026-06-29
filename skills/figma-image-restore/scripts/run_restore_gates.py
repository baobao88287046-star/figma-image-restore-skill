#!/usr/bin/env python3
"""Run the standard local QA gates for one restore SVG version."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


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
    version.setdefault("remaining_issues", [])

    acceptance = manifest.setdefault("acceptance", {})
    acceptance["text_bounds_checked"] = True
    acceptance["local_render_compared"] = True

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
    _, render_stdout = run(render_cmd)
    outputs["render"] = load_json_from_stdout(render_stdout)
    _, text_stdout = run(text_cmd)
    outputs["text_bounds"] = text_stdout.strip()
    compare_code, compare_stdout = run(compare_cmd, allow_fail=True)
    outputs["comparison"] = load_json_from_stdout(compare_stdout)

    comparison_paths = [outputs["comparison"]["global"]["contact_sheet"]]
    comparison_paths.extend(region["contact_sheet"] for region in outputs["comparison"].get("regions", []))
    comparison_report = comparisons / f"{args.version}_report.json"
    update_manifest(manifest, args.version, svg, render, comparison_paths, comparison_report)

    verify_cmd = [
        sys.executable,
        str(script_dir / "verify_manifest.py"),
        str(manifest),
        "--version",
        args.version,
    ]
    if args.require_figma:
        verify_cmd.append("--require-figma")
    if args.allow_remaining_issues:
        verify_cmd.append("--allow-remaining-issues")
    verify_code, verify_stdout = run(verify_cmd, allow_fail=True)
    outputs["manifest"] = load_json_from_stdout(verify_stdout)

    ok = compare_code == 0 and verify_code == 0 and outputs["comparison"].get("ok")
    outputs["ok"] = bool(ok)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
